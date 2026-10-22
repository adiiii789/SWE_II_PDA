"""Schnittstelle zwischen Chat (Frontend) und Assistent.

Jeder Assistent - der heutige CommandAssistant ebenso wie ein späterer
Ollama/MCP-Assistent - implementiert das Protokoll Assistant.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from backend.assistant.tools import Attachment
from backend.views import View


@dataclass(frozen=True)
class AssistantReply:
    text: str
    view: View | None = None   # TemplateView oder HtmlView; None = aktuelle Ansicht beibehalten
    attachments: tuple[Attachment, ...] = ()   # Dateien im Chat, z. B. Mail-Anhänge (backend/attachments.py)


@runtime_checkable
class Assistant(Protocol):
    def reply(self, message: str) -> AssistantReply:
        """Antwort auf eine Chat-Nachricht des Nutzers."""
        ...


@runtime_checkable
class ModelSelection(Protocol):
    """Optional: Assistenten mit Sprachmodell, deren Modell man im Popup wählen kann."""

    def available_models(self) -> list[dict]:
        """Wählbare Modelle: [{"name": str, "tools": bool, "cloud": bool}, ...]"""
        ...

    def current_model(self) -> str:
        ...

    def select_model(self, name: str) -> None:
        ...
