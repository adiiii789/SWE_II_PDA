"""Wird von pytest vor allen Testmodulen geladen.

Die Tests laufen mit dem CommandAssistant: Sie sollen nicht von einem laufenden
Ollama abhängen. Der OllamaAssistant wird in tests/assistant/ mit Attrappen getestet.
"""
import os

os.environ["PDA_ASSISTANT_BACKEND"] = "commands"
