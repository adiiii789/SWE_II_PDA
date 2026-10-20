import re
import unittest

from backend import config
from backend.assistant import Assistant, ModelSelection, create_assistant
from backend.assistant.ollama_assistant import OllamaAssistant
from backend.assistant import commands
from backend.assistant.commands import CommandAssistant
from backend.rendering import ViewRenderer
from backend.views import START_VIEW


class CommandAssistantTest(unittest.TestCase):
    def setUp(self):
        self.assistant = CommandAssistant()

    def test_implements_assistant_protocol(self):
        self.assertIsInstance(self.assistant, Assistant)

    def test_every_command_renders_with_the_real_template(self):
        # Vertrag Assistent ↔ Template: jede Ansicht lässt sich mit dem echten Template rendern.
        renderer = ViewRenderer(config.TEMPLATE_DIR, config.FRONTEND_DIR)
        for name, (_, handler) in commands.COMMANDS.items():
            with self.subTest(command=name):
                view = handler().view
                self.assertIsNotNone(view)
                self.assertIn("<!DOCTYPE html>", renderer.render(view))

    def test_commands_are_case_and_whitespace_insensitive(self):
        self.assertEqual(self.assistant.reply("  HILFE ").view.data["title"], "Befehle")

    def test_help_lists_all_commands(self):
        rows = self.assistant.reply("hilfe").view.data["rows"]
        self.assertEqual([row[0] for row in rows], list(commands.COMMANDS))

    def test_time_shows_clock_and_german_weekday(self):
        data = self.assistant.reply("uhrzeit").view.data
        self.assertRegex(data["title"], re.compile(r"^\d{2}:\d{2}:\d{2}$"))
        self.assertIn(data["text"].split(",")[0], commands._WEEKDAYS)

    def test_system_table_has_two_columns(self):
        data = self.assistant.reply("system").view.data
        self.assertTrue(all(len(row) == len(data["columns"]) for row in data["rows"]))

    def test_start_command_shows_start_view(self):
        self.assertIs(self.assistant.reply("start").view, START_VIEW)

    def test_unknown_message_keeps_current_view(self):
        reply = self.assistant.reply("blabla")
        self.assertIsNone(reply.view)
        self.assertIn("blabla", reply.text)


class CreateAssistantTest(unittest.TestCase):
    def test_configured_backend(self):
        self.assertIsInstance(create_assistant(), Assistant)

    def test_commands_backend(self):
        self.assertIsInstance(create_assistant("commands"), CommandAssistant)

    def test_ollama_backend_uses_configured_mcp_servers(self):
        # Erzeugen startet weder Ollama noch MCP-Server - das passiert erst bei Bedarf.
        assistant = create_assistant("ollama")
        self.assertIsInstance(assistant, OllamaAssistant)
        self.assertIsInstance(assistant, ModelSelection)
        self.assertEqual([p.name for p in assistant.tools._providers], ["pda"])   # "demo" ist abgeschaltet

    def test_unknown_backend_raises(self):
        with self.assertRaisesRegex(ValueError, "does_not_exist"):
            create_assistant("does_not_exist")


if __name__ == "__main__":
    unittest.main()
