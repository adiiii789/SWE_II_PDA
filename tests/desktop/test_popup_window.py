import unittest
import sys
from unittest import mock

from PyQt5.QtCore import QPoint, QRect
from PyQt5.QtGui import QCloseEvent, QCursor, QGuiApplication
from PyQt5.QtWidgets import QLabel

from tests.qt_helpers import qt_app, wait_until

from backend import config
from backend.desktop import popup_window
from backend.desktop.popup_window import PopupWindow, popup_geometry


class PopupWindowTest(unittest.TestCase):
    def setUp(self):
        qt_app()
        monitor = mock.patch("backend.desktop.macos.OutsideClickMonitor")
        monitor.start()
        self.addCleanup(monitor.stop)
        self.content = QLabel("Inhalt")
        self.popup = PopupWindow(self.content)
        self.addCleanup(self.popup.release_desktop_resources)

    def tearDown(self):
        self.popup.hide()

    def test_content_is_embedded(self):
        self.assertIs(self.popup.content, self.content)
        self.assertIs(self.content.parent(), self.popup)

    def test_show_at_cursor_uses_screen_ratio_and_ends_at_cursor(self):
        QCursor.setPos(QPoint(800, 600))
        cursor = QCursor.pos()
        geo = QGuiApplication.primaryScreen().geometry()
        width = int(geo.width() * config.POPUP_SIZE_RATIO[0])
        height = int(geo.height() * config.POPUP_SIZE_RATIO[1])

        self.popup.show_at_cursor()

        self.assertTrue(self.popup.isVisible())
        self.assertEqual((self.popup.width(), self.popup.height()), (width, height))
        end = self.popup._animation.endValue()
        self.assertEqual(end, popup_geometry(cursor, self.popup._screen().availableGeometry(), width, height, sys.platform == "darwin"))

    def test_show_requested_opens_at_anchor_and_takes_focus(self):
        # Proaktive Meldung: wie ein Klick aufs Tray-Icon, nur am Ankerpunkt statt am Mauszeiger.
        self.popup.anchor = lambda: QPoint(900, 700)
        with mock.patch.object(popup_window, "bring_to_front", return_value=True) as front:
            self.popup.show_requested.emit()
        self.assertTrue(self.popup.isVisible())
        self.assertEqual(self.popup._animation.endValue(), popup_geometry(QPoint(900, 700), self.popup._screen().availableGeometry(), self.popup.width(), self.popup.height(), sys.platform == "darwin"))
        front.assert_called_once_with(int(self.popup.winId()))

    def test_show_requested_leaves_open_popup_alone(self):
        self.popup.show_at_cursor()
        end = self.popup._animation.endValue()
        self.popup.anchor = lambda: QPoint(300, 300)
        with mock.patch.object(popup_window, "bring_to_front") as front:
            self.popup.show_requested.emit()
        front.assert_not_called()
        self.assertEqual(self.popup._animation.endValue(), end)

    def test_default_anchor_is_bottom_right_of_screen(self):
        self.assertTrue(QGuiApplication.primaryScreen().availableGeometry().contains(self.popup.anchor()))

    def test_show_at_cursor_does_not_force_focus(self):
        with mock.patch.object(popup_window, "bring_to_front") as front:
            self.popup.show_at_cursor()
        front.assert_not_called()

    def test_enlarged_size_is_used_on_next_show(self):
        self.popup.set_enlarged(True)
        self.popup.show_at_cursor()
        geo = QGuiApplication.primaryScreen().geometry()
        self.assertEqual(self.popup.width(), int(geo.width() * config.POPUP_ENLARGED_SIZE_RATIO[0]))

    def test_enlarge_while_visible_keeps_bottom_right_corner_on_screen(self):
        QCursor.setPos(QPoint(800, 600))
        self.popup.show_at_cursor()
        self.popup._animation.stop()
        self.popup.setGeometry(self.popup._animation.endValue())
        corner = self.popup.geometry().bottomRight()

        self.popup.set_enlarged(True)

        geo = QGuiApplication.primaryScreen().geometry()
        self.assertEqual(self.popup.width(), int(geo.width() * config.POPUP_ENLARGED_SIZE_RATIO[0]))
        available = QGuiApplication.primaryScreen().availableGeometry()
        self.assertTrue(available.contains(self.popup.geometry().topLeft()))
        self.assertLessEqual(self.popup.geometry().bottom(), max(corner.y(), available.bottom()))

        self.popup.set_enlarged(False)
        self.assertEqual(self.popup.width(), int(geo.width() * config.POPUP_SIZE_RATIO[0]))

    def test_close_only_hides(self):
        self.popup.show()
        event = QCloseEvent()
        self.popup.closeEvent(event)
        self.assertFalse(event.isAccepted())
        self.assertFalse(self.popup.isVisible())

    def test_tray_click_is_not_treated_as_an_outside_click(self):
        icon_pos = QPoint(700, 15)
        self.popup.anchor = lambda: icon_pos
        self.popup.tray_geometry = lambda: QRect(690, 0, 20, 30)
        self.popup.toggle_at_anchor()
        with mock.patch.object(QCursor, "pos", return_value=icon_pos):
            self.popup.outside_click_detected.emit()
        self.assertTrue(self.popup.isVisible())
        self.popup.toggle_at_anchor()
        self.assertFalse(self.popup.isVisible())
        self.popup.toggle_at_anchor()
        self.assertTrue(self.popup.isVisible())
        with mock.patch.object(QCursor, "pos", return_value=QPoint(100, 100)):
            self.popup.outside_click_detected.emit()
        self.assertFalse(self.popup.isVisible())


if __name__ == "__main__":
    unittest.main()
