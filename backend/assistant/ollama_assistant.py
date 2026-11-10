"""Modellwahl und gespeicherte Auswahl für lokales Ollama."""
from __future__ import annotations

from backend.assistant.model_assistant import ModelAssistant
from backend.assistant.ollama import OllamaError, OllamaModel


class OllamaAssistant(ModelAssistant):
    model: OllamaModel
    provider = "Ollama"
    model_preference = "ollama_model"
    model_commands = {
        "modelle": "Zeigt lokal installierte Ollama-Modelle",
        "modell <name>": "Wählt ein installiertes Modell",
    }
    model_hint = "Ollama führt die hier gelisteten Modelle auf diesem Rechner aus."
    no_model_hint = "Installiere ein lokales Ollama-Modell, damit EVE es verwenden kann."
    unknown_model_message = "{name!r} ist kein installiertes lokales Ollama-Modell"

    def available_models(self) -> list[dict]:
        try:
            return super().available_models()
        except OllamaError:
            return []

    def current_model(self) -> str:
        try:
            return super().current_model()
        except OllamaError:
            return ""

    def _ensure_model(self) -> bool:
        if not self.model.name:
            saved = self.preferences.get(self.model_preference)
            if isinstance(saved, str) and saved:
                self.model.name = saved
            else:
                self.model.name = next(iter(self.model.selectable()), "")
        return bool(self.model.name)
