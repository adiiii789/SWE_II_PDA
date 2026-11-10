"""Funktionen für das Frontend.

Jede Funktion in dieser Datei ist im Frontend (frontend/*.js) unter demselben
Namen aufrufbar:  result = await name(arg1, arg2);
Funktionen mit "_" am Anfang bleiben privat.
Argumente und Rückgabewerte müssen JSON-tauglich sein (str, int, list, dict ...).
Aufrufe laufen in einem Hintergrund-Thread - auch langsame Funktionen frieren
das Popup nicht ein.
"""
from __future__ import annotations

import logging
import re
import threading
import webbrowser
from functools import cache
from typing import Any

from backend import config, proactive
from backend.assistant import Assistant, ConsultingAssistant, ModelPreloading, ModelSelection, create_assistant
from backend.assistant.settings import AssistantSettings, is_internal_tool
from backend.assistant.tools import ToolResult
from backend.preferences import JsonPreferenceStore, default_store
from backend.events import POPUP_ENLARGED, events
from backend.presenter import attachment_store, present, renderer
from backend.proactive_settings import ProactiveSettings
from backend.speech import SpeechInput, SpeechOutput, create_speech_input, create_speech_output
from backend.startup import Startup, Step
from backend.views import START_VIEW, view_from_dict
from backend.watcher import ProactiveWatcher

log = logging.getLogger(__name__)

# Der Assistent ist nicht thread-sicher. Bridge-Aufrufe laufen nacheinander, proaktive
# Meldungen kommen aber aus einem anderen Thread (backend/desktop/application.py).
_assistant_lock = threading.Lock()

@cache
def _assistant() -> Assistant:
    """Ein Assistent für die ganze Laufzeit (behält später z. B. den Chat-Verlauf)."""
    return create_assistant()


def chat(message: str) -> dict[str, Any]:
    """Antwort des Assistenten: {"text", "html", "attachments"} (siehe backend/presenter.py)."""
    with _assistant_lock:
        reply = _assistant().reply(message)
    return present(reply)


def render_view(request: dict[str, Any]) -> str:
    """HTML fürs iframe aus einer Anfrage - Template oder eigenes HTML:

    {"template": "default", "data": {"title": "...", ...}}
    {"html": "<h1>...</h1>"}
    """
    return renderer().render(view_from_dict(request))


def start_view() -> str:
    """HTML der Startansicht fürs iframe."""
    return renderer().render(START_VIEW)


_TASK_REF = re.compile(r"[^\s:]{1,200}::[^\s:]{1,200}")   # Liste::Aufgabe, wie google_tasks.make_ref


def complete_task_from_view(task_id: str, done: bool = True) -> str:
    """Aufgabe abhaken (oder wieder öffnen), weil der Nutzer sie in der Aufgabenansicht angeklickt hat
    (frontend/templates/dashboard.html.j2). Läuft ohne Sprachmodell direkt über das Werkzeug complete_task."""
    if not isinstance(task_id, str) or not _TASK_REF.fullmatch(task_id):
        raise ValueError("Ungültige Aufgaben-ID")
    tools = getattr(_assistant(), "tools", None)
    if tools is None:
        raise RuntimeError("Aufgaben sind nicht verfügbar")
    with _assistant_lock:   # MCP-Clients teilt der Assistent - nicht gleichzeitig benutzen
        result = tools.call_tool("complete_task", {"task_id": task_id, "done": bool(done)})
    if result.is_error:
        raise RuntimeError(result.content)
    return result.content


def list_models() -> dict[str, Any]:
    """Wählbare Sprachmodelle: {"models": [{"name", "tools", "cloud", optional "id"}], "current": str | None}.
    Ohne Sprachmodell (CommandAssistant) ist die Liste leer."""
    assistant = _assistant()
    if not isinstance(assistant, ModelSelection):
        return {"models": [], "current": None}
    with _assistant_lock:
        return {"models": assistant.available_models(), "current": assistant.current_model()}


def select_model(name: str) -> str:
    """Sprachmodell wechseln (bleibt gespeichert). Gibt den Namen zurück."""
    assistant = _assistant()
    if not isinstance(assistant, ModelSelection):
        raise ValueError("Dieser Assistent nutzt kein Sprachmodell")
    with _assistant_lock:
        assistant.select_model(name)
    return name


def open_attachment(attachment_id: str) -> str:
    """Datei aus dem Chat mit dem Standardprogramm öffnen. Gibt den Dateinamen zurück."""
    return attachment_store().open(attachment_id)


def save_attachment(attachment_id: str) -> str:
    """Datei aus dem Chat in den Download-Ordner kopieren. Gibt den Zielpfad zurück."""
    return attachment_store().save(attachment_id)


@cache
def _speech_input() -> SpeechInput | None:
    return create_speech_input()


@cache
def _speech_output() -> SpeechOutput | None:
    return create_speech_output()


def speech_support() -> dict[str, bool]:
    """Welche Sprachfunktionen da sind: {"input": bool, "output": bool} - fehlende blendet das Frontend aus."""
    return {"input": _speech_input() is not None, "output": _speech_output() is not None}


def start_recording() -> None:
    """Spracheingabe starten (unterbricht das Vorlesen, damit das Mikrofon es nicht aufnimmt)."""
    stop_speaking()
    _require(_speech_input(), "Spracheingabe").start()


def stop_recording() -> str:
    """Spracheingabe beenden; gibt den erkannten Text zurück (leer, wenn nichts erkannt wurde)."""
    return _require(_speech_input(), "Spracheingabe").stop()


def cancel_recording() -> None:
    """Spracheingabe verwerfen."""
    if (speech_input := _speech_input()) is not None:
        speech_input.cancel()


def speak(text: str) -> None:
    """Text vorlesen; kehrt sofort zurück."""
    _require(_speech_output(), "Sprachausgabe").speak(text)


def stop_speaking() -> None:
    """Vorlesen abbrechen."""
    if (speech_output := _speech_output()) is not None:
        speech_output.stop()


def open_link(url: str) -> None:
    """Link aus einer Antwort im Standardbrowser öffnen (nur http, https und mailto)."""
    if not url.lower().startswith(("http://", "https://", "mailto:")):
        raise ValueError(f"Diesen Link öffne ich nicht: {url}")
    webbrowser.open(url)


def enlarge_popup(enlarged: bool) -> bool:
    """Popup-Fenster vergrößern oder auf Normalgröße zurücksetzen. Gibt den neuen Zustand zurück."""
    enlarged = bool(enlarged)
    events.publish(POPUP_ENLARGED, enlarged)
    return enlarged


def proactive_message(occasion: str = proactive.DEMO) -> dict[str, Any]:
    """EVE meldet sich von sich aus (Anlass aus backend/proactive.py, z. B. "demo").

    Die Meldung erscheint als Push im Chat und als Windows-Benachrichtigung und wird
    vorgelesen (config.PROACTIVE_SPEAK). Gibt die Chat-Nachricht zurück. Darf aus jedem
    Thread aufgerufen werden; dauert so lange, wie das Sprachmodell braucht.
    """
    return _deliver_proactive(proactive.occasion(occasion), speak=config.PROACTIVE_SPEAK)


def _deliver_proactive(occasion: proactive.Occasion, formulate: bool = True, speak: bool = True,
                       display: str | None = None) -> dict[str, Any]:
    """Meldung formulieren (oder fester Text), zeigen und ggf. vorlesen. Aus jedem Thread aufrufbar."""
    with _assistant_lock:
        reply = proactive.compose(_assistant() if formulate else None, occasion)
    message = proactive.announce(present(reply), occasion, events, display)
    if speak and (speech_output := _speech_output()) is not None:
        try:
            speech_output.speak(reply.text)
        except Exception:  # noqa: BLE001  # Meldung ist schon da - Vorlesen ist Zugabe
            log.exception("Proaktive Meldung konnte nicht vorgelesen werden")
    return message


def _watch_tool(name: str, arguments: dict[str, Any]) -> ToolResult:
    """Internes Werkzeug für den Wächter; Fehler kommen als Ergebnis zurück, nie als Ausnahme."""
    with _assistant_lock:   # MCP-Clients teilt der Assistent - nicht gleichzeitig benutzen
        tools = getattr(_assistant(), "tools", None)
        if tools is None:
            return ToolResult("Dieser Assistent hat keine Werkzeuge", is_error=True)
        try:
            return tools.call_tool(name, arguments)
        except Exception as error:  # noqa: BLE001  # z. B. MCP-Server gerade nicht erreichbar
            return ToolResult(str(error), is_error=True)


def _consult_model(prompt: str) -> str | None:
    """Einmalige Frage ans Sprachmodell, ohne Verlauf und Werkzeuge; None, wenn es nicht antwortet."""
    with _assistant_lock:
        assistant = _assistant()
        return assistant.consult(prompt) if isinstance(assistant, ConsultingAssistant) else None


@cache
def _proactive_settings() -> ProactiveSettings:
    return ProactiveSettings(default_store())


@cache
def _proactive_watcher() -> ProactiveWatcher:
    """Der eine Wächter der App; application.py startet ihn."""
    return ProactiveWatcher(_proactive_settings(), JsonPreferenceStore(config.PROACTIVE_STATE_FILE), _watch_tool,
                            _consult_model, _deliver_proactive)


@cache
def _settings() -> AssistantSettings:
    """Einstellungen auf demselben Store wie der Assistent (preferences.default_store)."""
    return AssistantSettings(default_store())


def _available_tools() -> list[tuple[str, str]]:
    """Werkzeuge des Assistenten als (Name, Beschreibung); leer ohne Sprachmodell oder wenn keine da sind."""
    tools = getattr(_assistant(), "tools", None)
    if tools is None:
        return []
    try:
        with _assistant_lock:   # MCP-Clients teilt der Assistent - nicht gleichzeitig benutzen
            return [(spec.name, spec.description) for spec in tools.list_tools() if not is_internal_tool(spec.name)]
    except Exception:  # noqa: BLE001  # Einstellungen sollen sich trotzdem öffnen lassen
        log.exception("Werkzeuge für die Einstellungen nicht abrufbar")
        return []


def get_settings() -> dict[str, Any]:
    """Formular der Einstellungen (⚙ im Popup), siehe backend/assistant/settings.py:
    {"answer": {"fields": [...], "values": {...}},
     "tools": [{"id", "title", "description", "tools", "available", "fields", "values"}, ...],
     "proactive": [gleicher Aufbau wie "tools", siehe backend/proactive_settings.py]}
    fields: [{"key", "label", "kind": "choice"|"multi"|"bool"|"number"|"text"|"time", "default", "help",
              "choices"?: [{"value", "label"}], "minimum"?, "maximum"?}]"""
    return {**_settings().form(_available_tools()), "proactive": _proactive_settings().form()}


def save_settings(changes: dict[str, Any]) -> dict[str, Any]:
    """Einstellungen speichern: {"answer": {key: value}, "tools": {group_id: {key: value}},
    "proactive": {bereich: {key: value}}} - alles optional, nur geänderte Werte nötig. Ungültige
    Werte: ValueError, dann wird nichts gespeichert. Gilt ab der nächsten Nachricht bzw. Prüfung.
    Gibt das aktualisierte Formular zurück."""
    proactive_values = _proactive_settings().validated(changes.get("proactive"))
    _settings().save(changes.get("answer"), changes.get("tools"))
    _proactive_settings().store_validated(proactive_values)
    return get_settings()


def reset_settings() -> dict[str, Any]:
    """Alle Einstellungen auf die Standardwerte. Gibt das Formular zurück."""
    _settings().reset()
    _proactive_settings().reset()
    return get_settings()


def _prepare_assistant() -> None:
    # Unter dem Lock: Eine proaktive Meldung darf den Assistenten nicht gleichzeitig ein zweites Mal
    # erzeugen. Andere Aufrufer gibt es so früh nicht, das Frontend wartet auf den Ladebildschirm.
    with _assistant_lock:
        _assistant()
    _available_tools()   # startet die MCP-Server


def _load_model() -> None:
    assistant = _assistant()
    if isinstance(assistant, ModelPreloading):
        assistant.preload_model()


@cache
def _startup() -> Startup:
    return Startup([Step("Einstellungen werden gelesen", lambda: _settings().answer_values()),
                    Step("Assistent und Werkzeuge starten", _prepare_assistant),
                    Step("Sprachmodell wird geladen", _load_model, skippable=True)],
                   events)


def loading_status() -> dict[str, Any]:
    """Stand des Hochfahrens fürs Frontend, siehe backend/startup.py. Der erste Aufruf startet es."""
    return _startup().start()


def _require(component: Any, name: str) -> Any:
    if component is None:
        raise RuntimeError(f"{name} nicht verfügbar - Pakete aus requirements.txt installiert?")
    return component
