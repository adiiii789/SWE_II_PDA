"""Wechselt zwischen lokalem Ollama und Gemini mit getrennten Verläufen."""
from __future__ import annotations

from backend.assistant.base import AssistantReply
from backend.assistant.commands import COMMANDS
from backend.assistant.gemini_assistant import GeminiAssistant
from backend.assistant.model_assistant import (PROVIDER_PREFERENCE, model_help_reply, model_list_reply,
                                               model_select_reply)
from backend.assistant.ollama_assistant import OllamaAssistant
from backend.preferences import PreferenceStore


class ModelPicker:
    def __init__(self, gemini: GeminiAssistant, ollama: OllamaAssistant, preferences: PreferenceStore):
        self._assistants = {"gemini": gemini, "ollama": ollama}
        self._provider = "ollama" if preferences.get(PROVIDER_PREFERENCE) == "ollama" else "gemini"
        self._preferences = preferences
        self.tools = gemini.tools

    def reply(self, message: str) -> AssistantReply:
        command = message.strip().lower()
        if command == "neu":
            for assistant in self._assistants.values():
                assistant.new_conversation()
            return COMMANDS["neu"][1]()
        if command == "hilfe":
            return model_help_reply({
                "modelle": "Zeigt lokale Ollama- und Gemini-Modelle",
                "modell <name>": "Wechselt das Modell, optional mit Präfix ollama/ oder gemini/",
            })
        if command == "modelle":
            return model_list_reply(self, "Ollama läuft lokal. Gemini verarbeitet Anfragen in der Google-Cloud.")
        if command.startswith("modell "):
            return model_select_reply(self, message.strip()[len("modell "):].strip())
        return self._assistants[self._provider].reply(message)

    def announce(self, instruction: str) -> str | None:
        return self._assistants[self._provider].announce(instruction)

    def consult(self, prompt: str) -> str | None:
        return self._assistants[self._provider].consult(prompt)

    def available_models(self) -> list[dict]:
        return [{**model, "id": f"{provider}/{model['name']}"}
                for provider, assistant in self._assistants.items() for model in assistant.available_models()]

    def current_model(self) -> str:
        return f"{self._provider}/{self._assistants[self._provider].current_model()}"

    def select_model(self, name: str) -> None:
        provider, separator, model_name = name.partition("/")
        if not separator or provider not in self._assistants:
            model_name = name
            provider = "gemini" if name in self._assistants["gemini"].model.selectable() else "ollama"
        self._assistants[provider].select_model(model_name)
        if provider != self._provider:
            self._preferences.set(PROVIDER_PREFERENCE, provider)
            self._provider = provider
