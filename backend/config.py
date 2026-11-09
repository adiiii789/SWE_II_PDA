"""Zentrale Konfiguration: Pfade, Namen und Darstellungswerte."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from backend.platform_paths import app_data_dir

# Im PyInstaller-Build liegen die Dateien im Entpack-Ordner (_MEIPASS).
ROOT_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
FRONTEND_DIR = ROOT_DIR / "frontend"
TEMPLATE_DIR = FRONTEND_DIR / "templates"   # Jinja2-Templates für das iframe

APP_NAME = "EVE"
APP_USER_MODEL_ID = "swe2.personaldigitalagent.1.0"
IS_MAC = sys.platform == "darwin"
TRAY_ICON = ROOT_DIR / "assets" / "tray-macos.svg" if IS_MAC else ROOT_DIR / "TrayIcon.ico"

# "gemini" (Google), "ollama" (optional) oder "commands" (nur feste Befehle).
# Siehe backend/assistant/__init__.py (_BACKENDS). Die Tests setzen "commands" (tests/conftest.py).
ASSISTANT_BACKEND = os.environ.get("PDA_ASSISTANT_BACKEND", "gemini")

GEMINI_MODEL = os.environ.get("PDA_GEMINI_MODEL", "").strip()
GEMINI_TIMEOUT_S = 120

# Ollama (backend/assistant/ollama.py)
OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("PDA_OLLAMA_MODEL", "")   # leer = zuletzt gewähltes bzw. erstes installiertes
OLLAMA_TIMEOUT_S = 300                # Laden eines großen Modells kann dauern
OLLAMA_OPTIONS: dict = {}             # z. B. {"temperature": 0.2, "num_ctx": 8192}
# Cloud-Modelle (z. B. "gemma4:31b-cloud") laufen über das lokale Ollama auf ollama.com,
# einmalig "ollama signin" nötig. Die Liste kommt von OLLAMA_CLOUD_URL; "0" blendet sie aus.
OLLAMA_CLOUD = os.environ.get("PDA_OLLAMA_CLOUD", "1") != "0"
OLLAMA_CLOUD_ONLY = os.environ.get("PDA_OLLAMA_CLOUD_ONLY", "1") != "0"
OLLAMA_CLOUD_URL = "https://ollama.com"
OLLAMA_CLOUD_CATALOG_TIMEOUT_S = 5
ASSISTANT_MAX_TOOL_ROUNDS = 5         # Werkzeug-Runden pro Nachricht, gegen Endlosschleifen
ASSISTANT_MAX_HISTORY = 30            # Nachrichten im Verlauf, die das Modell sieht

# MCP-Server, deren Werkzeuge der Assistent nutzen kann (backend/integrations/mcp_client.py)
MCP_SERVERS_FILE = ROOT_DIR / "mcp_servers.json"

# Präferenzen (backend/preferences.py) - außerhalb des Programmordners, damit sie Updates überstehen
APP_DATA_DIR = app_data_dir()
PREFERENCES_FILE = APP_DATA_DIR / "preferences.json"
GEMINI_KEY_FILE = APP_DATA_DIR / "gemini-api-key.txt"

# Dateien im Chat (backend/attachments.py). Nur Dateien in ATTACHMENT_DIR lassen sich öffnen;
# derselbe Ordner, in den mcp_servers/inbox.py Mail-Anhänge ablegt.
ATTACHMENT_DIR = Path(os.environ.get("PDA_ATTACHMENT_DIR") or APP_DATA_DIR / "attachments")
DOWNLOAD_DIR = Path.home() / "Downloads"   # Ziel von "Speichern"

# Sprache (backend/speech.py) - alles lokal; Modelle werden beim ersten Gebrauch hierhin geladen
SPEECH_DIR = APP_DATA_DIR / "speech"
SPEECH_LANGUAGE = os.environ.get("PDA_SPEECH_LANGUAGE", "de")         # leer = Whisper erkennt die Sprache
WHISPER_MODEL = os.environ.get("PDA_WHISPER_MODEL", "small")          # tiny, base, small, medium …
PIPER_VOICE = os.environ.get("PDA_PIPER_VOICE", "de_DE-pavoque-low")
MAC_VOICE = os.environ.get("PDA_MAC_VOICE", "")   # leer: installierte Stimme passend zur Sprache

# Proaktive Meldungen (backend/proactive.py): EVE meldet sich von sich aus.
# Test-Makro: globales Tastenkürzel, leer = aus. Auch über das Symbolmenü auslösbar.
PROACTIVE_HOTKEY = os.environ.get("PDA_PROACTIVE_HOTKEY", "Cmd+Alt+P" if IS_MAC else "Ctrl+Alt+P")
PROACTIVE_SPEAK = os.environ.get("PDA_PROACTIVE_SPEAK", "1") != "0"           # Meldung vorlesen
# Popup von selbst öffnen (wie ein Klick aufs Symbol); "0" = stattdessen Systembenachrichtigung
PROACTIVE_OPEN_POPUP = os.environ.get("PDA_PROACTIVE_OPEN_POPUP", "1") != "0"
PROACTIVE_NOTICE_MS = 8000            # Anzeigedauer der Benachrichtigung (Klick darauf öffnet das Popup)

POPUP_PAGE = FRONTEND_DIR / "popup.html"
POPUP_SIZE_RATIO = (0.3, 0.6)         # Anteil des Bildschirms (Breite, Höhe)
POPUP_ENLARGED_SIZE_RATIO = (0.55, 0.9)   # vergrößertes Popup (Knopf im Chat)
POPUP_BACKGROUND = "#f5f5f7"          # Grundfarbe vor dem Laden der gewählten Designpalette
POPUP_MARGIN_PX = 0
POPUP_SLIDE_IN_OFFSET_PX = 12
POPUP_ANIMATION_MS = 220
POPUP_CLOSE_ANIMATION_MS = 140
POPUP_CORNER_RADIUS_PX = 22
