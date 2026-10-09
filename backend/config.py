"""Zentrale Konfiguration: Pfade, Namen und Darstellungswerte."""
from __future__ import annotations

import sys
from pathlib import Path

# Im PyInstaller-Build liegen die Dateien im Entpack-Ordner (_MEIPASS).
ROOT_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
FRONTEND_DIR = ROOT_DIR / "frontend"
TEMPLATE_DIR = FRONTEND_DIR / "templates"   # Jinja2-Templates für das iframe

APP_NAME = "Personal Digital Agent"
APP_USER_MODEL_ID = "swe2.personaldigitalagent.1.0"
TRAY_ICON = ROOT_DIR / "TrayIcon.ico"

ASSISTANT_BACKEND = "commands"        # siehe backend/assistant/__init__.py (_BACKENDS)

POPUP_PAGE = FRONTEND_DIR / "popup.html"
POPUP_SIZE_RATIO = (0.3, 0.6)         # Anteil des Bildschirms (Breite, Höhe)
POPUP_BACKGROUND = "#2E2E2E"          # identisch mit --background in frontend/theme.css
POPUP_MARGIN_PX = 8
POPUP_SLIDE_IN_OFFSET_PX = 50         # Start der Animation unterhalb der Endposition
POPUP_ANIMATION_MS = 500
