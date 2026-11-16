"""Laufende Werkzeugaufrufe ans Popup melden (backend/assistant/tool_activity.py, ModelAssistant.on_tool)."""
import unittest

from backend.assistant.llm import ToolCall
from backend.assistant.tool_activity import tool_activity, tool_label
from tests.assistant.test_gemini_assistant import EchoTools, FakeModel, calls, make, text


class LabelTest(unittest.TestCase):
    def test_known_tools_have_german_labels(self):
        self.assertEqual(tool_label("list_calendar_events"), "Termine abrufen")
        self.assertEqual(tool_label("complete_task"), "Aufgabe erledigen")

    def test_unknown_tools_use_their_name(self):
        self.assertEqual(tool_label("book_flight"), "Book flight")

    def test_new_sprint_tools_have_german_labels(self):
        self.assertEqual(tool_label("plan_trip_home"), "Heimweg planen")
        self.assertEqual(tool_label("get_weather_forecast"), "Wetter abrufen")

    def test_error_flag_only_at_the_end(self):
        self.assertNotIn("error", tool_activity("start", "calculate"))
        self.assertTrue(tool_activity("end", "calculate", error=True)["error"])


class ReportTest(unittest.TestCase):
    def test_each_call_is_reported_before_and_after(self):
        seen = []
        model = FakeModel(calls(ToolCall("echo", {"text": "a"})), text("Fertig"))
        reply = make(model, EchoTools(), on_tool=seen.append).reply("Mach was")
        self.assertEqual(reply.text, "Fertig")
        self.assertEqual([(item["phase"], item["tool"]) for item in seen], [("start", "echo"), ("end", "echo")])
        self.assertFalse(seen[1]["error"])

    def test_broken_listener_does_not_stop_the_reply(self):
        def broken(_activity):
            raise RuntimeError("Anzeige kaputt")

        model = FakeModel(calls(ToolCall("echo", {"text": "a"})), text("Fertig"))
        with self.assertLogs("backend.assistant.model_assistant", "ERROR"):
            self.assertEqual(make(model, EchoTools(), on_tool=broken).reply("Mach was").text, "Fertig")


if __name__ == "__main__":
    unittest.main()
