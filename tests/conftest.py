"""Wird von pytest vor allen Testmodulen geladen.

Die Tests laufen mit dem CommandAssistant: Sie sollen nicht von Gemini abhängen.
Der GeminiAssistant wird in tests/assistant/ mit Attrappen getestet.
Außerdem wird onnxruntime vor PyQt5 geladen, wie in main.py (siehe backend/speech.py).
"""
import os

os.environ["PDA_ASSISTANT_BACKEND"] = "commands"   # vor dem ersten Import von backend.config
os.environ["PDA_PROACTIVE_WATCH"] = "0"            # kein Wächter, der in Tests echte Postfächer abfragt

from backend.speech import load_before_qt  # noqa: E402

load_before_qt()

# Keine echten Dienste in den Tests: Ohne Keys plant der Reise-Assistent nichts
# (der Befehl "reise" meldet dann nur, dass etwas fehlt).
for key in ("PDA_ORS_KEY", "PDA_DB_CLIENT_ID", "PDA_DB_API_KEY", "PDA_TANKERKOENIG_KEY"):
    os.environ[key] = ""
