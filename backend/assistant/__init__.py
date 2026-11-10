"""Assistent hinter dem Chat.

Aufbau:
  base.py              Assistant-Protokoll + AssistantReply (Ansichten: backend/views.py)
  commands.py          CommandAssistant - feste Befehle, ohne Sprachmodell
  llm.py               LanguageModel-Protokoll
  gemini.py            GeminiModel - LanguageModel über die Google Gemini API
  ollama.py            OllamaModel - lokal installierte Modelle
  model_assistant.py   Gemeinsamer Verlauf und Werkzeugaufrufe für je einen Anbieter
  model_picker.py      Wechsel zwischen den Anbietern
  tools.py             ToolProvider-Protokoll (Integrationen, MCP) + CompositeToolProvider
  skills/              Fähigkeiten des Assistenten (morning, travel, organization)

Es gibt einen durchgehenden Assistenten. Welcher läuft, legt
config.ASSISTANT_BACKEND fest ("models", "gemini", "ollama" oder "commands").
"""
from __future__ import annotations

from collections.abc import Callable
from functools import partial

from backend import config
from backend.assistant.base import (Assistant, AssistantReply, ConsultingAssistant, ModelPreloading, ModelSelection,
                                    ProactiveAssistant)
from backend.assistant.commands import CommandAssistant


def _model_assistant(backend: str) -> Assistant:
    from backend.assistant.gemini import GeminiModel
    from backend.assistant.gemini_assistant import GeminiAssistant
    from backend.assistant.model_picker import ModelPicker
    from backend.assistant.ollama import OllamaClient, OllamaModel
    from backend.assistant.ollama_assistant import OllamaAssistant
    from backend.assistant.skills import SKILLS
    from backend.assistant.tools import CompositeToolProvider
    from backend.integrations.mcp_client import load_mcp_servers
    from backend.preferences import default_store

    mcp_servers = load_mcp_servers(config.MCP_SERVERS_FILE, config.ROOT_DIR)
    tools = CompositeToolProvider([*mcp_servers, *(skill.tools for skill in SKILLS)])
    instructions = "\n\n".join(skill.instructions for skill in SKILLS)
    preferences = default_store()
    args = (tools, preferences, instructions, config.ASSISTANT_MAX_TOOL_ROUNDS, config.ASSISTANT_MAX_HISTORY)
    gemini = GeminiAssistant(GeminiModel(config.GEMINI_MODEL, config.GEMINI_KEY_FILE, config.GEMINI_TIMEOUT_S),
                             *args)
    ollama = OllamaAssistant(OllamaModel(OllamaClient(config.OLLAMA_TIMEOUT_S, config.OLLAMA_CATALOG_TIMEOUT_S)),
                             *args)
    if backend == "models":
        return ModelPicker(gemini, ollama, preferences)
    return gemini if backend == "gemini" else ollama


_BACKENDS: dict[str, Callable[[], Assistant]] = {
    "commands": CommandAssistant,
    "models": partial(_model_assistant, "models"),
    "gemini": partial(_model_assistant, "gemini"),
    "ollama": partial(_model_assistant, "ollama"),
}


def create_assistant(backend: str = config.ASSISTANT_BACKEND) -> Assistant:
    try:
        factory = _BACKENDS[backend]
    except KeyError:
        raise ValueError(f"Unbekanntes Assistant-Backend: {backend!r} (verfügbar: {sorted(_BACKENDS)})") from None
    return factory()


__all__ = ["Assistant", "AssistantReply", "ConsultingAssistant", "ModelPreloading", "ModelSelection",
           "ProactiveAssistant", "create_assistant"]
