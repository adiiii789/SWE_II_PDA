"""Assistent hinter dem Chat.

Aufbau:
  base.py              Assistant-Protokoll + AssistantReply (Ansichten: backend/views.py)
  commands.py          CommandAssistant - feste Befehle, ohne Sprachmodell
  llm.py               LanguageModel-Protokoll
  model_assistant.py   Gemeinsamer Verlauf und Werkzeugaufrufe
  gemini.py            GeminiModel - LanguageModel über die Gemini API
  ollama.py            OllamaModel - LanguageModel über ein lokales Ollama (auch Cloud-Modelle)
  tools.py             ToolProvider-Protokoll (Integrationen, MCP) + CompositeToolProvider
  skills/              Fähigkeiten des Assistenten (morning, travel, organization)

Es gibt einen durchgehenden Assistenten. Welcher läuft, legt
config.ASSISTANT_BACKEND fest ("gemini", "ollama" oder "commands").
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from backend import config
from backend.assistant.base import Assistant, AssistantReply, ModelSelection, ProactiveAssistant
from backend.assistant.commands import CommandAssistant

if TYPE_CHECKING:
    from backend.assistant.llm import SelectableLanguageModel
    from backend.assistant.model_assistant import ModelAssistant


def _ollama_assistant() -> Assistant:
    # Erst hier importieren: Der CommandAssistant braucht nichts davon.
    from backend.assistant.ollama import OllamaClient, OllamaModel
    from backend.assistant.ollama_assistant import OllamaAssistant

    catalog = (OllamaClient(config.OLLAMA_CLOUD_URL, config.OLLAMA_CLOUD_CATALOG_TIMEOUT_S,
                            "Ohne Internet gibt es nur lokale Modelle.")
               if config.OLLAMA_CLOUD or config.OLLAMA_CLOUD_ONLY else None)
    model = OllamaModel(OllamaClient(config.OLLAMA_URL, config.OLLAMA_TIMEOUT_S),
                        config.OLLAMA_MODEL, config.OLLAMA_OPTIONS, catalog, cloud_only=config.OLLAMA_CLOUD_ONLY)
    return _with_tools(OllamaAssistant, model)


def _gemini_assistant() -> Assistant:
    from backend.assistant.gemini import GeminiModel
    from backend.assistant.gemini_assistant import GeminiAssistant

    model = GeminiModel(config.GEMINI_MODEL, config.GEMINI_KEY_FILE, config.GEMINI_TIMEOUT_S)
    return _with_tools(GeminiAssistant, model)


def _with_tools(assistant: type[ModelAssistant], model: SelectableLanguageModel) -> Assistant:
    from backend.assistant.skills import SKILLS
    from backend.assistant.tools import CompositeToolProvider
    from backend.integrations.mcp_client import load_mcp_servers
    from backend.preferences import default_store

    mcp_servers = load_mcp_servers(config.MCP_SERVERS_FILE, config.ROOT_DIR)
    tools = CompositeToolProvider([*mcp_servers, *(skill.tools for skill in SKILLS)])
    instructions = "\n\n".join(skill.instructions for skill in SKILLS)
    return assistant(model, tools, default_store(), instructions,
                     config.ASSISTANT_MAX_TOOL_ROUNDS, config.ASSISTANT_MAX_HISTORY)


_BACKENDS: dict[str, Callable[[], Assistant]] = {
    "commands": CommandAssistant,
    "gemini": _gemini_assistant,
    "ollama": _ollama_assistant,
}


def create_assistant(backend: str = config.ASSISTANT_BACKEND) -> Assistant:
    try:
        factory = _BACKENDS[backend]
    except KeyError:
        raise ValueError(f"Unbekanntes Assistant-Backend: {backend!r} (verfügbar: {sorted(_BACKENDS)})") from None
    return factory()


__all__ = ["Assistant", "AssistantReply", "ModelSelection", "ProactiveAssistant", "create_assistant"]
