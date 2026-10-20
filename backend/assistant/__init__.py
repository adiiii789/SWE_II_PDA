"""Assistent hinter dem Chat.

Aufbau:
  base.py              Assistant-Protokoll + AssistantReply (Ansichten: backend/views.py)
  commands.py          CommandAssistant - feste Befehle, ohne Sprachmodell
  llm.py               LanguageModel-Protokoll
  ollama.py            OllamaModel - LanguageModel über ein lokales Ollama
  ollama_assistant.py  OllamaAssistant - Sprachmodell + Werkzeuge (Tool-Calling)
  tools.py             ToolProvider-Protokoll (Integrationen, MCP) + CompositeToolProvider
  skills/              Fähigkeiten des Assistenten (morning, travel, organization)

Es gibt einen durchgehenden Assistenten. Welcher läuft, legt
config.ASSISTANT_BACKEND fest ("ollama" oder "commands", siehe _BACKENDS).
"""
from __future__ import annotations

from collections.abc import Callable

from backend import config
from backend.assistant.base import Assistant, AssistantReply, ModelSelection
from backend.assistant.commands import CommandAssistant


def _ollama_assistant() -> Assistant:
    # Erst hier importieren: Der CommandAssistant braucht nichts davon.
    from backend.assistant.ollama import OllamaClient, OllamaModel
    from backend.assistant.ollama_assistant import OllamaAssistant
    from backend.assistant.skills import SKILLS
    from backend.assistant.tools import CompositeToolProvider
    from backend.integrations.mcp_client import load_mcp_servers
    from backend.preferences import app_preferences

    model = OllamaModel(OllamaClient(config.OLLAMA_URL, config.OLLAMA_TIMEOUT_S),
                        config.OLLAMA_MODEL, config.OLLAMA_OPTIONS)
    mcp_servers = load_mcp_servers(config.MCP_SERVERS_FILE, config.ROOT_DIR)
    tools = CompositeToolProvider([*mcp_servers, *(skill.tools for skill in SKILLS)])
    instructions = "\n\n".join(skill.instructions for skill in SKILLS)
    return OllamaAssistant(model, tools, app_preferences(), instructions,
                           config.ASSISTANT_MAX_TOOL_ROUNDS, config.ASSISTANT_MAX_HISTORY)


_BACKENDS: dict[str, Callable[[], Assistant]] = {
    "commands": CommandAssistant,
    "ollama": _ollama_assistant,
}


def create_assistant(backend: str = config.ASSISTANT_BACKEND) -> Assistant:
    try:
        factory = _BACKENDS[backend]
    except KeyError:
        raise ValueError(f"Unbekanntes Assistant-Backend: {backend!r} (verfügbar: {sorted(_BACKENDS)})") from None
    return factory()


__all__ = ["Assistant", "AssistantReply", "ModelSelection", "create_assistant"]
