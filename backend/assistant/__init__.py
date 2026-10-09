"""Assistent hinter dem Chat.

Aufbau:
  base.py      Assistant-Protokoll + AssistantReply (Ansichten: backend/views.py)
  commands.py  CommandAssistant - heutiger Platzhalter mit festen Befehlen
  llm.py       LanguageModel-Protokoll (Anbindung für Ollama)
  tools.py     ToolProvider-Protokoll (Integrationen, MCP) + CompositeToolProvider
  skills/      Fähigkeiten des Assistenten (morning, travel, organization)

Es gibt einen durchgehenden Assistenten. Heute ist das der CommandAssistant,
später ein Assistent mit LanguageModel (Ollama), der die Werkzeuge aller
Fähigkeiten nutzt. Er wird unten in _BACKENDS eingetragen; welcher läuft, legt
config.ASSISTANT_BACKEND fest.
"""
from __future__ import annotations

from collections.abc import Callable

from backend import config
from backend.assistant.base import Assistant, AssistantReply
from backend.assistant.commands import CommandAssistant

_BACKENDS: dict[str, Callable[[], Assistant]] = {
    "commands": CommandAssistant,
}


def create_assistant(backend: str = config.ASSISTANT_BACKEND) -> Assistant:
    try:
        factory = _BACKENDS[backend]
    except KeyError:
        raise ValueError(f"Unbekanntes Assistant-Backend: {backend!r} (verfügbar: {sorted(_BACKENDS)})") from None
    return factory()


__all__ = ["Assistant", "AssistantReply", "create_assistant"]
