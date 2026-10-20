"""CommandAssistant: Assistent mit festen Befehlen (ohne Sprachmodell).

Die Befehle in COMMANDS gelten auch im OllamaAssistant: Eine Nachricht, die genau
einem Befehl entspricht, wird sofort beantwortet, ohne das Sprachmodell zu fragen.
"""
from __future__ import annotations

import datetime
import os
import platform
import sys
from collections.abc import Callable

from backend.assistant.base import AssistantReply
from backend.views import START_VIEW, TemplateView


# --- Befehle -----------------------------------------------------------------
def _help() -> AssistantReply:
    rows = [[name, description] for name, (description, _) in COMMANDS.items()]
    return AssistantReply(
        "Das sind meine Befehle:",
        TemplateView("default", {"title": "Befehle", "columns": ["Befehl", "Beschreibung"], "rows": rows}))


_WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")


def _time() -> AssistantReply:
    now = datetime.datetime.now()
    return AssistantReply(
        f"Es ist {now:%H:%M} Uhr.",
        TemplateView("default", {"title": f"{now:%H:%M:%S}", "text": f"{_WEEKDAYS[now.weekday()]}, {now:%d.%m.%Y}"}))


def _system() -> AssistantReply:
    rows = [
        ["Betriebssystem", f"{platform.system()} {platform.release()}"],
        ["Rechner", platform.node()],
        ["Prozessorkerne", str(os.cpu_count())],
        ["Python", sys.version.split()[0]],
    ]
    return AssistantReply(
        "Hier sind die Systeminfos.",
        TemplateView("default", {"title": "System", "columns": ["Eigenschaft", "Wert"], "rows": rows}))


def _start() -> AssistantReply:
    return AssistantReply("Startansicht.", START_VIEW)


def _new_conversation() -> AssistantReply:
    # Den Verlauf leert der OllamaAssistant, bevor er diesen Befehl ausführt.
    return AssistantReply("Neues Gespräch begonnen.", START_VIEW)


COMMANDS: dict[str, tuple[str, Callable[[], AssistantReply]]] = {
    "hilfe": ("Zeigt alle Befehle", _help),
    "uhrzeit": ("Zeigt Uhrzeit und Datum", _time),
    "system": ("Zeigt Systeminformationen", _system),
    "start": ("Zurück zur Startansicht", _start),
    "neu": ("Neues Gespräch (KI vergisst den Verlauf)", _new_conversation),
}


class CommandAssistant:
    def reply(self, message: str) -> AssistantReply:
        command = message.strip().lower()
        if command in COMMANDS:
            _, handler = COMMANDS[command]
            return handler()
        return AssistantReply(f'Das verstehe ich noch nicht: "{message.strip()}". Schreib "hilfe".')
