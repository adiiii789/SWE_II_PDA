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
import threading
import webbrowser
from functools import cache
from typing import Any

from backend import config, proactive
from backend.assistant import Assistant, ModelSelection, create_assistant
from backend.assistant.settings import AssistantSettings
from backend.preferences import default_store
from backend.events import POPUP_ENLARGED, events
from backend.presenter import attachment_store, present, renderer
from backend.speech import SpeechInput, SpeechOutput, create_speech_input, create_speech_output
from backend.views import START_VIEW, view_from_dict

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


def list_models() -> dict[str, Any]:
    """Wählbare Sprachmodelle: {"models": [{"name", "tools", "cloud"}], "current": str | None}.
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
    chosen = proactive.occasion(occasion)
    with _assistant_lock:
        reply = proactive.compose(_assistant(), chosen)
    message = proactive.announce(present(reply), chosen, events)
    if config.PROACTIVE_SPEAK and (speech_output := _speech_output()) is not None:
        try:
            speech_output.speak(reply.text)
        except Exception:  # noqa: BLE001  # Meldung ist schon da - Vorlesen ist Zugabe
            log.exception("Proaktive Meldung konnte nicht vorgelesen werden")
    return message


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
            return [(spec.name, spec.description) for spec in tools.list_tools()]
    except Exception:  # noqa: BLE001  # Einstellungen sollen sich trotzdem öffnen lassen
        log.exception("Werkzeuge für die Einstellungen nicht abrufbar")
        return []


def get_settings() -> dict[str, Any]:
    """Formular der Einstellungen (⚙ im Popup), siehe backend/assistant/settings.py:
    {"answer": {"fields": [...], "values": {...}},
     "tools": [{"id", "title", "description", "tools", "available", "fields", "values"}, ...]}
    fields: [{"key", "label", "kind": "choice"|"multi"|"bool"|"number"|"text", "default", "help",
              "choices"?: [{"value", "label"}], "minimum"?, "maximum"?}]"""
    return _settings().form(_available_tools())


def save_settings(changes: dict[str, Any]) -> dict[str, Any]:
    """Einstellungen speichern: {"answer": {key: value}, "tools": {group_id: {key: value}}} - beides
    optional, nur geänderte Werte nötig. Ungültige Werte: ValueError, dann wird nichts gespeichert.
    Gilt ab der nächsten Nachricht. Gibt das aktualisierte Formular zurück."""
    _settings().save(changes.get("answer"), changes.get("tools"))
    return get_settings()


def reset_settings() -> dict[str, Any]:
    """Alle Einstellungen auf die Standardwerte. Gibt das Formular zurück."""
    _settings().reset()
    return get_settings()


def _require(component: Any, name: str) -> Any:
    if component is None:
        raise RuntimeError(f"{name} nicht verfügbar - Pakete aus requirements.txt installiert?")
    return component
