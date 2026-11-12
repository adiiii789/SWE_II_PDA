"""Wechselt zwischen lokalem Ollama, Gemini und Claude (Abo) mit getrennten Verläufen."""
from __future__ import annotations

from backend.assistant.base import AssistantReply
from backend.assistant.claude_code_assistant import ClaudeCodeAssistant
from backend.assistant.commands import COMMANDS
from backend.assistant.gemini_assistant import GeminiAssistant
from backend.assistant.model_assistant import (PROVIDER_PREFERENCE, model_help_reply, model_list_reply,
                                               model_select_reply)
from backend.assistant.ollama_assistant import OllamaAssistant
from backend.preferences import PreferenceStore


class ModelPicker:
    def __init__(self, gemini: GeminiAssistant, ollama: OllamaAssistant, preferences: PreferenceStore,
                 claude: ClaudeCodeAssistant | None = None):
        self._assistants = {"gemini": gemini, "ollama": ollama, **({"claude": claude} if claude else {})}
        saved = preferences.get(PROVIDER_PREFERENCE)
        self._provider = saved if saved in self._assistants else "gemini"
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
                "modelle": f"Zeigt {self._provider_names()}",
                "modell <name>": "Wechselt das Modell, optional mit Präfix " + " oder ".join(
                    f"{provider}/" for provider in self._assistants),
            })
        if command == "modelle":
            hint = "Ollama läuft lokal. Gemini verarbeitet Anfragen in der Google-Cloud."
            if "claude" in self._assistants:
                hint += " Claude läuft über dein Claude-Abo bei Anthropic."
            return model_list_reply(self, hint)
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
            provider = next((key for key in ("gemini", "claude")
                             if key in self._assistants and name in self._assistants[key].model.selectable()),
                            "ollama")
        self._assistants[provider].select_model(model_name)
        if provider != self._provider:
            self._preferences.set(PROVIDER_PREFERENCE, provider)
            self._provider = provider

    def _provider_names(self) -> str:
        names = {"ollama": "lokale Ollama-", "gemini": "Gemini-", "claude": "Claude-"}
        labels = [names[provider] for provider in self._assistants]
        return ", ".join(labels[:-1]) + " und " + labels[-1] + "Modelle"
