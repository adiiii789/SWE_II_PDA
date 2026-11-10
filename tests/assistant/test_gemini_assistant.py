"""GeminiAssistant: Tool-Calling-Schleife, Verlauf und Modellwahl - mit Attrappen statt Gemini."""
import datetime
import unittest

from backend.assistant import Assistant, ConsultingAssistant, ModelSelection, ProactiveAssistant
from backend.assistant.llm import ChatMessage, ModelResponse, ToolCall
from backend.assistant.gemini import MODELS, GeminiError
from backend.assistant.llm import ModelInfo
from backend.assistant.gemini_assistant import MODEL_PREFERENCE, PROACTIVE_TRIGGER, GeminiAssistant
from backend.assistant.tools import Attachment, CompositeToolProvider, ToolResult, ToolSpec
from backend.views import START_VIEW


class FakeModel:
    """Spielt vorbereitete Antworten ab und merkt sich, was es bekommen hat."""

    def __init__(self, *responses, models=MODELS, name=""):
        self.responses = list(responses)
        self.calls = []
        self.name = name
        self.models = list(models)
        self.default_name = self.models[0]

    def chat(self, messages, tools=()):
        self.calls.append((list(messages), list(tools)))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return ModelResponse(response)

    def available_models(self):
        return [ModelInfo(name, True, True) for name in self.models]

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
    return GeminiAssistant(model, tools or EchoTools(), preferences or MemoryPreferences(),
                           clock=lambda: FIXED_NOW, **kwargs)


class WatcherSupportTest(unittest.TestCase):
    def test_consult_has_no_history_or_tools_and_leaves_no_trace(self):
        model = FakeModel(text("  Nein  "))
        assistant = make(model)
        assistant.history.append(ChatMessage("user", "privat"))
        self.assertIsInstance(assistant, ConsultingAssistant)
        self.assertEqual(assistant.consult("Wichtig?"), "Nein")
        self.assertEqual(model.calls, [([ChatMessage("user", "Wichtig?")], [])])
        self.assertEqual(len(assistant.history), 1)

    def test_consult_without_model(self):
        self.assertIsNone(make(FakeModel(GeminiError("weg"))).consult("Frage"))
        self.assertIsNone(make(FakeModel(text("   "))).consult("Frage"))

    def test_internal_tools_stay_hidden_and_cannot_be_called(self):
        class Tools(EchoTools):
            def list_tools(self):
                return [*super().list_tools(), ToolSpec("watch_new_emails", "intern", {"type": "object"})]

        tools = Tools()
        model = FakeModel(calls(ToolCall("watch_new_emails", {})), text("Fertig"))
        make(model, tools).reply("Hi")
        self.assertEqual([tool.name for tool in model.calls[0][1]], ["echo"])
        self.assertEqual(tools.calls, [])

    def test_proactive_settings_are_not_personal_facts(self):
        model = FakeModel(text("Hallo"))
        make(model, preferences=MemoryPreferences(proactive_settings={"mail": {"criteria": "GEHEIMES_KRITERIUM"}})).reply("Hi")
        self.assertNotIn("GEHEIMES_KRITERIUM", model.calls[0][0][0].content)


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

    def test_gemini_error_is_answer_and_history_rolled_back(self):
        assistant = make(FakeModel(GeminiError("kaputt")))
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


class ConfirmationTest(unittest.TestCase):
    """Riskante Werkzeuge laufen erst, wenn die nächste Nachricht des Nutzers zustimmt."""

    CALL = ToolCall("delete_task", {"task_id": "l::t"})

    def setUp(self):
        self.tools = EchoTools()

    def turn(self, *calls_):
        return [calls(call) for call in calls_] + [text("Antwort")]

    def run_turns(self, *turns):
        """turns: (Nachricht des Nutzers, Aufrufe des Modells in dieser Runde)"""
        model = FakeModel(*[response for _, calls_ in turns for response in self.turn(*calls_)])
        assistant = make(model, self.tools)
        for message, _ in turns:
            assistant.reply(message)
        return model

    def test_first_call_is_only_proposed(self):
        model = self.run_turns(("Lösch die Aufgabe", [self.CALL]))
        self.assertEqual(self.tools.calls, [])
        self.assertIn("NICHT ausgeführt", model.calls[1][0][-1].content)

    def test_agreement_in_next_message_runs_it(self):
        for answer in ("ja", "Ja, bitte löschen", "ok", "Mach das", "lösche sie"):
            with self.subTest(answer=answer):
                self.tools = EchoTools()
                self.run_turns(("Lösch die Aufgabe", [self.CALL]), (answer, [self.CALL]))
                self.assertEqual(self.tools.calls, [("delete_task", {"task_id": "l::t"})])

    def test_repeating_it_in_the_same_turn_does_not_help(self):
        self.run_turns(("Fasse meine Mails zusammen", [self.CALL, self.CALL]))
        self.assertEqual(self.tools.calls, [])

    def test_other_answers_do_not_run_it(self):
        for answer in ("nein", "bitte nicht", "ok, doch nicht", "danke", "Was gibt es Neues?"):
            with self.subTest(answer=answer):
                self.run_turns(("Lösch die Aufgabe", [self.CALL]), (answer, [self.CALL]))
                self.assertEqual(self.tools.calls, [])

    def test_agreement_covers_only_the_proposed_call(self):
        other = ToolCall("delete_task", {"task_id": "l::anders"})
        self.run_turns(("Lösch die Aufgabe", [self.CALL]), ("ja", [other]))
        self.assertEqual(self.tools.calls, [])

    def test_agreement_is_used_up(self):
        self.run_turns(("Lösch die Aufgabe", [self.CALL]), ("ja", [self.CALL, self.CALL]))
        self.assertEqual(len(self.tools.calls), 1)

    def test_agreement_only_counts_for_the_next_message(self):
        self.run_turns(("Lösch die Aufgabe", [self.CALL]), ("Wie spät ist es?", []), ("ja", [self.CALL]))
        self.assertEqual(self.tools.calls, [])

    def test_new_conversation_forgets_proposals(self):
        model = FakeModel(calls(self.CALL), text("Soll ich?"), calls(self.CALL), text("Soll ich?"))
        assistant = make(model, self.tools)
        assistant.reply("Lösch die Aufgabe")
        assistant.reply("neu")
        assistant.reply("ja")
        self.assertEqual(self.tools.calls, [])

    def test_other_tools_run_directly(self):
        self.run_turns(("Mach", [ToolCall("echo", {"text": "a"})]))
        self.assertEqual(len(self.tools.calls), 1)


class SettingsTest(unittest.TestCase):
    """Einstellungen aus dem Popup (backend/assistant/settings.py) wirken auf Modell und Ansicht."""

    def make_with(self, model, tools=None, answer=None, tool_settings=None):
        assistant = make(model, tools)
        assistant.settings.save(answer, tool_settings)
        return assistant

    def test_answer_wishes_in_system_message_not_as_raw_json(self):
        model = FakeModel(text("ok"))
        self.make_with(model, answer={"length": "ausfuehrlich", "address": "sie"}).reply("x")
        system = model.calls[0][0][0].content
        self.assertIn("Antworte ausführlich und vollständig.", system)
        self.assertIn("Sieze den Nutzer.", system)
        self.assertNotIn("Bekanntes über den Nutzer", system)   # Einstellungen sind kein Kontextwissen
        self.assertNotIn("answer_settings", system)

    def test_tool_wishes_for_offered_tools(self):
        model = FakeModel(text("ok"))
        self.make_with(model, tool_settings={"tool:echo": {"notes": "immer in Großbuchstaben"}}).reply("x")
        self.assertIn('Darstellung von "echo": immer in Großbuchstaben', model.calls[0][0][0].content)

    def test_disabled_tool_is_not_offered_and_refused(self):
        tools = EchoTools()
        model = FakeModel(calls(ToolCall("echo", {"text": "a"})), text("Geht nicht"))
        reply = self.make_with(model, tools, tool_settings={"tool:echo": {"enabled": False}}).reply("x")
        self.assertEqual(model.calls[0][1], [])
        self.assertEqual(tools.calls, [])   # auch ein erfundener Aufruf läuft nicht
        self.assertIn("abgeschaltet", model.calls[1][0][-1].content)
        self.assertEqual(reply.text, "Geht nicht")

    def test_view_off_hides_table(self):
        model = FakeModel(calls(ToolCall("echo", {"text": "a"})), text("Fertig"))
        reply = self.make_with(model, tool_settings={"tool:echo": {"view": "aus"}}).reply("x")
        self.assertIsNone(reply.view)

    def test_full_view_does_not_shorten(self):
        class LongTools(EchoTools):
            def call_tool(self, name, arguments):
                return ToolResult("x" * 1000)

        model = FakeModel(calls(ToolCall("echo")), text("Fertig"))
        short = make(FakeModel(calls(ToolCall("echo")), text("Fertig")), LongTools()).reply("x")
        full = self.make_with(model, LongTools(), tool_settings={"tool:echo": {"view": "voll"}}).reply("x")
        self.assertEqual(len(short.view.data["rows"][0][2]), 300 + len(" …"))
        self.assertEqual(full.view.data["rows"][0][2], "x" * 1000)

    def test_announce_uses_answer_wishes(self):
        model = FakeModel(text("Hallo"))
        self.make_with(model, answer={"language": "englisch"}).announce("Sag Hallo")
        self.assertIn("Antworte immer auf Englisch.", model.calls[0][0][0].content)


class ModelSelectionTest(unittest.TestCase):
    def test_picks_default_model(self):
        model = FakeModel(text("ok"), models=["a", "b"])
        make(model).reply("x")
        self.assertEqual(model.name, "a")

    def test_prefers_saved_model(self):
        model = FakeModel(models=["a", "b"])
        self.assertEqual(make(model, preferences=MemoryPreferences(**{MODEL_PREFERENCE: "b"})).current_model(), "b")

    def test_saved_model_no_longer_available(self):
        model = FakeModel(models=["a"])
        self.assertEqual(make(model, preferences=MemoryPreferences(**{MODEL_PREFERENCE: "weg"})).current_model(), "a")

    def test_configured_model_wins(self):
        self.assertEqual(make(FakeModel(models=["a"], name="fest")).current_model(), "fest")

    def test_select_model_is_saved(self):
        prefs = MemoryPreferences()
        model = FakeModel(models=["a", "b"])
        assistant = make(model, preferences=prefs)
        assistant.select_model("b")
        self.assertEqual(model.name, "b")
        self.assertEqual(prefs.get(MODEL_PREFERENCE), "b")

    def test_select_unknown_model(self):
        with self.assertRaisesRegex(ValueError, "steht nicht zur Auswahl"):
            make(FakeModel(models=["a"])).select_model("b")

    def test_available_models(self):
        models = make(FakeModel(models=["a", "b"])).available_models()
        self.assertEqual(models, [{"name": "a", "tools": True, "cloud": True},
                                  {"name": "b", "tools": True, "cloud": True}])

    def test_models_command_lists_gemini_models(self):
        reply = make(FakeModel(models=["a", "b"])).reply("modelle")
        self.assertEqual(reply.view.data["rows"], [["▶ a", "Cloud", "ja"], ["b", "Cloud", "ja"]])

    def test_model_command_switches_model(self):
        model = FakeModel(models=["a", "b"])
        self.assertIn("b", make(model).reply("modell b").text)
        self.assertEqual(model.name, "b")

    def test_model_command_unknown_model(self):
        self.assertIn('"modelle"', make(FakeModel(models=["a"])).reply("modell gibtsnicht").text)

    def test_help_lists_model_commands(self):
        rows = make(FakeModel()).reply("hilfe").view.data["rows"]
        self.assertIn("modelle", [row[0] for row in rows])


class AnnounceTest(unittest.TestCase):
    def test_implements_protocol(self):
        self.assertIsInstance(make(FakeModel()), ProactiveAssistant)

    def test_message_joins_history_but_trigger_does_not(self):
        model = FakeModel(text(" Hallo von selbst! "), text("Gern."))
        assistant = make(model)
        self.assertEqual(assistant.announce("Sag Hallo"), "Hallo von selbst!")
        messages, tools = model.calls[0]
        self.assertEqual(messages[0].role, "system")
        self.assertEqual(messages[-1], ChatMessage("user", PROACTIVE_TRIGGER + "Sag Hallo"))
        self.assertEqual(tools, [])
        self.assertEqual(assistant.history, [ChatMessage("assistant", "Hallo von selbst!")])
        assistant.reply("Danke")   # der Nutzer kann direkt antworten - das Modell sieht die Meldung
        self.assertEqual(model.calls[1][0][1:], [ChatMessage("assistant", "Hallo von selbst!"),
                                                 ChatMessage("user", "Danke")])

    def test_gemini_error(self):
        assistant = make(FakeModel(GeminiError("Gemini ist nicht erreichbar")))
        with self.assertLogs("backend.assistant.model_assistant", "WARNING"):
            self.assertIsNone(assistant.announce("Sag Hallo"))
        self.assertEqual(assistant.history, [])

    def test_empty_answer(self):
        assistant = make(FakeModel(text("  ")))
        self.assertIsNone(assistant.announce("Sag Hallo"))
        self.assertEqual(assistant.history, [])


if __name__ == "__main__":
    unittest.main()
