"""Proaktive Meldungen: Meldung formulieren, an Chat und Benachrichtigung verteilen, api.proactive_message."""
import datetime
import unittest
from unittest import mock

from backend import api, proactive
from backend.assistant import ProactiveAssistant
from backend.assistant.commands import CommandAssistant
from backend.events import ASSISTANT_MESSAGE, PROACTIVE_NOTICE, EventBus, events
from backend.views import TemplateView

FIXED_NOW = datetime.datetime(2026, 11, 2, 14, 5)
OCCASION = proactive.Occasion("Titel", "Sag Hallo", "Ersatztext", "Test")


class Announcer:
    def __init__(self, result):
        self.result = result
        self.instructions = []

    def reply(self, message):
        raise AssertionError("reply darf für proaktive Meldungen nicht aufgerufen werden")

    def announce(self, instruction):
        self.instructions.append(instruction)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def compose(assistant):
    return proactive.compose(assistant, OCCASION, clock=lambda: FIXED_NOW)


class ComposeTest(unittest.TestCase):
    def test_assistant_formulates_message(self):
        assistant = Announcer("Hallo von selbst!")
        self.assertIsInstance(assistant, ProactiveAssistant)
        reply = compose(assistant)
        self.assertEqual(reply.text, "Hallo von selbst!")
        self.assertEqual(assistant.instructions, ["Sag Hallo"])
        self.assertIsInstance(reply.view, TemplateView)
        self.assertEqual(reply.view.data["title"], "Titel")
        self.assertIn(["Ausgelöst", "02.11.2026, 14:05 Uhr"], reply.view.data["rows"])
        self.assertIn(["Formuliert von", "Sprachmodell"], reply.view.data["rows"])

    def test_fallback_without_model(self):
        reply = compose(Announcer(None))
        self.assertEqual(reply.text, "Ersatztext")
        self.assertIn(["Formuliert von", "festem Text (kein Sprachmodell)"], reply.view.data["rows"])

    def test_fallback_when_assistant_fails(self):
        with self.assertLogs("backend.proactive", "ERROR"):
            reply = compose(Announcer(RuntimeError("kaputt")))
        self.assertEqual(reply.text, "Ersatztext")

    def test_fallback_for_assistant_without_announce(self):
        self.assertNotIsInstance(CommandAssistant(), ProactiveAssistant)
        self.assertEqual(compose(CommandAssistant()).text, "Ersatztext")


class AnnounceTest(unittest.TestCase):
    def test_publishes_chat_message_and_notice(self):
        bus = EventBus()
        received = []
        bus.subscribe(lambda name, payload: received.append((name, payload)))
        message = proactive.announce({"text": "**Hallo**", "html": None, "attachments": []}, OCCASION, bus)
        self.assertEqual(message, {"text": "**Hallo**", "html": None, "attachments": [],
                                   "proactive": True, "title": "Titel"})
        self.assertEqual(received, [(ASSISTANT_MESSAGE, message),
                                    (PROACTIVE_NOTICE, {"title": "Titel", "text": "Hallo"})])


class NoticeTextTest(unittest.TestCase):
    def test_removes_markdown_and_line_breaks(self):
        self.assertEqual(proactive.notice_text("# Hallo\n\n**du**  `x`"), "Hallo du x")

    def test_long_text_is_shortened(self):
        text = proactive.notice_text("a " * 500)
        self.assertEqual(len(text), proactive.NOTICE_MAX_CHARS)
        self.assertTrue(text.endswith("…"))


class OccasionTest(unittest.TestCase):
    def test_demo_exists(self):
        self.assertIs(proactive.occasion(proactive.DEMO), proactive.OCCASIONS["demo"])

    def test_unknown_occasion(self):
        with self.assertRaisesRegex(ValueError, "Unbekannter Anlass"):
            proactive.occasion("gibt_es_nicht")


class ApiProactiveMessageTest(unittest.TestCase):
    """Tests laufen mit dem CommandAssistant (tests/conftest.py) - also mit dem Ersatztext."""

    def setUp(self):
        self.received = []
        self.addCleanup(events.subscribe(lambda name, payload: self.received.append((name, payload))))
        self.speech = mock.Mock()
        patcher = mock.patch.object(api, "_speech_output", return_value=self.speech)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_message_reaches_chat_notice_and_speech(self):
        demo = proactive.OCCASIONS[proactive.DEMO]
        with mock.patch.object(api.config, "PROACTIVE_SPEAK", True):
            message = api.proactive_message()
        self.assertTrue(message["proactive"])
        self.assertEqual(message["text"], demo.fallback)
        self.assertIn(demo.title, message["html"])
        self.assertEqual([name for name, _ in self.received], [ASSISTANT_MESSAGE, PROACTIVE_NOTICE])
        self.speech.speak.assert_called_once_with(demo.fallback)

    def test_speech_can_be_switched_off(self):
        with mock.patch.object(api.config, "PROACTIVE_SPEAK", False):
            api.proactive_message("demo")
        self.speech.speak.assert_not_called()

    def test_speech_error_does_not_lose_message(self):
        self.speech.speak.side_effect = RuntimeError("kein Lautsprecher")
        with mock.patch.object(api.config, "PROACTIVE_SPEAK", True), self.assertLogs("backend.api", "ERROR"):
            message = api.proactive_message("demo")
        self.assertTrue(message["proactive"])


if __name__ == "__main__":
    unittest.main()
