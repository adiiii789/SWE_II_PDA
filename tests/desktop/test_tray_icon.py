import unittest
from pathlib import Path

from PyQt5.QtWidgets import QSystemTrayIcon

from tests.qt_helpers import qt_app

from backend import config
from backend.desktop.tray_icon import PROACTIVE_TEST_ACTION, TrayIcon


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

    def test_context_menu_actions(self):
        actions = self.tray.contextMenu().actions()
        self.assertEqual([a.text() for a in actions], [PROACTIVE_TEST_ACTION, "", "Beenden"])
        self.assertEqual(self.quits, [])

    def test_context_menu_quit_action(self):
        self.tray.contextMenu().actions()[-1].trigger()
        self.assertEqual(self.quits, [True])

    def test_context_menu_proactive_test_action(self):
        tests = []
        self.tray.proactive_test_requested.connect(lambda: tests.append(True))
        self.tray.contextMenu().actions()[0].trigger()
        self.assertEqual(tests, [True])
        self.assertEqual(self.quits, [])

    def test_anchor_is_icon_center_or_screen_corner(self):
        from PyQt5.QtGui import QGuiApplication
        self.tray.show()
        self.addCleanup(self.tray.hide)
        geometry = self.tray.geometry()
        expected = (geometry.center() if geometry.isValid() and not geometry.isEmpty()
                    else QGuiApplication.primaryScreen().availableGeometry().bottomRight())
        self.assertEqual(self.tray.anchor(), expected)

    def test_notify_requested_shows_message(self):
        shown = []
        self.tray.showMessage = lambda *args: shown.append(args[:2] + args[3:])
        self.tray.notify_requested.emit("Titel", "Text", 1000)
        self.assertEqual(shown, [("Titel", "Text", 1000)])


if __name__ == "__main__":
    unittest.main()
