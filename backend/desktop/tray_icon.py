"""Tray-Icon: Linksklick meldet sich per Signal, Rechtsklick zeigt das Kontextmenü,
notify() zeigt eine Windows-Benachrichtigung (proaktive Meldungen)."""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QObject, QPoint, pyqtSignal
from PyQt5.QtGui import QGuiApplication, QIcon
from PyQt5.QtWidgets import QMenu, QSystemTrayIcon


PROACTIVE_TEST_ACTION = "Proaktive Meldung testen"


class TrayIcon(QSystemTrayIcon):
    left_clicked = pyqtSignal()
    quit_requested = pyqtSignal()
    proactive_test_requested = pyqtSignal()   # Menü: proaktive Meldung vorführen
    # Darf aus jedem Thread gesendet werden - Qt zeigt die Benachrichtigung im Haupt-Thread.
    notify_requested = pyqtSignal(str, str, int)

    def __init__(self, icon_path: Path, tooltip: str, parent: QObject | None = None):
        super().__init__(parent)
        if icon_path.exists():
            self.setIcon(QIcon(str(icon_path)))
        self.setToolTip(tooltip)

        self._menu = QMenu()
        self._menu.addAction(PROACTIVE_TEST_ACTION, self.proactive_test_requested.emit)
        self._menu.addSeparator()
        self._menu.addAction("Beenden", self.quit_requested.emit)
        self.setContextMenu(self._menu)

        self.activated.connect(self._on_activated)
        self.notify_requested.connect(self.notify)

    def anchor(self) -> QPoint:
        """Mitte des Icons in der Taskleiste - dort, wo ein Klick aufs Icon landen würde. Liegt das
        Icon im ausgeblendeten Überlaufbereich, kennt Windows keine Position: dann die Ecke unten rechts."""
        geometry = self.geometry()
        if geometry.isValid() and not geometry.isEmpty():
            return geometry.center()
        return QGuiApplication.primaryScreen().availableGeometry().bottomRight()

    def notify(self, title: str, text: str, duration_ms: int) -> None:
        """Windows-Benachrichtigung am Tray-Icon; ein Klick darauf sendet messageClicked."""
        self.showMessage(title, text, self.icon() if not self.icon().isNull() else QSystemTrayIcon.Information,
                         duration_ms)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self.left_clicked.emit()
