"""Anzeige oben aktuell halten (Kalender, Aufgaben, Mails - backend/business_views.py).

Die Anzeige entsteht aus Abfragen wie list_tasks oder list_calendar_events. LiveView merkt sich diese
Aufrufe samt Argumenten. Ändert danach ein Werkzeug derselben Bereiche etwas (update_task, Termin
verschieben, Mail lesen oder löschen ...), laufen die Abfragen noch einmal und die Anzeige zeigt den
neuen Stand - ohne dass das Sprachmodell erneut auflisten muss. Ohne Sprachmodell geht das auch
(refresh), z. B. wenn das Popup wieder in den Vordergrund kommt.

Eine Instanz teilen sich alle Anbieter (Gemini, Ollama, Claude), damit ein Modellwechsel die Anzeige
nicht vergisst.
"""
from __future__ import annotations

import datetime
import logging
from collections.abc import Sequence

from backend import business_views
from backend.assistant.llm import ToolCall
from backend.assistant.settings import AssistantSettings
from backend.assistant.tools import ToolProvider, ToolResult
from backend.views import TemplateView

log = logging.getLogger(__name__)

ToolLog = Sequence[tuple[ToolCall, ToolResult]]


class LiveView:
    def __init__(self) -> None:
        self.calls: list[ToolCall] = []   # Abfragen hinter der aktuellen Anzeige

    def clear(self) -> None:
        self.calls = []

    def after_round(self, tool_log: ToolLog, tools: ToolProvider, settings: AssistantSettings,
                    now: datetime.datetime) -> TemplateView | None:
        """Anzeige nach einer Antwort: neue Abfragen zeigen ihre Daten; kam danach (oder ohne neue
        Abfrage) eine Änderung, werden die gemerkten Abfragen neu ausgeführt. None = Anzeige bleibt."""
        shown = [index for index, (call, result) in enumerate(tool_log) if _is_query(call, result, settings)]
        changed = [index for index, (call, result) in enumerate(tool_log) if _is_change(call, result, settings)]
        if shown:
            self.calls = _unique(tool_log[index][0] for index in shown)
            if not changed or changed[-1] < shown[-1]:   # Abfrage zeigt schon den neuesten Stand
                return _view([tool_log[index][1].data for index in shown], now)
        if changed and self.calls:
            return self.refresh(tools, settings, now)
        return None

    def refresh(self, tools: ToolProvider, settings: AssistantSettings,
                now: datetime.datetime) -> TemplateView | None:
        """Gemerkte Abfragen neu ausführen. None, wenn es keine gibt oder keine gelingt."""
        data = []
        for call in self.calls:
            if not settings.tool_enabled(call.name) or not settings.view_shown(call.name):
                continue
            try:
                result = tools.call_tool(call.name, call.arguments)
            except Exception as error:   # Netz weg o. ä.: dann eben die bisherige Anzeige
                log.warning("Anzeige nicht aktualisiert, %s fehlgeschlagen: %s", call.name, error)
                continue
            if not result.is_error and result.data:
                data.append(result.data)
        return _view(data, now) if data else None


def _is_query(call: ToolCall, result: ToolResult, settings: AssistantSettings) -> bool:
    return not result.is_error and bool(result.data) and settings.view_shown(call.name)


def _is_change(call: ToolCall, result: ToolResult, settings: AssistantSettings) -> bool:
    """Erfolgreicher Aufruf aus einem angezeigten Bereich, der selbst nichts auflistet (ändert also etwas
    oder markiert z. B. eine Mail als gelesen). Rückfragen vor riskanten Aufrufen filtert der Assistent
    vorher heraus (model_assistant.py)."""
    return not result.is_error and not result.data and settings.view_shown(call.name)


def _unique(calls) -> list[ToolCall]:
    seen, unique = set(), []
    for call in calls:
        key = (call.name, repr(sorted(call.arguments.items())))
        if key not in seen:
            seen.add(key)
            unique.append(ToolCall(call.name, dict(call.arguments), call.id))
    return unique


def _view(data: list, now: datetime.datetime) -> TemplateView | None:
    parts = business_views.components(data, now)
    return TemplateView("dashboard", {"components": parts}) if parts else None
