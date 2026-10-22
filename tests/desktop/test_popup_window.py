import unittest

from PyQt5.QtCore import QPoint
from PyQt5.QtGui import QCloseEvent, QCursor, QGuiApplication
from PyQt5.QtWidgets import QLabel

from tests.qt_helpers import qt_app

from backend import config
from backend.desktop.popup_window import PopupWindow


class PopupWindowTest(unittest.TestCase):
    def setUp(self):
        qt_app()
        self.content = QLabel("Inhalt")
        self.popup = PopupWindow(self.content)

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
        self.assertEqual(end.bottomRight() + QPoint(1, 1), cursor)

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


if __name__ == "__main__":
    unittest.main()
