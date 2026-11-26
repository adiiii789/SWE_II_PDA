import unittest
from unittest import mock

from PyQt5.QtCore import QObject, QRect, pyqtSignal

from tests.qt_helpers import qt_app, wait_until

from backend.desktop.screens import ScreenWatcher


class FakeScreen(QObject):
    geometryChanged = pyqtSignal(QRect)
    availableGeometryChanged = pyqtSignal(QRect)
    logicalDotsPerInchChanged = pyqtSignal(float)
    physicalDotsPerInchChanged = pyqtSignal(float)
    orientationChanged = pyqtSignal(int)


class FakeApp(QObject):
    screenAdded = pyqtSignal(object)
    screenRemoved = pyqtSignal(object)
    primaryScreenChanged = pyqtSignal(object)

    def __init__(self, screens):
        super().__init__()
        self._screens = list(screens)

    def screens(self):
        return list(self._screens)


class ScreenWatcherTest(unittest.TestCase):
    def setUp(self):
        qt_app()
        self.screen = FakeScreen()
        self.app = FakeApp([self.screen])
        self.watcher = ScreenWatcher(self.app, delay_ms=10)
        self.changed = mock.Mock()
        self.watcher.changed.connect(self.changed)
        self.addCleanup(self.watcher.stop)

    def test_bundles_a_burst_of_changes_into_one(self):
        # Duplizieren: Auflösung, freie Fläche und DPI ändern sich kurz hintereinander
        self.screen.geometryChanged.emit(QRect(0, 0, 1024, 768))
        self.screen.availableGeometryChanged.emit(QRect(0, 0, 1024, 728))
        self.screen.logicalDotsPerInchChanged.emit(96.0)
        self.assertTrue(wait_until(lambda: self.changed.call_count > 0, 2))
        wait_until(lambda: False, 0.1)
        self.assertEqual(self.changed.call_count, 1)

    def test_reports_added_screen_and_watches_it(self):
        projector = FakeScreen()
        self.app.screenAdded.emit(projector)
        self.assertTrue(wait_until(lambda: self.changed.call_count == 1, 2))
        projector.geometryChanged.emit(QRect(0, 0, 1280, 720))
        self.assertTrue(wait_until(lambda: self.changed.call_count == 2, 2))

    def test_reports_removed_and_primary_screen(self):
        self.app.screenRemoved.emit(self.screen)
        self.assertTrue(wait_until(lambda: self.changed.call_count == 1, 2))
        self.app.primaryScreenChanged.emit(self.screen)
        self.assertTrue(wait_until(lambda: self.changed.call_count == 2, 2))

    def test_stop_disconnects(self):
        self.watcher.stop()
        self.screen.geometryChanged.emit(QRect(0, 0, 800, 600))
        self.app.screenAdded.emit(FakeScreen())
        wait_until(lambda: False, 0.1)
        self.changed.assert_not_called()
        self.watcher.stop()   # zweimal stoppen schadet nicht


if __name__ == "__main__":
    unittest.main()
