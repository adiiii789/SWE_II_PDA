import threading
import time
import unittest

from PyQt5.QtCore import QObject, QRect, QUrl, pyqtSignal

from tests.qt_helpers import qt_app, wait_until

from backend import api, config
from backend.desktop.application import Application, ProactiveTrigger, create_popup, forward_proactive_notices
from backend.desktop.popup_window import PopupWindow
from backend.desktop.tray_icon import TrayIcon
from backend.desktop.web_view import WebView
from backend.events import PROACTIVE_NOTICE, EventBus, events


def settle(seconds: float = 0.3) -> None:
    """Ereignisse eine Weile abarbeiten. Nach hide() schickt Windows noch "Fenster inaktiv" - würde
    das Popup im selben Durchlauf wieder geöffnet, schlösse diese späte Nachricht es gleich wieder.
    Im Betrieb liegen Schließen und neues Öffnen nie so dicht beieinander."""
    wait_until(lambda: False, seconds)


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
        self.assertIn('["cancel_recording", "chat", "enlarge_popup", "get_settings", "list_models", "open_attachment", "open_link", "proactive_message", "render_view", "reset_settings", "save_attachment", "save_settings", "select_model", "speak", "speech_support", "start_recording", "start_view", "stop_recording", "stop_speaking"]', script)
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
        self.assertTrue(self.application.tray.toolTip().startswith(config.APP_NAME))

    def test_left_click_and_notice_click_open_popup(self):
        # Ein Test statt zwei: jede Application startet ein eigenes Chromium, zu viele davon
        # lassen spätere Tests (test_popup_page) beim Laden scheitern.
        self.application.tray.left_clicked.emit()
        self.assertTrue(self.application.popup.isVisible())
        self.application.popup.hide()
        settle()
        self.application.tray.messageClicked.emit()   # Klick auf die Benachrichtigung einer Meldung
        self.assertTrue(wait_until(self.application.popup.isVisible))
        self.application.popup.hide()

    def test_proactive_notice_opens_popup_like_a_tray_click(self):
        # Wie im Betrieb: Meldung aus einem fremden Thread, das Programm hat keinen Fokus, vorher war
        # das Popup schon einmal offen. Ohne Fokusübernahme ginge das Qt.Popup sofort wieder zu.
        popup = self.application.popup
        self.assertEqual(popup.anchor, self.application.tray.anchor)   # Mitte des Tray-Icons, wie ein Klick
        used = []
        popup.anchor = lambda: used.append(self.application.tray.anchor()) or used[-1]
        popup.show_at_cursor()
        popup.hide()
        settle()
        sender = threading.Thread(target=events.publish, args=(PROACTIVE_NOTICE, {"title": "T", "text": "x"}))
        sender.start()
        sender.join()
        self.assertTrue(wait_until(popup.isVisible))
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            self.qt_app.processEvents()
            self.assertTrue(popup.isVisible(), "Popup hat sich wieder geschlossen")
            time.sleep(0.02)
        # Die Icon-Position kann sich ändern, wenn andere Tray-Icons kommen und gehen - daher der beim Öffnen benutzte Punkt.
        anchor, = used
        self.assertEqual(popup._animation.endValue(),
                         QRect(anchor.x() - popup.width(), anchor.y() - popup.height(), popup.width(), popup.height()))
        popup.hide()

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


class FakePopup(QObject):
    """Nur das Signal des Popups - ohne eigenes Chromium (davon verträgt der Testlauf nicht beliebig viele)."""
    show_requested = pyqtSignal()


class ForwardProactiveNoticesTest(unittest.TestCase):
    def setUp(self):
        qt_app()
        self.tray = TrayIcon(config.TRAY_ICON, "x")
        self.popup = FakePopup()
        self.notices = []
        self.opened = []
        self.tray.notify_requested.connect(lambda *args: self.notices.append(args))
        self.popup.show_requested.connect(lambda: self.opened.append(True))
        self.bus = EventBus()

    def test_notice_opens_popup_from_other_thread(self):
        self.addCleanup(forward_proactive_notices(self.tray, self.popup, self.bus, open_popup=True))
        self.bus.publish("anderes_ereignis", {})
        sender = threading.Thread(target=self.bus.publish, args=(PROACTIVE_NOTICE, {"title": "T", "text": "x"}))
        sender.start()
        sender.join()
        self.assertTrue(wait_until(lambda: self.opened == [True]))
        self.assertEqual(self.notices, [])

    def test_notice_becomes_tray_notification_when_popup_should_stay_closed(self):
        self.addCleanup(forward_proactive_notices(self.tray, self.popup, self.bus, open_popup=False))
        self.bus.publish(PROACTIVE_NOTICE, {"title": "T", "text": "Hallo"})
        self.assertEqual(self.notices, [("T", "Hallo", config.PROACTIVE_NOTICE_MS)])
        self.assertEqual(self.opened, [])


class ProactiveTriggerTest(unittest.TestCase):
    def test_runs_in_background_and_ignores_presses_while_busy(self):
        release = threading.Event()
        sent = []

        def send(occasion):
            sent.append((occasion, threading.current_thread() is not threading.main_thread()))
            release.wait(5)

        trigger = ProactiveTrigger(send)
        self.assertTrue(trigger.fire())
        self.assertTrue(wait_until(lambda: bool(sent)))
        self.assertFalse(trigger.fire())   # läuft noch
        release.set()
        self.assertTrue(wait_until(lambda: trigger.fire("demo")))
        self.assertTrue(wait_until(lambda: len(sent) == 2))
        self.assertEqual(sent, [("demo", True), ("demo", True)])

    def test_errors_are_logged_and_trigger_stays_usable(self):
        def send(occasion):
            raise RuntimeError("kaputt")

        trigger = ProactiveTrigger(send)
        with self.assertLogs("backend.desktop.application", "ERROR"):
            trigger.fire()
            self.assertTrue(wait_until(lambda: not trigger._busy.locked()))
        self.assertTrue(trigger.fire())


if __name__ == "__main__":
    unittest.main()
