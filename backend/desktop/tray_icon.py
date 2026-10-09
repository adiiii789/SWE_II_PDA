"""Tray-Icon: Linksklick meldet sich per Signal, Rechtsklick zeigt das Kontextmenü."""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QMenu, QSystemTrayIcon


class TrayIcon(QSystemTrayIcon):
    left_clicked = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, icon_path: Path, tooltip: str, parent: QObject | None = None):
        super().__init__(parent)
        if icon_path.exists():
            self.setIcon(QIcon(str(icon_path)))
        self.setToolTip(tooltip)

        self._menu = QMenu()
        self._menu.addAction("Beenden", self.quit_requested.emit)
        self.setContextMenu(self._menu)

        self.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self.left_clicked.emit()
