import unittest

from PyQt5.QtCore import QEvent, QUrl

from tests.qt_helpers import qt_app, wait_until

from backend import api, config
from backend.desktop.application import Application, create_popup
from backend.desktop.popup_window import PopupWindow
from backend.desktop.web_view import WebView


class CreatePopupTest(unittest.TestCase):
    def test_popup_contains_web_view_with_api_functions(self):
        qt_app()
        popup = create_popup()
        self.addCleanup(qt_app().sendPostedEvents, None, QEvent.DeferredDelete)   # läuft als letztes
        self.addCleanup(popup.content.deleteLater)
        self.addCleanup(popup.content.close_bridge)
        self.assertIsInstance(popup, PopupWindow)
        self.assertIsInstance(popup.content, WebView)
        script = popup.content.page().scripts().findScript("python-bridge").sourceCode()
        self.assertTrue(callable(api.chat))
        self.assertIn('["chat", "list_models", "open_attachment", "render_view", "save_attachment", "select_model", "start_view"]', script)
        expected = QUrl.fromLocalFile(str(config.POPUP_PAGE))
        self.assertTrue(wait_until(lambda: popup.content.url() == expected))


class ApplicationTest(unittest.TestCase):
    def setUp(self):
        self.qt_app = qt_app()
        self.application = Application(self.qt_app)
        self.addCleanup(self._shutdown)

    def _shutdown(self):
        self.application.shutdown()
        # deleteLater() sofort ausführen: Sonst zerstört Qt die WebViews erst, während der
        # nächste Test seine Seite lädt - das bremst deren Laden um Sekunden.
        self.qt_app.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_app_keeps_running_without_windows(self):
        self.assertFalse(self.qt_app.quitOnLastWindowClosed())

    def test_tray_is_configured(self):
        self.assertEqual(self.application.tray.toolTip(), config.APP_NAME)

    def test_left_click_opens_popup(self):
        self.application.tray.left_clicked.emit()
        self.assertTrue(self.application.popup.isVisible())
        self.application.popup.hide()

    def test_shutdown_hides_tray(self):
        self.application.shutdown()
        self.assertFalse(self.application.tray.isVisible())


if __name__ == "__main__":
    unittest.main()
