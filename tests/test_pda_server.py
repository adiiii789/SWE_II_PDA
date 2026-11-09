"""Integration: unser MCPToolProvider gegen den echten SDK-Server mcp_servers/pda_server.py.

Wird übersprungen, solange das MCP-SDK nicht installiert ist (pip install -r requirements.txt).
"""
import importlib.util
import unittest

from backend import config
from backend.integrations.mcp_client import MCPToolProvider

PDA_SERVER = str(config.ROOT_DIR / "mcp_servers" / "pda_server.py")


@unittest.skipUnless(importlib.util.find_spec("mcp"), "MCP-SDK nicht installiert")
class PdaServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Mail-Einstellungen leeren, damit der Test nie wirklich etwas versendet oder abruft.
        env = {key: "" for key in ("PDA_SMTP_HOST", "PDA_SMTP_USER", "PDA_SMTP_PASSWORD", "PDA_MAIL_RECIPIENTS",
                                   "PDA_IMAP_HOST", "PDA_IMAP_USER", "PDA_IMAP_PASSWORD")}
        env["PDA_GOOGLE_DIR"] = str(config.ROOT_DIR / "tests" / "gibt-es-nicht")   # nie der echte Kalender
        cls.provider = MCPToolProvider("pda", "python", [PDA_SERVER], env=env, cwd=config.ROOT_DIR, timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.provider.close()

    def test_tools_with_schema_from_type_annotations(self):
        tools = {spec.name: spec for spec in self.provider.list_tools()}
        self.assertEqual(set(tools), {"get_current_time", "calculate", "send_email", "list_emails", "read_email",
                                       "read_attachment", "list_calendar_events", "create_calendar_event",
                                       "update_calendar_event", "delete_calendar_event", "find_free_time",
                                       "respond_to_calendar_invitation", "list_tasks", "create_task", "update_task", "complete_task", "delete_task",
                                       "move_task", "create_task_list"})
        self.assertNotIn("required", tools["list_tasks"].input_schema)
        for name in ("update_task", "complete_task", "delete_task", "move_task"):
            self.assertEqual(tools[name].input_schema["required"], ["task_id"])
        self.assertEqual(tools["create_task"].input_schema["required"], ["title"])
        self.assertNotIn("required", tools["list_calendar_events"].input_schema)
        self.assertEqual(set(tools["create_calendar_event"].input_schema["required"]), {"title", "start"})
        self.assertIn("guests", tools["create_calendar_event"].input_schema["properties"])
        for name in ("update_calendar_event", "delete_calendar_event"):
            self.assertEqual(tools[name].input_schema["required"], ["event_id"])
        self.assertEqual(set(tools["respond_to_calendar_invitation"].input_schema["required"]), {"event_id", "response"})
        self.assertNotIn("required", tools["find_free_time"].input_schema)
        schema = tools["send_email"].input_schema
        self.assertEqual(set(schema["required"]), {"subject", "body"})
        self.assertIn("to", schema["properties"])
        self.assertEqual(tools["read_email"].input_schema["required"], ["uid"])
        self.assertNotIn("required", tools["list_emails"].input_schema)
        self.assertEqual(tools["read_attachment"].input_schema["required"], ["uid"])
        self.assertEqual(set(tools["read_attachment"].input_schema["properties"]), {"uid", "index", "part"})

    def test_calculate(self):
        self.assertEqual(self.provider.call_tool("calculate", {"expression": "6 * 7"}).content, "6 * 7 = 42")

    def test_invalid_expression_message_reaches_model(self):
        result = self.provider.call_tool("calculate", {"expression": "open('x')"})
        self.assertTrue(result.is_error)
        self.assertIn("Ungültiger Ausdruck", result.content)

    def test_tool_error_message_reaches_model(self):
        result = self.provider.call_tool("send_email", {"subject": "Hi", "body": "Text"})
        self.assertTrue(result.is_error)
        self.assertIn("nicht eingerichtet", result.content)

    def test_read_tools_report_missing_settings(self):
        for name, arguments in (("list_emails", {}), ("read_email", {"uid": "1"}), ("read_attachment", {"uid": "1"})):
            result = self.provider.call_tool(name, arguments)
            self.assertTrue(result.is_error)
            self.assertIn("Mail-Abruf ist nicht eingerichtet", result.content)

    def test_calendar_tools_report_missing_login(self):
        for name, arguments in (("list_calendar_events", {}),
                                ("create_calendar_event", {"title": "X", "start": "2026-11-10"}),
                                ("update_calendar_event", {"event_id": "a::b", "title": "X"}),
                                ("delete_calendar_event", {"event_id": "a::b"}), ("find_free_time", {}),
                                ("respond_to_calendar_invitation", {"event_id": "a::b", "response": "accepted"})):
            result = self.provider.call_tool(name, arguments)
            self.assertTrue(result.is_error)
            self.assertIn("Google Kalender ist nicht eingerichtet", result.content)

    def test_guests_must_be_approved_contacts(self):
        result = self.provider.call_tool("create_calendar_event", {"title": "X", "start": "2026-11-10",
                                                                   "guests": ["fremd@example.com"]})
        self.assertTrue(result.is_error)
        self.assertIn("Mailversand ist nicht eingerichtet", result.content)

    def test_task_tools_report_missing_login(self):
        for name, arguments in (("list_tasks", {}), ("create_task", {"title": "X"}), ("complete_task", {"task_id": "a::b"}),
                                ("update_task", {"task_id": "a::b", "title": "X"}), ("delete_task", {"task_id": "a::b"}),
                                ("move_task", {"task_id": "a::b", "target_list": "X"}),
                                ("create_task_list", {"title": "X"})):
            result = self.provider.call_tool(name, arguments)
            self.assertTrue(result.is_error)
            self.assertIn("Google Tasks ist nicht eingerichtet", result.content)


if __name__ == "__main__":
    unittest.main()
