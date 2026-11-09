"""Wird von pytest vor allen Testmodulen geladen.

Die Tests laufen mit dem CommandAssistant: Sie sollen nicht von einem laufenden
Ollama abhängen. Der OllamaAssistant wird in tests/assistant/ mit Attrappen getestet.
Außerdem wird onnxruntime vor PyQt5 geladen, wie in main.py (siehe backend/speech.py).
"""
import os

os.environ["PDA_ASSISTANT_BACKEND"] = "commands"   # vor dem ersten Import von backend.config
os.environ["PDA_STARTUP_OPEN_POPUP"] = "0"         # Tests öffnen das Popup selbst

from backend.speech import load_before_qt  # noqa: E402

load_before_qt()
