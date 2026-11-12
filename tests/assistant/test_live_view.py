"""LiveView: Anzeige oben nach Änderungen neu laden (backend/assistant/live_view.py)."""
import datetime
import unittest

from backend.assistant.live_view import LiveView
from backend.assistant.llm import ToolCall
from backend.assistant.settings import AssistantSettings
from backend.assistant.tools import ToolResult

NOW = datetime.datetime(2026, 11, 12, 14, 0)


class MemoryPreferences:
    def __init__(self, **values):
        self.values = dict(values)

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value

    def all(self):
        return dict(self.values)


class TaskTools:
    """Google Tasks in klein: list_tasks zeigt die Liste, update_task benennt um."""

    def __init__(self):
        self.titles = {"l::1": "Steuer"}
        self.calls = []
        self.fail = False

    def list_tools(self):
        return []

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if self.fail:
            raise ConnectionError("offline")
        if name == "list_tasks":
            tasks = [{"id": key, "title": title} for key, title in self.titles.items()]
            return ToolResult("Aufgaben ...", data={"type": "tasks", "tasks": tasks})
        if name == "update_task":
            self.titles[arguments["task_id"]] = arguments["title"]
            return ToolResult("Geändert")
        return ToolResult("ok")


def titles(view):
    return [task["title"] for part in view.data["components"] for task in part.get("tasks", [])]


class LiveViewTest(unittest.TestCase):
    def setUp(self):
        self.tools = TaskTools()
        self.settings = AssistantSettings(MemoryPreferences())
        self.live = LiveView()

    def round(self, *names_and_args):
        log = []
        for name, arguments in names_and_args:
            call = ToolCall(name, arguments, f"c{len(log)}")
            log.append((call, self.tools.call_tool(name, arguments)))
        return self.live.after_round(log, self.tools, self.settings, NOW)

    def test_query_shows_its_data_and_is_remembered(self):
        view = self.round(("list_tasks", {"list": "Privat"}))
        self.assertEqual(titles(view), ["Steuer"])
        self.assertEqual([(call.name, call.arguments) for call in self.live.calls], [("list_tasks", {"list": "Privat"})])

    def test_change_in_later_round_reloads_the_view(self):
        self.round(("list_tasks", {}))
        view = self.round(("update_task", {"task_id": "l::1", "title": "Steuer 2026"}))
        self.assertEqual(titles(view), ["Steuer 2026"])
        self.assertEqual(self.tools.calls[-1], ("list_tasks", {}))   # mit denselben Argumenten

    def test_change_after_query_in_same_round_reloads(self):
        view = self.round(("list_tasks", {}), ("update_task", {"task_id": "l::1", "title": "Neu"}))
        self.assertEqual(titles(view), ["Neu"])

    def test_query_after_change_needs_no_reload(self):
        self.round(("update_task", {"task_id": "l::1", "title": "Neu"}), ("list_tasks", {}))
        self.assertEqual(self.tools.calls[-1][0], "list_tasks")
        self.assertEqual(len(self.tools.calls), 2)

    def test_unrelated_tools_keep_the_view(self):
        self.round(("list_tasks", {}))
        self.assertIsNone(self.round(("get_current_time", {})))

    def test_change_without_shown_view_does_nothing(self):
        self.assertIsNone(self.round(("update_task", {"task_id": "l::1", "title": "Neu"})))

    def test_failed_reload_keeps_the_view(self):
        self.round(("list_tasks", {}))
        self.tools.fail = True
        self.assertIsNone(self.live.refresh(self.tools, self.settings, NOW))

    def test_errors_are_no_changes(self):
        self.round(("list_tasks", {}))
        log = [(ToolCall("update_task", {}, "c"), ToolResult("kaputt", is_error=True))]
        self.assertIsNone(self.live.after_round(log, self.tools, self.settings, NOW))


class AssistantRefreshTest(unittest.TestCase):
    """Rückfragen vor riskanten Aufrufen sind keine Änderung; refresh_view lädt ohne Sprachmodell neu."""

    def test_refresh_view_and_confirm_request(self):
        from backend.assistant.gemini_assistant import GeminiAssistant
        from backend.assistant.model_assistant import CONFIRM_REQUEST
        from tests.assistant.test_gemini_assistant import FakeModel, calls, text

        tools = TaskTools()
        model = FakeModel(calls(ToolCall("list_tasks")), text("Hier"),
                          calls(ToolCall("delete_task", {"task_id": "l::1"})), text("Sicher?"))
        assistant = GeminiAssistant(model, tools, MemoryPreferences(gemini_model=model.models[0]))
        self.assertEqual(assistant.reply("Aufgaben?").view.template, "dashboard")
        reply = assistant.reply("lösch die")
        self.assertIn(CONFIRM_REQUEST, model.calls[-1][0][-1].content)
        self.assertIsNone(reply.view)   # nichts gelöscht, nichts neu geladen
        tools.titles["l::1"] = "Von woanders geändert"
        self.assertEqual(titles(assistant.refresh_view()), ["Von woanders geändert"])


if __name__ == "__main__":
    unittest.main()
