"""Funktionen für das Frontend.

Jede Funktion in dieser Datei ist im Frontend (frontend/*.js) unter demselben
Namen aufrufbar:  result = await name(arg1, arg2);
Funktionen mit "_" am Anfang bleiben privat.
Argumente und Rückgabewerte müssen JSON-tauglich sein (str, int, list, dict ...).
Aufrufe laufen in einem Hintergrund-Thread - auch langsame Funktionen frieren
das Popup nicht ein.
"""
from __future__ import annotations

from functools import cache
from typing import Any

from backend.assistant import Assistant, ModelSelection, create_assistant
from backend.presenter import attachment_store, present, renderer
from backend.speech import SpeechInput, SpeechOutput, create_speech_input, create_speech_output
from backend.views import START_VIEW, view_from_dict


@cache
def _assistant() -> Assistant:
    """Ein Assistent für die ganze Laufzeit (behält später z. B. den Chat-Verlauf)."""
    return create_assistant()


def chat(message: str) -> dict[str, Any]:
    """Antwort des Assistenten: {"text", "html", "attachments"} (siehe backend/presenter.py)."""
    return present(_assistant().reply(message))


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
    return {"models": assistant.available_models(), "current": assistant.current_model()}


def select_model(name: str) -> str:
    """Sprachmodell wechseln (bleibt gespeichert). Gibt den Namen zurück."""
    assistant = _assistant()
    if not isinstance(assistant, ModelSelection):
        raise ValueError("Dieser Assistent nutzt kein Sprachmodell")
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


def _require(component: Any, name: str) -> Any:
    if component is None:
        raise RuntimeError(f"{name} nicht verfügbar - Pakete aus requirements.txt installiert?")
    return component
