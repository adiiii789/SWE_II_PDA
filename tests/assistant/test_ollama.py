"""OllamaModel: Übersetzung ins JSON-Format von Ollama, ohne echtes Ollama (Client-Attrappe)."""
import io
import json
import unittest
import urllib.error
from unittest import mock

from backend.assistant.llm import ChatMessage, LanguageModel, ToolCall
from backend.assistant.ollama import OllamaClient, OllamaError, OllamaModel
from backend.assistant.tools import ToolSpec


class FakeClient:
    def __init__(self, responses=None, tags=(), capabilities=None):
        self.responses = list(responses or [])
        self.tags = tags
        self.capabilities = capabilities or {}
        self.posts = []

    def get(self, path):
        assert path == "/api/tags"
        return {"models": [{"name": name} for name in self.tags]}

    def post(self, path, body):
        self.posts.append((path, dict(body)))
        if path == "/api/show":
            caps = self.capabilities.get(body["model"])
            if isinstance(caps, Exception):
                raise caps
            return {} if caps is None else {"capabilities": caps}
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def answer(content="", tool_calls=None):
    message = {"role": "assistant", "content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return {"message": message}


class OllamaModelTest(unittest.TestCase):
    def test_implements_language_model(self):
        self.assertIsInstance(OllamaModel(FakeClient(), "m"), LanguageModel)

    def test_chat_sends_messages_tools_and_options(self):
        client = FakeClient([answer("Hallo")])
        model = OllamaModel(client, "llama3.2", {"temperature": 0})
        history = [
            ChatMessage("user", "Wie spät?"),
            ChatMessage("assistant", "", (ToolCall("get_time", {"tz": "CET"}),)),
            ChatMessage("tool", "12:00", tool_name="get_time"),
        ]
        response = model.chat(history, [ToolSpec("get_time", "Uhrzeit", {"type": "object"})])

        self.assertEqual(response.message, ChatMessage("assistant", "Hallo"))
        path, body = client.posts[0]
        self.assertEqual(path, "/api/chat")
        self.assertEqual(body["model"], "llama3.2")
        self.assertFalse(body["stream"])
        self.assertEqual(body["options"], {"temperature": 0})
        self.assertEqual(body["messages"][1]["tool_calls"],
                         [{"function": {"name": "get_time", "arguments": {"tz": "CET"}}}])
        self.assertEqual(body["messages"][2], {"role": "tool", "content": "12:00", "tool_name": "get_time"})
        self.assertEqual(body["tools"], [{"type": "function", "function": {
            "name": "get_time", "description": "Uhrzeit", "parameters": {"type": "object"}}}])

    def test_without_tools_no_tools_key(self):
        client = FakeClient([answer("x")])
        OllamaModel(client, "m").chat([ChatMessage("user", "hi")])
        self.assertNotIn("tools", client.posts[0][1])
        self.assertNotIn("options", client.posts[0][1])

    def test_empty_schema_gets_default(self):
        client = FakeClient([answer("x")])
        OllamaModel(client, "m").chat([ChatMessage("user", "hi")], [ToolSpec("t", "d")])
        self.assertEqual(client.posts[0][1]["tools"][0]["function"]["parameters"],
                         {"type": "object", "properties": {}})

    def test_parses_tool_calls_including_string_arguments(self):
        client = FakeClient([answer(tool_calls=[
            {"function": {"name": "a", "arguments": {"x": 1}}},
            {"function": {"name": "b", "arguments": '{"y": 2}'}},
            {"function": {"name": "c", "arguments": "kaputt"}},
            {"function": {"name": "d"}},
        ])])
        response = OllamaModel(client, "m").chat([ChatMessage("user", "hi")])
        self.assertTrue(response.wants_tools)
        self.assertEqual(response.message.tool_calls,
                         (ToolCall("a", {"x": 1}), ToolCall("b", {"y": 2}), ToolCall("c"), ToolCall("d")))

    def test_falls_back_without_tools_if_model_cannot_use_them(self):
        client = FakeClient([OllamaError("registry.ollama.ai/library/gemma:2b does not support tools"),
                             answer("ohne Werkzeuge")])
        response = OllamaModel(client, "gemma").chat([ChatMessage("user", "hi")], [ToolSpec("t", "d")])
        self.assertEqual(response.message.content, "ohne Werkzeuge")
        self.assertIn("tools", client.posts[0][1])
        self.assertNotIn("tools", client.posts[1][1])

    def test_other_errors_are_raised(self):
        client = FakeClient([OllamaError("model 'x' not found")])
        with self.assertRaisesRegex(OllamaError, "not found"):
            OllamaModel(client, "x").chat([ChatMessage("user", "hi")], [ToolSpec("t", "d")])

    def test_available_models_with_tool_support(self):
        client = FakeClient(tags=["qwen3", "gemma"], capabilities={
            "qwen3": ["completion", "tools"], "gemma": ["completion"]})
        infos = OllamaModel(client, "").available_models()
        self.assertEqual([(i.name, i.supports_tools) for i in infos], [("gemma", False), ("qwen3", True)])

    def test_unknown_capabilities_count_as_tool_support(self):
        client = FakeClient(tags=["old", "broken"], capabilities={"broken": OllamaError("x")})
        self.assertTrue(all(i.supports_tools for i in OllamaModel(client, "").available_models()))


class OllamaClientTest(unittest.TestCase):
    def _urlopen_returning(self, payload):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(payload).encode()
        return mock.patch("urllib.request.urlopen", return_value=response)

    def test_post_sends_json_and_parses_answer(self):
        with self._urlopen_returning({"ok": 1}) as urlopen:
            result = OllamaClient("http://host:1/", 5).post("/api/chat", {"a": "ä"})
        self.assertEqual(result, {"ok": 1})
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://host:1/api/chat")
        self.assertEqual(json.loads(request.data), {"a": "ä"})
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 5)

    def test_get(self):
        with self._urlopen_returning({"models": []}):
            self.assertEqual(OllamaClient("http://h", 1).get("/api/tags"), {"models": []})

    def test_http_error_message_from_ollama(self):
        error = urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO(b'{"error": "model not found"}'))
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaisesRegex(OllamaError, "^model not found$"):
                OllamaClient("http://h", 1).get("/api/tags")

    def test_http_error_without_json(self):
        error = urllib.error.HTTPError("u", 500, "Server Error", {}, io.BytesIO(b"oops"))
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaisesRegex(OllamaError, "HTTP 500"):
                OllamaClient("http://h", 1).get("/api/tags")

    def test_not_reachable(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            with self.assertRaisesRegex(OllamaError, "nicht erreichbar"):
                OllamaClient("http://h", 1).get("/api/tags")


if __name__ == "__main__":
    unittest.main()
