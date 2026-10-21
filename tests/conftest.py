"""Wird von pytest vor allen Testmodulen geladen.

Die Tests laufen mit dem CommandAssistant: Sie sollen nicht von einem laufenden
Ollama abhängen. Der OllamaAssistant wird in tests/assistant/ mit Attrappen getestet.
"""
import os

os.environ["PDA_ASSISTANT_BACKEND"] = "commands"

# Keine echten Dienste in den Tests: Ohne Keys plant der Reise-Assistent nichts
# (der Befehl "reise" meldet dann nur, dass etwas fehlt).
for key in ("PDA_ORS_KEY", "PDA_DB_CLIENT_ID", "PDA_DB_API_KEY", "PDA_TANKERKOENIG_KEY"):
    os.environ[key] = ""
