import unittest

from backend.assistant.tools import (
    CompositeToolProvider,
    DuplicateToolError,
    ToolProvider,
    ToolResult,
    ToolSpec,
    UnknownToolError,
)


class FakeIntegration:
    """Steht für eine Integration wie Calendar oder Wetter."""

    def __init__(self, prefix, tool_names):
        self.prefix = prefix
        self.tool_names = tool_names

    def list_tools(self):
        return [ToolSpec(name, f"{self.prefix}: {name}") for name in self.tool_names]

    def call_tool(self, name, arguments):
        return ToolResult(f"{self.prefix}.{name}({arguments})")


class CompositeToolProviderTest(unittest.TestCase):
    def setUp(self):
        self.calendar = FakeIntegration("calendar", ["next_event"])
        self.weather = FakeIntegration("weather", ["forecast", "current"])
        self.tools = CompositeToolProvider([self.calendar, self.weather])

    def test_is_a_tool_provider(self):
        self.assertIsInstance(self.tools, ToolProvider)

    def test_lists_tools_of_all_providers(self):
        self.assertEqual([t.name for t in self.tools.list_tools()], ["next_event", "forecast", "current"])

    def test_routes_call_to_owning_provider(self):
        self.assertEqual(self.tools.call_tool("forecast", {"city": "Mannheim"}).content,
                         "weather.forecast({'city': 'Mannheim'})")
        self.assertEqual(self.tools.call_tool("next_event", {}).content, "calendar.next_event({})")

    def test_unknown_tool_raises(self):
        with self.assertRaises(UnknownToolError):
            self.tools.call_tool("does_not_exist", {})

    def test_duplicate_tool_names_raise(self):
        tools = CompositeToolProvider([self.calendar, FakeIntegration("other", ["next_event"])])
        with self.assertRaises(DuplicateToolError):
            tools.list_tools()

    def test_tools_are_read_fresh_on_each_call(self):
        self.weather.tool_names.append("radar")   # z. B. MCP-Server mit neuem Tool
        self.assertIn("radar", [t.name for t in self.tools.list_tools()])

    def test_empty_composite(self):
        self.assertEqual(CompositeToolProvider([]).list_tools(), [])


if __name__ == "__main__":
    unittest.main()
