"""Modellauswahl für den optionalen Ollama-Betrieb."""
from __future__ import annotations

from backend.assistant.model_assistant import ModelAssistant, PROACTIVE_TRIGGER as PROACTIVE_TRIGGER
from backend.assistant.ollama import OllamaModel, cloud_name

MODEL_PREFERENCE = "ollama_model"
MODEL_COMMANDS = {
    "modelle": "Zeigt lokale und Cloud-Sprachmodelle",
    "modell <name>": "Wechselt das Sprachmodell, z. B. modell gemma4:31b-cloud",
}
CLOUD_HINT = ("Cloud-Modelle laufen auf ollama.com statt auf deinem PC. Dafür einmal im Terminal "
              "'ollama signin' ausführen. Im Free-Plan sind nur einige Modelle enthalten, mit einem "
              "Nutzungskontingent.")


class OllamaAssistant(ModelAssistant):
    model: OllamaModel
    provider = "Ollama"
    model_preference = MODEL_PREFERENCE
    model_commands = MODEL_COMMANDS
    model_hint = CLOUD_HINT
    no_model_hint = ("In Ollama ist noch kein Modell installiert. Lade eins herunter, "
                     "z. B. mit: ollama pull llama3.2 - oder nutze ein Cloud-Modell "
                     "(Liste mit 'modelle'). " + CLOUD_HINT)
    unknown_model_message = "Modell {name!r} ist weder installiert noch in der Ollama-Cloud verfügbar"

    def _model_alias(self, name: str) -> str:
        selectable = self.model.selectable()
        alias = cloud_name(name)
        return alias if name not in selectable and alias in selectable else name

    def _ensure_model(self) -> bool:
        """Modell festlegen, falls noch keins gewählt ist: zuletzt gewähltes (auch Cloud),
        sonst erstes installiertes."""
        if self.model.name:
            return True
        installed = self.model.installed()
        saved = self.preferences.get(MODEL_PREFERENCE)
        if saved and (saved in installed or saved in {info.name for info in self.model.cloud_models()}):
            self.model.name = saved
        else:
            self.model.name = installed[0] if installed else ""
            if not self.model.name:
                cloud = self.model.cloud_models()
                preferred = next((info for info in cloud if info.name == "gemma4:31b-cloud"), None)
                fallback = next((info for info in cloud if info.supports_tools), None)
                self.model.name = (preferred or fallback).name if preferred or fallback else ""
        return bool(self.model.name)
