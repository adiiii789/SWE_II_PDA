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


def read_env_file(path: Path) -> dict[str, str]:
    """KEY=VALUE pro Zeile; leere Zeilen und # Kommentare werden ignoriert.
    Gegenstück für die MCP-Server: mcp_servers/mailer.py (eigene Prozesse, importieren backend nicht)."""
    if not path.exists():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


# Keys und Zugangsdaten: Umgebungsvariablen oder die .env im Projektordner (Vorlage: .env.example).
# Umgebungsvariablen haben Vorrang. os.environ bleibt unverändert, damit die MCP-Server die .env
# selbst lesen - Änderungen an den Mail-Einstellungen wirken dort ohne Neustart.
ENV_FILE = ROOT_DIR / ".env"
_ENV = {**read_env_file(ENV_FILE), **os.environ}

# "models" (Ollama und Gemini), einzelner Anbieter oder "commands" (nur feste Befehle).
# Siehe backend/assistant/__init__.py (_BACKENDS). Die Tests setzen "commands" (tests/conftest.py).
ASSISTANT_BACKEND = _ENV.get("PDA_ASSISTANT_BACKEND", "models")

GEMINI_MODEL = _ENV.get("PDA_GEMINI_MODEL", "").strip()
GEMINI_TIMEOUT_S = 120
OLLAMA_TIMEOUT_S = 300
OLLAMA_CATALOG_TIMEOUT_S = 2

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
ATTACHMENT_DIR = Path(_ENV.get("PDA_ATTACHMENT_DIR") or APP_DATA_DIR / "attachments")
DOWNLOAD_DIR = Path.home() / "Downloads"   # Ziel von "Speichern"

# Reise-Assistent (backend/assistant/skills/travel/). Ohne Key fällt der jeweilige Teil weg;
# Einrichtung siehe README. Persönliche Werte (Zeitwert, Verbrauch …) stehen in den Präferenzen.
# credentials.json (OAuth-Client) und token.json - derselbe Ordner wie mcp_servers/google_calendar.py
GOOGLE_DIR = Path(_ENV.get("PDA_GOOGLE_DIR") or APP_DATA_DIR / "google")
ORS_KEY = _ENV.get("PDA_ORS_KEY", "")                      # openrouteservice: Adressen, Routen
DB_CLIENT_ID = _ENV.get("PDA_DB_CLIENT_ID", "")            # DB API Marketplace (Timetables)
DB_API_KEY = _ENV.get("PDA_DB_API_KEY", "")
TANKERKOENIG_KEY = _ENV.get("PDA_TANKERKOENIG_KEY", "")    # Spritpreise
HTTP_TIMEOUT_S = 20
TRAVEL_REMINDER_MINUTES = 15          # Erinnerung so lange vor der empfohlenen Abfahrt
TRAVEL_CHECK_INTERVAL_S = 300         # so oft schaut die Erinnerung in den Kalender

# Sprache (backend/speech.py) - alles lokal; Modelle werden beim ersten Gebrauch hierhin geladen
SPEECH_DIR = APP_DATA_DIR / "speech"
SPEECH_LANGUAGE = _ENV.get("PDA_SPEECH_LANGUAGE", "de")         # leer = Whisper erkennt die Sprache
WHISPER_MODEL = _ENV.get("PDA_WHISPER_MODEL", "small")          # tiny, base, small, medium …
PIPER_VOICE = _ENV.get("PDA_PIPER_VOICE", "de_DE-pavoque-low")
MAC_VOICE = _ENV.get("PDA_MAC_VOICE", "")   # leer: installierte Stimme passend zur Sprache

# Proaktive Meldungen (backend/proactive.py): EVE meldet sich von sich aus.
# Test-Makro: globales Tastenkürzel, leer = aus. Auch über das Symbolmenü auslösbar.
PROACTIVE_HOTKEY = _ENV.get("PDA_PROACTIVE_HOTKEY", "Cmd+Alt+P" if IS_MAC else "Ctrl+Alt+P")
PROACTIVE_SPEAK = _ENV.get("PDA_PROACTIVE_SPEAK", "1") != "0"           # Meldung vorlesen
# Popup von selbst öffnen (wie ein Klick aufs Symbol); "0" = stattdessen Systembenachrichtigung
PROACTIVE_OPEN_POPUP = _ENV.get("PDA_PROACTIVE_OPEN_POPUP", "1") != "0"
PROACTIVE_NOTICE_MS = 8000            # Anzeigedauer der Benachrichtigung (Klick darauf öffnet das Popup)
# Wächter (backend/watcher.py): prüft im Hintergrund Mails, Aufgaben, Termine. Alles Weitere im Popup.
PROACTIVE_WATCH = _ENV.get("PDA_PROACTIVE_WATCH", "1") != "0"
PROACTIVE_STATE_FILE = APP_DATA_DIR / "proactive_state.json"   # was schon gemeldet wurde

POPUP_PAGE = FRONTEND_DIR / "popup.html"
POPUP_SIZE_RATIO = (0.3, 0.6)         # Anteil des Bildschirms (Breite, Höhe)
POPUP_ENLARGED_SIZE_RATIO = (0.55, 0.9)   # vergrößertes Popup (Knopf im Chat)
POPUP_BACKGROUND = "#2E2E2E"          # identisch mit --background in frontend/theme.css
POPUP_MARGIN_PX = 8
POPUP_SLIDE_IN_OFFSET_PX = 50         # Start der Animation unterhalb der Endposition
POPUP_ANIMATION_MS = 500
