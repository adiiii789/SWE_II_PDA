"""Gemini-Modellwahl und getrennte Speicherung der gewählten Variante."""
from __future__ import annotations

from backend.assistant.gemini import MODELS, GeminiModel
from backend.assistant.model_assistant import ModelAssistant, PROACTIVE_TRIGGER as PROACTIVE_TRIGGER

MODEL_PREFERENCE = "gemini_model"


class GeminiAssistant(ModelAssistant):
    model: GeminiModel
    provider = "Gemini"
    model_preference = MODEL_PREFERENCE
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
            self.model.name = (saved if isinstance(saved, str) and saved in self.model.selectable()
                               else self.model.default_name)
        return True
