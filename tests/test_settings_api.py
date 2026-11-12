"""api.get_settings / save_settings / reset_settings - mit Speicher im Arbeitsspeicher statt APPDATA."""
import unittest
from unittest import mock

from backend import api
from backend.assistant.settings import ANSWER_KEY, AssistantSettings
from backend.assistant.skills.travel.settings import TravelSettingsForm
from backend.proactive_settings import ProactiveSettings
from tests.assistant.test_settings import MemoryStore


class SettingsApiTest(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        for name, settings in (("_settings", AssistantSettings(self.store)),
                               ("_proactive_settings", ProactiveSettings(self.store)),
                               ("_travel_settings", TravelSettingsForm(self.store))):
            patcher = mock.patch.object(api, name, return_value=settings)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.stop_patches = mock.patch.stopall

    def test_travel_settings_are_saved_and_reset(self):
        form = api.save_settings({"travel": {"reminder": {"reminder_minutes": 20}, "general": {"home_address": "Daheim"}}})
        reminder = next(group for group in form["travel"] if group["id"] == "reminder")
        self.assertEqual(reminder["values"]["reminder_minutes"], 20)
        reset = next(group for group in api.reset_settings()["travel"] if group["id"] == "reminder")
        self.assertEqual(reset["values"]["reminder_minutes"], 15)
        self.assertEqual(self.store.get("travel_home_address"), "Daheim")

    def test_invalid_travel_value_saves_nothing(self):
        with self.assertRaises(ValueError):
            api.save_settings({"proactive": {"mail": {"criteria": "Uni"}}, "travel": {"car": {"fuel": "kerosin"}}})
        self.assertEqual(self.store.values, {})

    def test_travel_form_knows_missing_keys(self):
        self.stop_patches()
        with mock.patch.object(api, "default_store", return_value=self.store):
            form = api._travel_settings.__wrapped__().form()   # ungecacht, mit dem Speicher des Tests
        general = next(group for group in form if group["id"] == "general")
        weather = next(group for group in form if group["id"] == "weather")
        self.assertEqual(general["available"], bool(api.config.ORS_KEY))   # Adressen brauchen openrouteservice
        self.assertTrue(weather["available"])                               # braucht keinen Key

    def test_proactive_settings_are_saved_and_reset(self):
        form = api.save_settings({"proactive": {"mail": {"criteria": "Uni"}}})
        mail = next(section for section in form["proactive"] if section["id"] == "mail")
        self.assertEqual(mail["values"]["criteria"], "Uni")
        reset = next(section for section in api.reset_settings()["proactive"] if section["id"] == "mail")
        self.assertEqual(reset["values"]["criteria"], "")

    def test_invalid_answer_also_keeps_proactive_settings_unsaved(self):
        with self.assertRaises(ValueError):
            api.save_settings({"answer": {"tone": "frech"}, "proactive": {"mail": {"criteria": "Uni"}}})
        self.assertEqual(self.store.values, {})

    def test_invalid_proactive_value_saves_nothing(self):
        with self.assertRaises(ValueError):
            api.save_settings({"answer": {"tone": "sachlich"}, "proactive": {"general": {"quiet_from": "25:00"}}})
        self.assertEqual(self.store.values, {})

    def test_internal_tools_are_not_offered_in_settings(self):
        assistant = mock.Mock()
        assistant.tools.list_tools.return_value = [mock.Mock(description="intern")]
        assistant.tools.list_tools.return_value[0].name = "watch_open_tasks"
        with mock.patch.object(api, "_assistant", return_value=assistant):
            self.assertNotIn("tool:watch_open_tasks", [group["id"] for group in api.get_settings()["tools"]])

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
