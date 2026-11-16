"""Wird von pytest vor allen Testmodulen geladen.

Die Tests laufen mit dem CommandAssistant: Sie sollen nicht von Gemini abhängen.
Der GeminiAssistant wird in tests/assistant/ mit Attrappen getestet.
Außerdem wird onnxruntime vor PyQt5 geladen, wie in main.py (siehe backend/speech.py).
"""
import os
import tempfile
from pathlib import Path

os.environ["PDA_ASSISTANT_BACKEND"] = "commands"   # vor dem ersten Import von backend.config
os.environ["PDA_PROACTIVE_WATCH"] = "0"            # kein Wächter, der in Tests echte Postfächer abfragt
os.environ["PDA_STARTUP_OPEN_POPUP"] = "0"         # Tests öffnen das Popup selbst

# Keine echten Dienste und Keys in den Tests: eine eigene, leere .env statt der im Projektordner
# (vor dem ersten Import von backend.config). Ohne Keys plant der Reise-Assistent nichts (der Befehl
# "reise" meldet dann nur, dass etwas fehlt). Leere Umgebungsvariablen zählen nicht (backend/api_keys.py).
_SANDBOX = Path(tempfile.mkdtemp(prefix="pda-tests-"))
os.environ["PDA_ENV_FILE"] = str(_SANDBOX / ".env")
# Auch der App-Datenordner (Präferenzen, frühere Key-Dateien, Kacheln …) ist ein eigener: Sonst
# übernähme z. B. der Start von Application in tests/desktop echte Key-Dateien in die Test-.env.
os.environ["PDA_APP_DATA_DIR"] = str(_SANDBOX / "appdata")
os.environ["PDA_LEGACY_MCP_ENV_FILE"] = str(_SANDBOX / "mcp_servers.env")   # nie die echte mcp_servers/.env
for key in ("GEMINI_API_KEY", "PDA_ORS_KEY", "PDA_DB_CLIENT_ID", "PDA_DB_API_KEY", "PDA_TANKERKOENIG_KEY",
            "PDA_ALPHAVANTAGE_KEY", "PDA_SMTP_PASSWORD", "PDA_IMAP_PASSWORD"):
    os.environ.pop(key, None)

from backend.speech import load_before_qt  # noqa: E402

load_before_qt()
