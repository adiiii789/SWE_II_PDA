"""MCPToolProvider gegen einen echten MCP-Server (mcp_servers/demo_server.py als Unterprozess)."""
import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from backend import config
from backend.assistant.tools import Attachment, CompositeToolProvider, ToolProvider, ToolResult
from backend.integrations.mcp_client import MCPToolProvider, _attachments, _content_to_text, load_mcp_servers

DEMO_SERVER = str(config.ROOT_DIR / "mcp_servers" / "demo_server.py")


def script_server(source: str) -> MCPToolProvider:
    """MCP-Server aus einem kurzen Python-Skript (für Sonderfälle)."""
    return MCPToolProvider("test", sys.executable, ["-c", textwrap.dedent(source)], timeout=10)


class DemoServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.provider = MCPToolProvider("demo", "python", [DEMO_SERVER], timeout=10)

    @classmethod
    def tearDownClass(cls):
        cls.provider.close()

    def test_implements_tool_provider(self):
        self.assertIsInstance(self.provider, ToolProvider)

    def test_list_tools(self):
        tools = {spec.name: spec for spec in self.provider.list_tools()}
        self.assertEqual(set(tools), {"get_current_time", "calculate"})
        self.assertEqual(tools["calculate"].input_schema["required"], ["expression"])

    def test_call_tool(self):
        self.assertEqual(self.provider.call_tool("calculate", {"expression": "(3 + 4) * 2"}),
                         ToolResult("(3 + 4) * 2 = 14"))
        self.assertIn("Uhr", self.provider.call_tool("get_current_time", {}).content)

    def test_tool_error_is_result(self):
        result = self.provider.call_tool("calculate", {"expression": "__import__('os')"})
        self.assertTrue(result.is_error)

    def test_unknown_tool_is_error_result(self):
        result = self.provider.call_tool("nope", {})
        self.assertTrue(result.is_error)
        self.assertIn("Unbekannt", result.content)

    def test_works_inside_composite(self):
        composite = CompositeToolProvider([self.provider])
        self.assertEqual(composite.call_tool("calculate", {"expression": "2**10"}).content, "2**10 = 1024")

    def test_restarts_after_crash(self):
        provider = MCPToolProvider("demo", "python", [DEMO_SERVER], timeout=10)
        self.assertTrue(provider.list_tools())
        provider._process.kill()
        provider._process.wait()
        self.assertEqual(provider.call_tool("calculate", {"expression": "1+1"}).content, "1+1 = 2")
        provider.close()


class FailureTest(unittest.TestCase):
    def test_missing_command_gives_no_tools(self):
        provider = MCPToolProvider("kaputt", "gibt-es-nicht-12345")
        self.assertEqual(provider.list_tools(), [])
        self.assertTrue(provider.call_tool("x", {}).is_error)

    def test_server_exits_immediately(self):
        provider = script_server("import sys; sys.exit(1)")
        self.assertEqual(provider.list_tools(), [])

    def test_timeout(self):
        provider = script_server("import time; time.sleep(30)")
        provider.timeout = 0.5
        result = provider.call_tool("x", {})
        self.assertTrue(result.is_error)
        self.assertIn("keine Antwort", result.content)
        provider.close()

    def test_handles_ping_notifications_noise_and_pagination(self):
        provider = script_server("""
            import json, sys
            def send(m): print(json.dumps(m), flush=True)
            for line in sys.stdin:
                m = json.loads(line)
                if "id" not in m or "method" not in m:   # Benachrichtigung oder Antwort auf unsere Anfrage
                    continue
                if m["method"] == "initialize":
                    print("kein JSON", flush=True)
                    send({"jsonrpc": "2.0", "method": "notifications/message", "params": {}})
                    send({"jsonrpc": "2.0", "id": "srv-1", "method": "ping"})
                    send({"jsonrpc": "2.0", "id": "srv-2", "method": "sampling/createMessage"})
                    send({"jsonrpc": "2.0", "id": m["id"], "result": {}})
                elif m["method"] == "tools/list":
                    page2 = m["params"].get("cursor") == "p2"
                    tools = [{"name": "b"}] if page2 else [{"name": "a", "description": "A"}]
                    result = {"tools": tools} if page2 else {"tools": tools, "nextCursor": "p2"}
                    send({"jsonrpc": "2.0", "id": m["id"], "result": result})
                else:
                    send({"jsonrpc": "2.0", "id": m["id"], "error": {"code": 1, "message": "nein"}})
        """)
        tools = provider.list_tools()
        self.assertEqual([(t.name, t.description) for t in tools], [("a", "A"), ("b", "")])
        result = provider.call_tool("a", {})
        self.assertEqual(result, ToolResult("tools/call: nein", is_error=True))
        provider.close()


class ContentTest(unittest.TestCase):
    def test_content_blocks_to_text(self):
        result = {"content": [{"type": "text", "text": "a"}, {"type": "image", "data": "..."},
                              {"type": "resource", "resource": {"text": "r"}}]}
        self.assertEqual(_content_to_text(result), "a\n[image-Inhalt nicht darstellbar]\nr")

    def test_resource_links_become_attachments(self):
        result = {"content": [{"type": "text", "text": "Mail"},
                              {"type": "resource_link", "name": "plan.pdf", "uri": "file:///C:/a/plan.pdf",
                               "mimeType": "application/pdf", "size": 3},
                              {"type": "resource_link", "name": "ohne uri"}]}
        self.assertEqual(_content_to_text(result).splitlines()[:2], ["Mail", "[Datei im Chat angehängt: plan.pdf]"])
        self.assertEqual(_attachments(result), (Attachment("plan.pdf", "file:///C:/a/plan.pdf", "application/pdf", 3),))

    def test_structured_content(self):
        self.assertEqual(_content_to_text({"content": [], "structuredContent": {"x": 1}}), '{"x": 1}')


class LoadServersTest(unittest.TestCase):
    def test_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mcp_servers.json"
            path.write_text(json.dumps({"mcpServers": {
                "a": {"command": "npx", "args": ["-y", "x"], "env": {"K": "V"}, "cwd": "sub"},
                "b": {"command": "uvx", "disabled": True},
            }}), encoding="utf-8")
            servers = load_mcp_servers(path, Path(tmp))
        self.assertEqual(len(servers), 1)
        self.assertEqual((servers[0].name, servers[0].command, servers[0].args, servers[0].env),
                         ("a", "npx", ["-y", "x"], {"K": "V"}))
        self.assertEqual(servers[0].cwd, Path(tmp) / "sub")

    def test_missing_file(self):
        self.assertEqual(load_mcp_servers(Path("gibt/es/nicht.json"), Path(".")), [])

    def test_project_config_is_valid(self):
        self.assertTrue(load_mcp_servers(config.MCP_SERVERS_FILE, config.ROOT_DIR))


if __name__ == "__main__":
    unittest.main()
