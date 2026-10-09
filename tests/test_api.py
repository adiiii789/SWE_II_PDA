import json
import unittest

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
