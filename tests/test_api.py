import json
import unittest
from unittest import mock

from backend import api
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
