"""OllamaAssistant: Tool-Calling-Schleife, Verlauf und Modellwahl - mit Attrappen statt Ollama."""
import datetime
import unittest

from backend.assistant import Assistant, ModelSelection
from backend.assistant.llm import ChatMessage, ModelResponse, ToolCall
from backend.assistant.ollama import ModelInfo, OllamaError
from backend.assistant.ollama_assistant import MODEL_PREFERENCE, OllamaAssistant
from backend.assistant.tools import Attachment, CompositeToolProvider, ToolResult, ToolSpec
from backend.views import START_VIEW


class FakeModel:
    """Spielt vorbereitete Antworten ab und merkt sich, was es bekommen hat."""

    def __init__(self, *responses, installed=("llama3.2",), name="", cloud=()):
        self.responses = list(responses)
        self.calls = []
        self.name = name
        self._installed = list(installed)
        self._cloud = list(cloud)

    def chat(self, messages, tools=()):
        self.calls.append((list(messages), list(tools)))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return ModelResponse(response)

    def installed(self):
        return self._installed

    def cloud_models(self):
        return [ModelInfo(name, True, True) for name in self._cloud]

    def available_models(self):
        return [ModelInfo(name, name != "gemma") for name in self._installed] + self.cloud_models()

    def selectable(self):
        return [info.name for info in self.available_models()]


class EchoTools:
    def __init__(self):
        self.calls = []

    def list_tools(self):
        return [ToolSpec("echo", "Gibt den Text zurück", {"type": "object"})]

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return ToolResult(f"echo: {arguments.get('text')}")


class MemoryPreferences:
    def __init__(self, **values):
        self.values = dict(values)

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value

    def all(self):
        return dict(self.values)


def text(content):
    return ChatMessage("assistant", content)


def calls(*tool_calls):
    return ChatMessage("assistant", "", tuple(tool_calls))


FIXED_NOW = datetime.datetime(2026, 10, 14, 9, 30)


def make(model, tools=None, preferences=None, **kwargs):
    return OllamaAssistant(model, tools or EchoTools(), preferences or MemoryPreferences(),
                           clock=lambda: FIXED_NOW, **kwargs)


class ReplyTest(unittest.TestCase):
    def test_implements_protocols(self):
        assistant = make(FakeModel())
        self.assertIsInstance(assistant, Assistant)
        self.assertIsInstance(assistant, ModelSelection)

    def test_plain_answer_without_view(self):
        model = FakeModel(text("  Hallo!  "))
        reply = make(model).reply("Hi")
        self.assertEqual(reply.text, "Hallo!")
        self.assertIsNone(reply.view)
        messages, tools = model.calls[0]
        self.assertEqual(messages[0].role, "system")
        self.assertIn("Mittwoch, der 14.10.2026, 09:30 Uhr", messages[0].content)
        self.assertEqual(messages[1], ChatMessage("user", "Hi"))
        self.assertEqual([t.name for t in tools], ["echo"])

    def test_tool_call_loop(self):
        tools = EchoTools()
        model = FakeModel(calls(ToolCall("echo", {"text": "a"}), ToolCall("echo", {"text": "b"})),
                          text("Fertig"))
        reply = make(model, tools).reply("Mach was")

        self.assertEqual(reply.text, "Fertig")
        self.assertEqual(tools.calls, [("echo", {"text": "a"}), ("echo", {"text": "b"})])
        second_round = model.calls[1][0]
        self.assertEqual(second_round[-2:], [ChatMessage("tool", "echo: a", tool_name="echo"),
                                             ChatMessage("tool", "echo: b", tool_name="echo")])
        self.assertEqual(reply.view.data["title"], "Verwendete Werkzeuge")
        self.assertEqual(reply.view.data["rows"][0], ["echo", '{"text": "a"}', "echo: a"])
        self.assertEqual(reply.attachments, ())

    def test_attachments_of_all_tool_calls_once(self):
        plan = Attachment("plan.pdf", "file:///C:/a/plan.pdf")
        foto = Attachment("foto.jpg", "file:///C:/a/foto.jpg")

        class FileTools(EchoTools):
            def call_tool(self, name, arguments):
                files = (plan, foto) if arguments.get("text") == "mail" else (plan,)
                return ToolResult("[Datei im Chat angehängt]", attachments=files)

        model = FakeModel(calls(ToolCall("echo", {"text": "mail"})), calls(ToolCall("echo", {"text": "pdf"})),
                          text("Hier ist die Mail"))
        self.assertEqual(make(model, FileTools()).reply("Lies die Mail").attachments, (plan, foto))

    def test_unknown_tool_is_reported_to_model(self):
        model = FakeModel(calls(ToolCall("gibts_nicht")), text("Sorry"))
        reply = make(model, CompositeToolProvider([EchoTools()])).reply("x")
        tool_message = model.calls[1][0][-1]
        self.assertEqual(tool_message.role, "tool")
        self.assertIn("Fehler: Unbekanntes Werkzeug", tool_message.content)
        self.assertIn("Fehler:", reply.view.data["rows"][0][2])

    def test_stops_after_max_rounds_and_forces_answer(self):
        loop = calls(ToolCall("echo", {"text": "x"}))
        model = FakeModel(loop, loop, text("Antwort ohne Werkzeuge"))
        reply = make(model, max_tool_rounds=2).reply("x")
        self.assertEqual(reply.text, "Antwort ohne Werkzeuge")
        self.assertEqual([len(tools) for _, tools in model.calls], [1, 1, 0])

    def test_gives_up_if_model_keeps_calling_tools(self):
        loop = calls(ToolCall("echo", {"text": "x"}))
        reply = make(FakeModel(loop, loop), max_tool_rounds=1).reply("x")
        self.assertIn("zu viele Werkzeuge", reply.text)

    def test_empty_answer(self):
        self.assertIn("keine Antwort", make(FakeModel(text(""))).reply("x").text)

    def test_history_is_kept_between_messages(self):
        model = FakeModel(text("Eins"), text("Zwei"))
        assistant = make(model)
        assistant.reply("a")
        assistant.reply("b")
        self.assertEqual([m.content for m in model.calls[1][0][1:]], ["a", "Eins", "b"])

    def test_history_is_trimmed_at_user_messages(self):
        model = FakeModel(calls(ToolCall("echo", {"text": "x"})), text("Eins"), text("Zwei"))
        assistant = make(model, max_history=3)
        assistant.reply("a")   # user, assistant(call), tool, assistant = 4 > 3
        self.assertEqual(assistant.history, [])
        assistant.reply("b")
        self.assertEqual([m.role for m in assistant.history], ["user", "assistant"])

    def test_ollama_error_is_answer_and_history_rolled_back(self):
        assistant = make(FakeModel(OllamaError("kaputt")))
        reply = assistant.reply("x")
        self.assertIn("kaputt", reply.text)
        self.assertEqual(assistant.history, [])

    def test_commands_bypass_model(self):
        model = FakeModel()
        self.assertEqual(make(model).reply(" HILFE ").view.data["title"], "Befehle")
        self.assertEqual(model.calls, [])

    def test_new_clears_history(self):
        assistant = make(FakeModel(text("Eins")))
        assistant.reply("a")
        reply = assistant.reply("neu")
        self.assertEqual(assistant.history, [])
        self.assertIs(reply.view, START_VIEW)

    def test_preferences_and_skill_instructions_in_system_message(self):
        model = FakeModel(text("ok"))
        prefs = MemoryPreferences(wohnort="Mannheim", **{MODEL_PREFERENCE: "llama3.2"})
        make(model, preferences=prefs, instructions="Briefing kurz halten.").reply("x")
        system = model.calls[0][0][0].content
        self.assertIn('"wohnort": "Mannheim"', system)
        self.assertNotIn(MODEL_PREFERENCE, system)
        self.assertTrue(system.endswith("Briefing kurz halten."))


class ModelSelectionTest(unittest.TestCase):
    def test_picks_first_installed_model(self):
        model = FakeModel(text("ok"), installed=["a", "b"])
        make(model).reply("x")
        self.assertEqual(model.name, "a")

    def test_prefers_saved_model(self):
        model = FakeModel(installed=["a", "b"])
        self.assertEqual(make(model, preferences=MemoryPreferences(**{MODEL_PREFERENCE: "b"})).current_model(), "b")

    def test_saved_model_no_longer_installed(self):
        model = FakeModel(installed=["a"])
        self.assertEqual(make(model, preferences=MemoryPreferences(**{MODEL_PREFERENCE: "weg"})).current_model(), "a")

    def test_configured_model_wins(self):
        self.assertEqual(make(FakeModel(installed=["a"], name="fest")).current_model(), "fest")

    def test_no_model_installed(self):
        reply = make(FakeModel(installed=[])).reply("x")
        self.assertIn("ollama pull", reply.text)

    def test_ollama_not_running(self):
        model = FakeModel()
        model.installed = lambda: (_ for _ in ()).throw(OllamaError("nicht erreichbar"))
        self.assertIn("nicht erreichbar", make(model).reply("x").text)

    def test_select_model_is_saved(self):
        prefs = MemoryPreferences()
        model = FakeModel(installed=["a", "b"])
        assistant = make(model, preferences=prefs)
        assistant.select_model("b")
        self.assertEqual(model.name, "b")
        self.assertEqual(prefs.get(MODEL_PREFERENCE), "b")

    def test_select_unknown_model(self):
        with self.assertRaisesRegex(ValueError, "weder installiert noch in der Ollama-Cloud"):
            make(FakeModel(installed=["a"])).select_model("b")

    def test_available_models(self):
        models = make(FakeModel(installed=["gemma", "qwen3"], cloud=["gpt-oss:120b-cloud"])).available_models()
        self.assertEqual(models, [{"name": "gemma", "tools": False, "cloud": False},
                                  {"name": "qwen3", "tools": True, "cloud": False},
                                  {"name": "gpt-oss:120b-cloud", "tools": True, "cloud": True}])

    def test_saved_cloud_model_without_pull(self):
        model = FakeModel(installed=["a"], cloud=["gemma4:31b-cloud"])
        prefs = MemoryPreferences(**{MODEL_PREFERENCE: "gemma4:31b-cloud"})
        self.assertEqual(make(model, preferences=prefs).current_model(), "gemma4:31b-cloud")

    def test_models_command_lists_local_and_cloud(self):
        reply = make(FakeModel(installed=["a"], cloud=["b-cloud"])).reply("modelle")
        self.assertEqual(reply.view.data["rows"], [["▶ a", "Lokal", "ja"], ["b-cloud", "Cloud", "ja"]])

    def test_model_command_accepts_cloud_name_without_suffix(self):
        model = FakeModel(installed=["a"], cloud=["gemma4:31b-cloud"])
        self.assertIn("gemma4:31b-cloud", make(model).reply("modell gemma4:31b").text)
        self.assertEqual(model.name, "gemma4:31b-cloud")

    def test_model_command_unknown_model(self):
        self.assertIn('"modelle"', make(FakeModel(installed=["a"])).reply("modell gibtsnicht").text)

    def test_help_lists_model_commands(self):
        rows = make(FakeModel()).reply("hilfe").view.data["rows"]
        self.assertIn("modelle", [row[0] for row in rows])


if __name__ == "__main__":
    unittest.main()
