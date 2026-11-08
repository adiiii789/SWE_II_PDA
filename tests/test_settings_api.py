"""api.get_settings / save_settings / reset_settings - mit Speicher im Arbeitsspeicher statt APPDATA."""
import unittest
from unittest import mock

from backend import api
from backend.assistant.settings import ANSWER_KEY, AssistantSettings
from tests.assistant.test_settings import MemoryStore


class SettingsApiTest(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        patcher = mock.patch.object(api, "_settings", return_value=AssistantSettings(self.store))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_form_without_language_model_has_no_tools_available(self):
        # Tests laufen mit dem CommandAssistant: keine Werkzeuge, die bekannten Gruppen trotzdem
        form = api.get_settings()
        self.assertIn("length", [field["key"] for field in form["answer"]["fields"]])
        self.assertFalse(any(group["available"] for group in form["tools"]))

    def test_save_returns_new_form(self):
        form = api.save_settings({"answer": {"tone": "sachlich"}, "tools": {"mail": {"max": 3}}})
        self.assertEqual(form["answer"]["values"]["tone"], "sachlich")
        mail = next(group for group in form["tools"] if group["id"] == "mail")
        self.assertEqual(mail["values"]["max"], 3)

    def test_invalid_change_raises(self):
        with self.assertRaises(ValueError):
            api.save_settings({"answer": {"tone": "frech"}})
        self.assertNotIn(ANSWER_KEY, self.store.values)

    def test_reset(self):
        api.save_settings({"answer": {"tone": "sachlich"}})
        self.assertEqual(api.reset_settings()["answer"]["values"]["tone"], "freundlich")

    def test_tools_of_assistant_are_listed(self):
        assistant = mock.Mock()
        assistant.tools.list_tools.return_value = [mock.Mock(description="Wetter")]
        assistant.tools.list_tools.return_value[0].name = "get_weather"
        with mock.patch.object(api, "_assistant", return_value=assistant):
            groups = {group["id"]: group for group in api.get_settings()["tools"]}
        self.assertTrue(groups["tool:get_weather"]["available"])

    def test_broken_tool_list_still_opens_settings(self):
        assistant = mock.Mock()
        assistant.tools.list_tools.side_effect = RuntimeError("MCP-Server weg")
        with mock.patch.object(api, "_assistant", return_value=assistant), self.assertLogs("backend.api", "ERROR"):
            self.assertIn("answer", api.get_settings())


if __name__ == "__main__":
    unittest.main()
