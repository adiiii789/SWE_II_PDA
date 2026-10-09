import unittest
from pathlib import Path

from PyQt5.QtWidgets import QSystemTrayIcon

from tests.qt_helpers import qt_app

from backend import config
from backend.desktop.tray_icon import TrayIcon


class TrayIconTest(unittest.TestCase):
    def setUp(self):
        qt_app()
        self.tray = TrayIcon(config.TRAY_ICON, "Tooltip")
        self.left_clicks = []
        self.quits = []
        self.tray.left_clicked.connect(lambda: self.left_clicks.append(True))
        self.tray.quit_requested.connect(lambda: self.quits.append(True))

    def test_tooltip_and_icon_are_set(self):
        self.assertEqual(self.tray.toolTip(), "Tooltip")
        self.assertFalse(self.tray.icon().isNull())

    def test_missing_icon_file_is_ignored(self):
        tray = TrayIcon(Path("gibt_es_nicht.ico"), "x")
        self.assertTrue(tray.icon().isNull())

    def test_left_click_emits_signal(self):
        self.tray.activated.emit(QSystemTrayIcon.Trigger)
        self.assertEqual(self.left_clicks, [True])

    def test_right_click_does_not_emit_left_click(self):
        self.tray.activated.emit(QSystemTrayIcon.Context)
        self.assertEqual(self.left_clicks, [])

    def test_context_menu_quit_action(self):
        actions = self.tray.contextMenu().actions()
        self.assertEqual([a.text() for a in actions], ["Beenden"])
        actions[0].trigger()
        self.assertEqual(self.quits, [True])


if __name__ == "__main__":
    unittest.main()
