"""Zentrale Konfiguration: Pfade, Namen und Darstellungswerte."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Im PyInstaller-Build liegen die Dateien im Entpack-Ordner (_MEIPASS).
ROOT_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
FRONTEND_DIR = ROOT_DIR / "frontend"
TEMPLATE_DIR = FRONTEND_DIR / "templates"   # Jinja2-Templates für das iframe

APP_NAME = "Personal Digital Agent"
APP_USER_MODEL_ID = "swe2.personaldigitalagent.1.0"
TRAY_ICON = ROOT_DIR / "TrayIcon.ico"

# "ollama" (lokales Sprachmodell + MCP-Werkzeuge) oder "commands" (feste Befehle, ohne KI).
# Siehe backend/assistant/__init__.py (_BACKENDS). Die Tests setzen "commands" (tests/conftest.py).
ASSISTANT_BACKEND = os.environ.get("PDA_ASSISTANT_BACKEND", "ollama")

# Ollama (backend/assistant/ollama.py)
OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("PDA_OLLAMA_MODEL", "")   # leer = zuletzt gewähltes bzw. erstes installiertes
OLLAMA_TIMEOUT_S = 300                # Laden eines großen Modells kann dauern
OLLAMA_OPTIONS: dict = {}             # z. B. {"temperature": 0.2, "num_ctx": 8192}
ASSISTANT_MAX_TOOL_ROUNDS = 5         # Werkzeug-Runden pro Nachricht, gegen Endlosschleifen
ASSISTANT_MAX_HISTORY = 30            # Nachrichten im Verlauf, die das Modell sieht

# MCP-Server, deren Werkzeuge der Assistent nutzen kann (backend/integrations/mcp_client.py)
MCP_SERVERS_FILE = ROOT_DIR / "mcp_servers.json"

# Präferenzen (backend/preferences.py) - außerhalb des Programmordners, damit sie Updates überstehen
APP_DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / "PersonalDigitalAgent"
PREFERENCES_FILE = APP_DATA_DIR / "preferences.json"

# Dateien im Chat (backend/attachments.py). Nur Dateien in ATTACHMENT_DIR lassen sich öffnen;
# derselbe Ordner, in den mcp_servers/inbox.py Mail-Anhänge ablegt.
ATTACHMENT_DIR = Path(os.environ.get("PDA_ATTACHMENT_DIR") or APP_DATA_DIR / "attachments")
DOWNLOAD_DIR = Path.home() / "Downloads"   # Ziel von "Speichern"

POPUP_PAGE = FRONTEND_DIR / "popup.html"
POPUP_SIZE_RATIO = (0.3, 0.6)         # Anteil des Bildschirms (Breite, Höhe)
POPUP_BACKGROUND = "#2E2E2E"          # identisch mit --background in frontend/theme.css
POPUP_MARGIN_PX = 8
POPUP_SLIDE_IN_OFFSET_PX = 50         # Start der Animation unterhalb der Endposition
POPUP_ANIMATION_MS = 500
