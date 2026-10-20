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
    """Wählbare Sprachmodelle: {"models": [{"name", "tools"}], "current": str | None}.
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
