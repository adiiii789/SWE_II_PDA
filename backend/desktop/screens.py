"""Bemerkt Änderungen an den Bildschirmen, während die App läuft.

Beispiele: Beamer oder zweiter Monitor an- bzw. abgesteckt, Anzeige dupliziert oder erweitert (Windows
schaltet dabei oft die Auflösung des Hauptbildschirms um, z. B. auf 1024 × 768), andere Auflösung oder
Skalierung eingestellt, Hauptbildschirm gewechselt, Taskleiste verschoben, Bildschirm gedreht.

Solche Umstellungen kommen als mehrere Qt-Signale kurz hintereinander; `changed` fasst sie zusammen und
meldet sich erst, wenn eine Weile Ruhe ist (config.SCREEN_CHANGE_DELAY_MS).
"""
from __future__ import annotations

from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from PyQt5.QtGui import QGuiApplication, QScreen

from backend import config


def _screen_signals(screen: QScreen) -> tuple:
    return (screen.geometryChanged, screen.availableGeometryChanged, screen.logicalDotsPerInchChanged,
            screen.physicalDotsPerInchChanged, screen.orientationChanged)


class ScreenWatcher(QObject):
    changed = pyqtSignal()

    def __init__(self, app: QGuiApplication | None = None, delay_ms: int = config.SCREEN_CHANGE_DELAY_MS,
                 parent: QObject | None = None):
        super().__init__(parent)
        self._app = app or QGuiApplication.instance()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(delay_ms)
        self._timer.timeout.connect(self.changed.emit)
        self._app.screenAdded.connect(self._on_screen_added)
        self._app.screenRemoved.connect(self.schedule)
        self._app.primaryScreenChanged.connect(self.schedule)
        for screen in self._app.screens():
            self._watch(screen)

    def _watch(self, screen: QScreen) -> None:
        # Signale eines abgesteckten Bildschirms trennt Qt selbst, wenn das QScreen-Objekt verschwindet.
        for signal in _screen_signals(screen):
            signal.connect(self.schedule)

    def _on_screen_added(self, screen: QScreen) -> None:
        self._watch(screen)
        self.schedule()

    def schedule(self, *_args) -> None:
        """Änderung vormerken; jede weitere verschiebt die Meldung (Timer startet neu)."""
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        for signal, slot in ((self._app.screenAdded, self._on_screen_added),
                             (self._app.screenRemoved, self.schedule),
                             (self._app.primaryScreenChanged, self.schedule)):
            try:
                signal.disconnect(slot)
            except TypeError:   # schon getrennt
                pass
        for screen in self._app.screens():
            for signal in _screen_signals(screen):
                try:
                    signal.disconnect(self.schedule)
                except TypeError:
                    pass
