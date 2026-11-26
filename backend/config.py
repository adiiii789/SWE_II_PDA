"""Zentrale Konfiguration: Pfade, Namen und Darstellungswerte."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
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


# Einstellungen, Keys und Zugangsdaten: Umgebungsvariablen oder die .env (Vorlage: .env.example) -
# im Projektordner, im gepackten Programm im App-Datenordner (der Entpack-Ordner ist nur vorübergehend).
# PDA_ENV_FILE nennt eine andere Datei (die Tests nutzen eine leere). Umgebungsvariablen haben Vorrang.
# os.environ bleibt unverändert, damit die MCP-Server die .env selbst lesen - Änderungen an den
# Mail-Einstellungen wirken dort ohne Neustart. Keys liest backend/api_keys.py bei jedem Zugriff neu
# (verwaltbar im Popup unter ⚙ → Zugangsdaten).
ENV_FILE = Path(os.environ.get("PDA_ENV_FILE")
                or (app_data_dir() if hasattr(sys, "_MEIPASS") else ROOT_DIR) / ".env")
_ENV = {**read_env_file(ENV_FILE), **os.environ}
# Früherer Ort der Mail-Einstellungen (vor Sprint 3): Fehlende Einträge übernimmt backend/api_keys.py beim
# Start in ENV_FILE. Die alte Datei bleibt, wie sie ist.
LEGACY_MCP_ENV_FILE = Path(os.environ.get("PDA_LEGACY_MCP_ENV_FILE") or ROOT_DIR / "mcp_servers" / ".env")

# "models" (Ollama, Gemini, Claude), einzelner Anbieter oder "commands" (nur feste Befehle).
# Siehe backend/assistant/__init__.py (_BACKENDS). Die Tests setzen "commands" (tests/conftest.py).
ASSISTANT_BACKEND = _ENV.get("PDA_ASSISTANT_BACKEND", "models")

GEMINI_MODEL = _ENV.get("PDA_GEMINI_MODEL", "").strip()
GEMINI_TIMEOUT_S = 120
OLLAMA_TIMEOUT_S = 300
OLLAMA_CATALOG_TIMEOUT_S = 2

# Claude über die Claude-Code-Anmeldung dieses Rechners (backend/assistant/claude_code.py).
# Erscheint in der Modellauswahl, sobald claude-agent-sdk installiert ist; PDA_CLAUDE=0 blendet es aus.
CLAUDE_MODEL = _ENV.get("PDA_CLAUDE_MODEL", "").strip()          # sonnet, haiku, opus oder Modell-ID
CLAUDE_EFFORT = _ENV.get("PDA_CLAUDE_EFFORT", "medium").strip()  # low, medium, high, xhigh, max
CLAUDE_TIMEOUT_S = 180
CLAUDE_ENABLED = (_ENV.get("PDA_CLAUDE", "1") != "0"
                  and importlib.util.find_spec("claude_agent_sdk") is not None)

ASSISTANT_MAX_TOOL_ROUNDS = 5         # Werkzeug-Runden pro Nachricht, gegen Endlosschleifen
ASSISTANT_MAX_HISTORY = 30            # Nachrichten im Verlauf, die das Modell sieht

# MCP-Server, deren Werkzeuge der Assistent nutzen kann (backend/integrations/mcp_client.py)
MCP_SERVERS_FILE = ROOT_DIR / "mcp_servers.json"

# Präferenzen (backend/preferences.py) - außerhalb des Programmordners, damit sie Updates überstehen
APP_DATA_DIR = app_data_dir()
PREFERENCES_FILE = APP_DATA_DIR / "preferences.json"
# Leerer Arbeitsordner für Claude Code. Im Temp-Ordner, weil Python aus dem Microsoft Store neue Ordner
# unter AppData umleitet - claude.exe würde sie dann nicht finden.
CLAUDE_WORK_DIR = Path(tempfile.gettempdir()) / "PersonalDigitalAgent-claude"

# Dateien im Chat (backend/attachments.py). Nur Dateien in ATTACHMENT_DIR lassen sich öffnen;
# derselbe Ordner, in den mcp_servers/inbox.py Mail-Anhänge ablegt.
ATTACHMENT_DIR = Path(_ENV.get("PDA_ATTACHMENT_DIR") or APP_DATA_DIR / "attachments")
DOWNLOAD_DIR = Path.home() / "Downloads"   # Ziel von "Speichern"

# Reise-Assistent (backend/assistant/skills/travel/). Ohne Key fällt der jeweilige Teil weg; die Keys
# (PDA_ORS_KEY, PDA_DB_CLIENT_ID, PDA_DB_API_KEY, PDA_TANKERKOENIG_KEY) liest backend/api_keys.py.
# Einrichtung siehe README. Persönliche Werte (Zeitwert, Verbrauch …) stehen in den Präferenzen.
# credentials.json (OAuth-Client) und token.json - derselbe Ordner wie mcp_servers/google_calendar.py
GOOGLE_DIR = Path(_ENV.get("PDA_GOOGLE_DIR") or APP_DATA_DIR / "google")
DB_STATIONS_FILE = APP_DATA_DIR / "db_stations.json"       # Bahnhofsliste aus StaDa (einmal pro Woche geladen)
STATIONS_TIMEOUT_S = 90                                    # der Download ist ≈ 9 MB groß
TILE_DIR = APP_DATA_DIR / "map_tiles"                      # OpenStreetMap-Kacheln für die Routenkarte
TILE_TIMEOUT_S = 5                                         # lieber ohne Karte als lange warten
# Bahn/ÖPNV-Verbindungssuche (MOTIS), ohne Key; leer = aus (dann nur die DB-Tafeln)
TRANSITOUS_URL = _ENV.get("PDA_TRANSITOUS_URL", "https://api.transitous.org")
# VVS-Auskunft (EFA) für Wege im VVS-Gebiet, ohne Key; leer = aus (dann Transitous)
VVS_URL = _ENV.get("PDA_VVS_URL", "https://www3.vvs.de/mngvvs")
HTTP_TIMEOUT_S = 20
TRAVEL_CHECK_INTERVAL_S = 120         # so oft schaut die Reise-Erinnerung in den Kalender (wie früh: ⚙ → Reise)

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

# Beim Programmstart das Popup mit dem Ladebildschirm öffnen; "0" = erst beim Klick aufs Tray-Icon
STARTUP_OPEN_POPUP = _ENV.get("PDA_STARTUP_OPEN_POPUP", "1") != "0"

POPUP_PAGE = FRONTEND_DIR / "popup.html"
# Größen relativ zum Bildschirm (backend/desktop/layout.py), gerechnet mit der freien Fläche in logischen
# Pixeln. Die px-Werte in den CSS-Dateien sind Entwurfsmaße für UI_REFERENCE_SCREEN (1080p ohne
# Taskleiste) und werden mit dem Maßstab gezoomt: 4K/1440p größer, kleine Bildschirme kleiner.
UI_REFERENCE_SCREEN = (1440, 1040)    # bei dieser Fläche Maßstab 1 (Breite zählt erst bei schmalen Bildschirmen)
UI_SCALE_RANGE = (0.9, 2.5)           # darunter wird Text zu klein zum Lesen, Knöpfe zu klein zum Treffen
POPUP_HEIGHT_RATIO = 0.6              # Anteil der Bildschirmhöhe
POPUP_ASPECT = 0.9                    # Breite / Höhe - gleich auf 4:3, 16:10, 16:9 und Ultrawide
POPUP_MAX_WIDTH_RATIO = 0.45          # höchstens dieser Anteil der Breite (hochkant, 4:3)
POPUP_ENLARGED_HEIGHT_RATIO = 0.9     # vergrößertes Popup (Knopf im Chat)
POPUP_ENLARGED_ASPECT = 1.15
POPUP_ENLARGED_MAX_WIDTH_RATIO = 0.7
# Kleinste Fläche, auf der Kopfzeile, Chat, Eingabe und Einstellungen bedienbar bleiben - in CSS-Pixeln,
# wird mit dem Maßstab multipliziert. Auf sehr kleinen Bildschirmen (480p) wird das Popup lieber fast
# bildschirmfüllend als unbedienbar; mehr als den Bildschirm nimmt es nie.
POPUP_MIN_CSS_SIZE = (360, 460)
# Bildschirm geändert (Beamer angesteckt/dupliziert, Auflösung, Skalierung, Taskleiste): so lange warten,
# bis Windows/macOS fertig umgeschaltet haben - dabei kommen meist mehrere Meldungen kurz hintereinander.
SCREEN_CHANGE_DELAY_MS = 300
# Seitenhintergrund der Web-Ansicht vor dem Laden: durchsichtig - das Fenster ist es auch, die Seite
# zeichnet Fläche und Ecken selbst (--window-shape in frontend/theme.css). Kein weißes Aufblitzen.
POPUP_BACKGROUND = "transparent"
POPUP_MARGIN_PX = 0                   # Abstand zum Rand macht die Seite selbst (popup.css), passend zum Design
POPUP_SLIDE_IN_OFFSET_PX = 50         # Start der Animation unterhalb der Endposition
POPUP_ANIMATION_MS = 500

# 3D-Begleiter: eigenes durchsichtiges Fenster links neben dem Popup (backend/desktop/companion_window.py).
# "0" schaltet ihn ganz ab; im Popup lässt er sich unter "Design" aus- und einblenden.
COMPANION_ENABLED = _ENV.get("PDA_COMPANION", "1") != "0"
COMPANION_PAGE = FRONTEND_DIR / "companion.html"
# Eigenes 3D-Modell (glTF/GLB) statt der eingebauten Figur; fehlt die Datei, bleibt die eingebaute.
COMPANION_MODELS_DIR = FRONTEND_DIR / "models"   # zur Auswahl in den Einstellungen (backend/companion_models.py)
COMPANION_MODEL = Path(_ENV.get("PDA_COMPANION_MODEL") or FRONTEND_DIR / "models" / "companion.glb")
COMPANION_HEIGHT_RATIO = 0.34         # Höhe als Anteil der Bildschirmhöhe (höchstens so hoch wie das Popup)
COMPANION_ASPECT = 0.7                # Breite / Höhe
COMPANION_GAP_PX = 4                  # Abstand zum Popup
COMPANION_POINTER_MS = 50             # so oft schaut der Begleiter nach dem Mauszeiger
