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

    def test_close_only_hides(self):
        self.popup.show()
        event = QCloseEvent()
        self.popup.closeEvent(event)
        self.assertFalse(event.isAccepted())
        self.assertFalse(self.popup.isVisible())


if __name__ == "__main__":
    unittest.main()
