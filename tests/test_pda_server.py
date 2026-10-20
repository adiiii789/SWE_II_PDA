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
        cls.provider = MCPToolProvider("pda", "python", [PDA_SERVER], env=env, cwd=config.ROOT_DIR, timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.provider.close()

    def test_tools_with_schema_from_type_annotations(self):
        tools = {spec.name: spec for spec in self.provider.list_tools()}
        self.assertEqual(set(tools), {"get_current_time", "calculate", "send_email", "list_emails", "read_email",
                                       "read_attachment"})
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


if __name__ == "__main__":
    unittest.main()
