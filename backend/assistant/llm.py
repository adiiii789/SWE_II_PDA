"""Schnittstelle zu einem Sprachmodell.

Gemeinsame Datentypen und Protokolle für die Anbieter.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from backend.assistant.tools import ToolSpec

Role = Literal["system", "user", "assistant", "tool"]


class LanguageModelError(RuntimeError):
    """Ein Modell konnte die Anfrage nicht beantworten."""


@dataclass(frozen=True)
class ModelInfo:
    name: str
    supports_tools: bool
    cloud: bool = False


@dataclass(frozen=True)
class ToolCall:
    """Das Modell möchte ein Werkzeug mit diesen Argumenten aufrufen."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    id: str = ""


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    tool_name: str = ""   # nur bei role="tool": zu welchem Werkzeug das Ergebnis gehört
    tool_call_id: str = ""
    # Gemini benötigt die ursprünglichen Parts samt Signaturen in Folgeanfragen.
    provider_content: dict[str, Any] | None = field(default=None, repr=False, compare=False)


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


class SelectableLanguageModel(LanguageModel, Protocol):
    name: str

    def available_models(self) -> list[ModelInfo]: ...

    def selectable(self) -> list[str]: ...
