import json
import unittest
from unittest import mock

from backend import api
from backend.events import POPUP_ENLARGED, events
from backend.views import InvalidViewRequestError


class ChatTest(unittest.TestCase):
    def test_chat_returns_json_serializable_reply_with_rendered_view(self):
        reply = api.chat("system")
        self.assertEqual(json.loads(json.dumps(reply)), reply)
        self.assertEqual(reply["text"], "Hier sind die Systeminfos.")
        self.assertIn("<table>", reply["html"])

    def test_chat_without_view(self):
        self.assertIsNone(api.chat("unbekannt")["html"])

    def test_start_view(self):
        self.assertIn("Personal Digital Agent", api.start_view())


class ModelSelectionApiTest(unittest.TestCase):
    # Die Tests laufen mit dem CommandAssistant (tests/conftest.py): kein Sprachmodell.
    def test_list_models_without_language_model(self):
        self.assertEqual(api.list_models(), {"models": [], "current": None})

    def test_select_model_without_language_model(self):
        with self.assertRaises(ValueError):
            api.select_model("llama3.2")

    def test_with_model_selection(self):
        class FakeAssistant:
            def reply(self, message): ...
            def available_models(self): return [{"name": "a", "tools": True}]
            def current_model(self): return "a"
            def select_model(self, name): self.selected = name

        fake = FakeAssistant()
        with mock.patch.object(api, "_assistant", return_value=fake):
            self.assertEqual(api.list_models(), {"models": [{"name": "a", "tools": True}], "current": "a"})
            self.assertEqual(api.select_model("a"), "a")
        self.assertEqual(fake.selected, "a")


class SpeechApiTest(unittest.TestCase):
    def setUp(self):
        self.speech_input, self.speech_output = mock.Mock(), mock.Mock()
        self.speech_input.stop.return_value = "Hallo"
        for name, value in (("_speech_input", self.speech_input), ("_speech_output", self.speech_output)):
            patcher = mock.patch.object(api, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_speech_support(self):
        self.assertEqual(api.speech_support(), {"input": True, "output": True})

    def test_recording_stops_speaking_first(self):
        api.start_recording()
        self.speech_output.stop.assert_called_once()
        self.speech_input.start.assert_called_once()
        self.assertEqual(api.stop_recording(), "Hallo")
        api.cancel_recording()
        self.speech_input.cancel.assert_called_once()

    def test_speak_and_stop(self):
        api.speak("Hallo")
        self.speech_output.speak.assert_called_once_with("Hallo")
        api.stop_speaking()
        self.speech_output.stop.assert_called_once()

    def test_without_speech_packages(self):
        with mock.patch.object(api, "_speech_input", return_value=None), \
                mock.patch.object(api, "_speech_output", return_value=None):
            self.assertEqual(api.speech_support(), {"input": False, "output": False})
            api.cancel_recording()   # nichts zu tun - kein Fehler
            api.stop_speaking()
            with self.assertRaisesRegex(RuntimeError, "Spracheingabe"):
                api.start_recording()
            with self.assertRaisesRegex(RuntimeError, "Sprachausgabe"):
                api.speak("Hallo")


class OpenLinkTest(unittest.TestCase):
    def test_opens_web_links_in_browser(self):
        with mock.patch("webbrowser.open") as browser:
            api.open_link("https://ollama.com")
        browser.assert_called_once_with("https://ollama.com")

    def test_rejects_other_schemes(self):
        with mock.patch("webbrowser.open") as browser:
            for url in ("javascript:alert(1)", "file:///C:/Windows/System32/cmd.exe"):
                with self.assertRaises(ValueError):
                    api.open_link(url)
        browser.assert_not_called()


class EnlargePopupTest(unittest.TestCase):
    def test_publishes_event(self):
        received = []
        unsubscribe = events.subscribe(lambda name, payload: received.append((name, payload)))
        self.addCleanup(unsubscribe)
        self.assertTrue(api.enlarge_popup(True))
        self.assertFalse(api.enlarge_popup(0))
        self.assertEqual(received, [(POPUP_ENLARGED, True), (POPUP_ENLARGED, False)])


class RenderViewTest(unittest.TestCase):
    def test_template_request(self):
        html = api.render_view({"template": "default", "data": {"title": "Hallo", "text": "Welt"}})
        self.assertIn("<h2>Hallo</h2>", html)
        self.assertIn("<p>Welt</p>", html)

    def test_html_request(self):
        self.assertEqual(api.render_view({"html": "<b>own</b>"}), "<b>own</b>")

    def test_invalid_request(self):
        with self.assertRaises(InvalidViewRequestError):
            api.render_view({"template": "default", "html": "<b>"})


if __name__ == "__main__":
    unittest.main()
