"""Schnittstelle zwischen Chat (Frontend) und Assistent.

Jeder Assistent - der heutige CommandAssistant ebenso wie ein späterer
Ollama/MCP-Assistent - implementiert das Protokoll Assistant.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from backend.views import View


@dataclass(frozen=True)
class AssistantReply:
    text: str
    view: View | None = None   # TemplateView oder HtmlView; None = aktuelle Ansicht beibehalten


@runtime_checkable
class Assistant(Protocol):
    def reply(self, message: str) -> AssistantReply:
        """Antwort auf eine Chat-Nachricht des Nutzers."""
        ...
