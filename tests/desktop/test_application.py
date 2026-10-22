import unittest

from PyQt5.QtCore import QUrl

from tests.qt_helpers import qt_app, wait_until

from backend import api, config
from backend.desktop.application import Application, create_popup
from backend.desktop.popup_window import PopupWindow
from backend.desktop.web_view import WebView


class CreatePopupTest(unittest.TestCase):
    def test_popup_contains_web_view_with_api_functions(self):
        qt_app()
        popup = create_popup()
        self.addCleanup(popup.content.deleteLater)
        self.addCleanup(popup.content.close_bridge)
        self.assertIsInstance(popup, PopupWindow)
        self.assertIsInstance(popup.content, WebView)
        script = popup.content.page().scripts().findScript("python-bridge").sourceCode()
        self.assertTrue(callable(api.chat))
        self.assertIn('["cancel_recording", "chat", "enlarge_popup", "list_models", "open_attachment", "open_link", "render_view", "save_attachment", "select_model", "speak", "speech_support", "start_recording", "start_view", "stop_recording", "stop_speaking"]', script)
        expected = QUrl.fromLocalFile(str(config.POPUP_PAGE))
        self.assertTrue(wait_until(lambda: popup.content.url() == expected))


class ApplicationTest(unittest.TestCase):
    def setUp(self):
        self.qt_app = qt_app()
        self.application = Application(self.qt_app)
        self.addCleanup(self.application.shutdown)

    def test_app_keeps_running_without_windows(self):
        self.assertFalse(self.qt_app.quitOnLastWindowClosed())

    def test_tray_is_configured(self):
        self.assertEqual(self.application.tray.toolTip(), config.APP_NAME)

    def test_left_click_opens_popup(self):
        self.application.tray.left_clicked.emit()
        self.assertTrue(self.application.popup.isVisible())
        self.application.popup.hide()

    def test_enlarge_event_resizes_popup(self):
        self.application.popup.show_at_cursor()
        normal = self.application.popup.size()
        api.enlarge_popup(True)
        self.assertTrue(wait_until(lambda: self.application.popup.enlarged))
        self.assertGreater(self.application.popup.width(), normal.width())
        api.enlarge_popup(False)
        self.assertTrue(wait_until(lambda: not self.application.popup.enlarged))
        self.assertEqual(self.application.popup.size(), normal)
        self.application.popup.hide()

    def test_shutdown_hides_tray(self):
        self.application.shutdown()
        self.assertFalse(self.application.tray.isVisible())


if __name__ == "__main__":
    unittest.main()
