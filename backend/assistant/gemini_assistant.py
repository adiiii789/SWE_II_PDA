"""Gemini-Modellwahl und getrennte Speicherung der gewählten Variante."""
from __future__ import annotations

from dataclasses import replace

from backend.assistant.gemini import MODELS, GeminiModel
from backend.assistant.model_assistant import ModelAssistant


class GeminiAssistant(ModelAssistant):
    model: GeminiModel
    provider = "Gemini"
    model_preference = "gemini_model"
    model_commands = {
        "modelle": "Zeigt die Gemini-Sprachmodelle",
        "modell <name>": f"Wechselt das Sprachmodell, z. B. modell {MODELS[0]}",
    }
    model_hint = "Gemini verarbeitet Chatverlauf und verwendete Werkzeugergebnisse in der Google-Cloud."
    no_model_hint = "Wähle ein Gemini-Modell aus."
    unknown_model_message = "Gemini-Modell {name!r} steht nicht zur Auswahl"

    def _ensure_model(self) -> bool:
        if not self.model.name:
            saved = self.preferences.get(self.model_preference)
            self.model.name = saved if saved in self.model.selectable() else self.model.default_name
        return True

    def select_model(self, name: str) -> None:
        previous = self.current_model()
        super().select_model(name)
        if name != previous:
            # Signaturen gelten für das bisherige Modell. Den Chattext weiterverwenden.
            self.history = [replace(message, provider_content=None) for message in self.history
                            if message.role != "tool" and not message.tool_calls]
