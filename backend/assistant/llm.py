"""Schnittstelle zu einem Sprachmodell (geplant: Ollama).

Nur Datentypen und Protokoll - noch keine Implementierung. Die Typen folgen
dem Chat-Format, das Ollama (/api/chat) und andere Anbieter gemeinsam haben.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from backend.assistant.tools import ToolSpec

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class ToolCall:
    """Das Modell möchte ein Werkzeug mit diesen Argumenten aufrufen."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str
    tool_calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True)
class ModelResponse:
    message: ChatMessage

    @property
    def wants_tools(self) -> bool:
        return bool(self.message.tool_calls)


@runtime_checkable
class LanguageModel(Protocol):
    def chat(self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec] = ()) -> ModelResponse:
        """Nächste Antwort des Modells auf den bisherigen Verlauf."""
        ...
