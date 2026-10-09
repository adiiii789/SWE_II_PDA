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

from backend.assistant import Assistant, create_assistant
from backend.presenter import present, renderer
from backend.views import START_VIEW, view_from_dict


@cache
def _assistant() -> Assistant:
    """Ein Assistent für die ganze Laufzeit (behält später z. B. den Chat-Verlauf)."""
    return create_assistant()


def chat(message: str) -> dict[str, Any]:
    """Antwort des Assistenten: {"text": str, "html": str | None} (siehe backend/presenter.py)."""
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
