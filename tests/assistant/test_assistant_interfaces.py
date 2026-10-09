"""Prüft, dass die Schnittstellen für Ollama (LanguageModel) und MCP (ToolProvider)
von einfachen Test-Implementierungen erfüllt werden können."""
import unittest

from backend.assistant.llm import ChatMessage, LanguageModel, ModelResponse, ToolCall
from backend.assistant.tools import ToolProvider, ToolResult, ToolSpec


class FakeModel:
    def chat(self, messages, tools=()):
        return ModelResponse(ChatMessage("assistant", f"{len(messages)} Nachrichten, {len(tools)} Tools"))


class FakeTools:
    def list_tools(self):
        return [ToolSpec("echo", "Gibt den Text zurück", {"type": "object"})]

    def call_tool(self, name, arguments):
        return ToolResult(arguments.get("text", ""))


class InterfaceTest(unittest.TestCase):
    def test_fakes_satisfy_protocols(self):
        self.assertIsInstance(FakeModel(), LanguageModel)
        self.assertIsInstance(FakeTools(), ToolProvider)

    def test_model_and_tools_work_together(self):
        tools = FakeTools()
        response = FakeModel().chat([ChatMessage("user", "Hallo")], tools.list_tools())
        self.assertEqual(response.message.content, "1 Nachrichten, 1 Tools")
        self.assertEqual(tools.call_tool("echo", {"text": "x"}), ToolResult("x"))

    def test_wants_tools(self):
        plain = ModelResponse(ChatMessage("assistant", "Hi"))
        with_call = ModelResponse(ChatMessage("assistant", "", (ToolCall("echo", {"text": "x"}),)))
        self.assertFalse(plain.wants_tools)
        self.assertTrue(with_call.wants_tools)


if __name__ == "__main__":
    unittest.main()
