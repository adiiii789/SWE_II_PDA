import sys
import unittest
from unittest import mock

from PyQt5.QtWidgets import QWidget

from tests.qt_helpers import qt_app, wait_until

from backend.desktop import foreground


class BringToFrontTest(unittest.TestCase):
    def test_other_platforms_do_nothing(self):
        with mock.patch.object(foreground.sys, "platform", "linux"):
            self.assertFalse(foreground.bring_to_front(1234))

    @unittest.skipUnless(sys.platform == "win32", "nur unter Windows")
    def test_window_becomes_foreground(self):
        qt_app()
        window = QWidget()
        window.show()
        self.addCleanup(window.close)
        self.assertTrue(foreground.bring_to_front(int(window.winId())))
        self.assertTrue(foreground.bring_to_front(int(window.winId())))   # schon vorn: ebenfalls True
        self.assertTrue(wait_until(window.isActiveWindow))

    @unittest.skipUnless(sys.platform == "win32", "nur unter Windows")
    def test_refusal_is_logged(self):
        with self.assertLogs("backend.desktop.foreground", "WARNING"):
            self.assertFalse(foreground.bring_to_front(1))   # kein gültiges Fenster


if __name__ == "__main__":
    unittest.main()
