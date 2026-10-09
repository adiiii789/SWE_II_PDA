"""Einstiegspunkt des Personal Digital Agent (PDA)."""
from __future__ import annotations

import ctypes
import logging
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from backend import config
from backend.desktop.application import Application


def configure_qt() -> None:
    """Einstellungen, die vor dem Erzeugen der QApplication gesetzt sein müssen."""
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    if sys.platform == "win32":  # eigenes Taskleisten-Icon statt python.exe
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(config.APP_USER_MODEL_ID)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    configure_qt()
    qt_app = QApplication(sys.argv)
    application = Application(qt_app)  # noqa: F841  # Referenz halten, solange die App läuft
    return qt_app.exec_()


if __name__ == "__main__":
    sys.exit(main())
