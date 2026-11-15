"""Welches Werkzeug der Assistent gerade aufruft - fürs Popup ("denkt nach …" wird zu "Termine abrufen …").

ModelAssistant meldet jeden Aufruf zweimal an `on_tool` (backend/assistant/__init__.py hängt dort
events.publish(TOOL_ACTIVITY, ...) an):

    {"phase": "start", "tool": "list_tasks", "label": "Aufgaben abrufen", "group": "Google Tasks"}
    {"phase": "end", ..., "error": False}

Unbekannte Werkzeuge (z. B. von fremden MCP-Servern) bekommen ihren Namen als Bezeichnung.
"""
from __future__ import annotations

from typing import Any

TOOL_LABELS: dict[str, str] = {
    "list_emails": "Mails abrufen",
    "read_email": "Mail lesen",
    "read_attachment": "Anhang lesen",
    "send_email": "Mail senden",
    "reply_email": "Antwort senden",
    "save_email_draft": "Entwurf speichern",
    "organize_email": "Mails ordnen",
    "delete_email": "Mail löschen",
    "list_calendar_events": "Termine abrufen",
    "create_calendar_event": "Termin erstellen",
    "update_calendar_event": "Termin ändern",
    "delete_calendar_event": "Termin löschen",
    "find_free_time": "Freie Zeit suchen",
    "respond_to_calendar_invitation": "Einladung beantworten",
    "list_tasks": "Aufgaben abrufen",
    "create_task": "Aufgabe erstellen",
    "update_task": "Aufgabe ändern",
    "complete_task": "Aufgabe erledigen",
    "delete_task": "Aufgabe löschen",
    "move_task": "Aufgabe verschieben",
    "create_task_list": "Aufgabenliste anlegen",
    "get_current_time": "Uhrzeit abfragen",
    "calculate": "Rechnen",
}


def tool_label(name: str) -> str:
    return TOOL_LABELS.get(name) or name.replace("_", " ").strip().capitalize() or "Werkzeug"


def tool_activity(phase: str, name: str, group: str = "", error: bool = False) -> dict[str, Any]:
    activity: dict[str, Any] = {"phase": phase, "tool": name, "label": tool_label(name), "group": group}
    if phase == "end":
        activity["error"] = error
    return activity
