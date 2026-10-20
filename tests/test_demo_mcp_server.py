"""Demo-MCP-Server direkt (ohne Unterprozess): Protokoll-Antworten und sicheres Rechnen."""
import importlib.util
import sys
import unittest

from backend import config

sys.path.insert(0, str(config.ROOT_DIR / "mcp_servers"))   # wie beim Start als Skript: basic_tools, mailer
_spec = importlib.util.spec_from_file_location("demo_server", config.ROOT_DIR / "mcp_servers" / "demo_server.py")
demo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(demo)


def call(name, **arguments):
    return demo.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                        "params": {"name": name, "arguments": arguments}})["result"]


class DemoServerTest(unittest.TestCase):
    def test_initialize_and_notifications(self):
        result = demo.handle({"id": 1, "method": "initialize", "params": {"protocolVersion": "x"}})["result"]
        self.assertEqual(result["protocolVersion"], "x")
        self.assertIsNone(demo.handle({"method": "notifications/initialized"}))
        self.assertEqual(demo.handle({"id": 2, "method": "ping"})["result"], {})

    def test_calculate(self):
        self.assertEqual(call("calculate", expression="-2 + 3 * (4 % 3) ** 2 / 1")["content"][0]["text"],
                         "-2 + 3 * (4 % 3) ** 2 / 1 = 1.0")

    def test_calculate_rejects_code(self):
        result = call("calculate", expression="open('x')")
        self.assertTrue(result["isError"])

    def test_unknown_method(self):
        self.assertEqual(demo.handle({"id": 3, "method": "resources/list"})["error"]["code"], -32601)


if __name__ == "__main__":
    unittest.main()
