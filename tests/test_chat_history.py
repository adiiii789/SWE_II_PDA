"""Gespeicherte Chats (backend/chat_history.py) und ihre Funktionen fürs Popup (backend/api.py)."""
import datetime
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend import api
from backend.assistant import ConversationMemory
from backend.assistant.llm import ChatMessage
from backend.assistant.model_picker import ModelPicker
from backend.chat_history import MAX_VIEW_CHARS, ChatHistory, ChatStore, chat_title, valid_chat_id
from tests.assistant.test_gemini_assistant import FakeModel, make, text


class Clock:
    """Jeder Aufruf eine Minute später - so ist die Reihenfolge der Chats eindeutig."""

    def __init__(self):
        self.now = datetime.datetime(2026, 11, 26, 9, 0)

    def __call__(self):
        self.now += datetime.timedelta(minutes=1)
        return self.now


class TempDirTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name) / "chats"
        self.store = ChatStore(self.dir, max_chats=3)
        self.history = ChatHistory(self.store, Clock())


class ChatHistoryTest(TempDirTest):
    def test_chat_is_saved_once_the_user_wrote_something(self):
        self.history.record_reply({"text": "Guten Morgen!", "proactive": True, "title": "Briefing"})
        self.assertEqual(self.history.summaries(), [])   # nur eine Meldung: kein eigener Eintrag
        self.history.record_exchange("Wie wird das Wetter?", {"text": "Sonnig.", "html": "<p>x</p>"})
        [summary] = self.history.summaries()
        self.assertEqual(summary["title"], "Wie wird das Wetter?")
        self.assertEqual(summary["count"], 3)
        self.assertTrue(summary["current"])
        saved = self.store.load(summary["id"])
        self.assertEqual([m["role"] for m in saved.messages], ["assistant", "user", "assistant"])
        self.assertEqual(saved.messages[0]["title"], "Briefing")
        self.assertNotIn("html", saved.messages[2])   # Ansichten nur mit "Anzeigen"-Knopf

    def test_views_with_button_are_kept_unless_huge(self):
        self.history.record_exchange("reise", {"text": "Plan", "html": "<p>Karte</p>", "view_button": "Anzeigen"})
        self.history.record_exchange("nochmal", {"text": "Plan", "html": "x" * (MAX_VIEW_CHARS + 1),
                                                 "view_button": "Anzeigen"})
        messages = self.store.load(self.history.current.id).messages
        self.assertEqual((messages[1]["html"], messages[1]["view_button"]), ("<p>Karte</p>", "Anzeigen"))
        self.assertNotIn("html", messages[3])

    def test_new_open_and_delete(self):
        self.history.record_exchange("Erster", {"text": "a"})
        first = self.history.current.id
        self.history.start_new()
        self.history.record_exchange("Zweiter", {"text": "b"})
        second = self.history.current.id
        self.assertEqual([c["title"] for c in self.history.summaries()], ["Zweiter", "Erster"])

        self.assertEqual(self.history.open(first).title, "Erster")
        self.history.record_exchange("weiter", {"text": "c"})
        self.assertEqual([c["id"] for c in self.history.summaries()], [first, second])   # zuletzt geändert zuerst

        self.assertFalse(self.history.delete(second))
        self.assertTrue(self.history.delete(first))   # der laufende: es beginnt ein neuer
        self.assertNotEqual(self.history.current.id, first)
        self.assertEqual(self.history.summaries(), [])
        with self.assertRaises(KeyError):
            self.history.open(first)

    def test_oldest_chats_are_pruned(self):
        for index in range(5):
            self.history.start_new()
            self.history.record_exchange(f"Chat {index}", {"text": "ok"})
        self.assertEqual([c["title"] for c in self.history.summaries()], ["Chat 4", "Chat 3", "Chat 2"])

    def test_dialogue_leaves_out_commands(self):
        self.history.record_exchange("hilfe", {"text": "Befehle …"})
        self.history.record_exchange("Was ist 2+2?", {"text": "4"})
        self.history.record_exchange("modell gemini-x", {"text": "Ich nutze jetzt gemini-x."})
        self.history.record_reply({"text": "Termin in 10 Minuten", "proactive": True, "title": "Termin"})
        self.assertEqual(self.history.current.dialogue(),
                         [("user", "Was ist 2+2?"), ("assistant", "4"), ("assistant", "Termin in 10 Minuten")])

    def test_unwritable_store_does_not_break_the_chat(self):
        with mock.patch.object(self.store, "save", side_effect=OSError("voll")), self.assertLogs(level="ERROR"):
            self.history.record_exchange("Hallo", {"text": "Hi"})
        self.assertEqual(len(self.history.current.messages), 2)


class ChatStoreTest(TempDirTest):
    def test_broken_and_foreign_files_are_skipped(self):
        self.history.record_exchange("Hallo", {"text": "Hi"})
        (self.dir / ("a" * 32 + ".json")).write_text("{kaputt", encoding="utf-8")
        (self.dir / "notizen.json").write_text("{}", encoding="utf-8")
        with self.assertLogs(level="WARNING"):
            self.assertEqual(len(self.history.summaries()), 1)

    def test_invalid_ids_never_reach_the_file_system(self):
        for chat_id in ("../preferences", "", "A" * 32, None):
            self.assertFalse(valid_chat_id(chat_id))
        with self.assertRaises(ValueError):
            self.store.load("../preferences")

    def test_saved_file_is_json(self):
        self.history.record_exchange("Hallo", {"text": "Hi"})
        data = json.loads((self.dir / f"{self.history.current.id}.json").read_text(encoding="utf-8"))
        self.assertEqual(data["title"], "Hallo")
        self.assertEqual(list(self.dir.glob("*.tmp")), [])

    def test_title_is_one_short_line(self):
        self.assertEqual(chat_title("  Hallo\n  Welt "), "Hallo Welt")
        long = chat_title("x " * 100)
        self.assertLessEqual(len(long), 60)
        self.assertTrue(long.endswith("…"))


class RestoreConversationTest(unittest.TestCase):
    def test_model_assistant_continues_a_saved_conversation(self):
        model = FakeModel(text("Weiter geht's."))
        assistant = make(model, max_history=3)   # kürzt vorn, beginnt aber immer bei einer Nutzernachricht
        self.assertIsInstance(assistant, ConversationMemory)
        assistant.restore_conversation([("assistant", "Meldung"), ("user", "a"), ("assistant", "b"),
                                        ("user", "c"), ("assistant", "d"), ("user", " ")])
        self.assertEqual(assistant.history, [ChatMessage("user", "c"), ChatMessage("assistant", "d")])
        assistant.reply("und jetzt?")
        sent = model.calls[0][0]
        self.assertEqual([m.content for m in sent[1:]], ["c", "d", "und jetzt?"])

    def test_picker_restores_every_provider(self):
        first, second = make(FakeModel()), make(FakeModel())
        picker = ModelPicker(first, second, first.preferences)
        picker.restore_conversation([("user", "Hallo"), ("assistant", "Hi")])
        self.assertEqual(len(first.history), 2)
        self.assertEqual(len(second.history), 2)
        picker.new_conversation()
        self.assertEqual((first.history, second.history), ([], []))


class ChatApiTest(TempDirTest):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(api, "_chat_history", return_value=self.history)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_chat_is_recorded_and_can_be_reopened(self):
        api.chat("uhrzeit")
        [summary] = api.list_chats()
        self.assertEqual(summary["title"], "uhrzeit")
        api.new_chat()
        self.assertFalse(api.list_chats()[0]["current"])
        opened = api.open_chat(summary["id"])
        self.assertEqual([m["role"] for m in opened["messages"]], ["user", "assistant"])
        self.assertTrue(api.list_chats()[0]["current"])

    def test_open_chat_restores_the_assistant(self):
        api.chat("Erzähl was")
        chat_id = self.history.current.id
        api.new_chat()
        class FakeAssistant:
            def reply(self, message): ...
            def new_conversation(self): ...
            def restore_conversation(self, messages): self.restored = messages

        fake = FakeAssistant()
        with mock.patch.object(api, "_assistant", return_value=fake):
            api.open_chat(chat_id)
        self.assertEqual(fake.restored[0], ("user", "Erzähl was"))

    def test_neu_starts_a_new_chat(self):
        api.chat("Hallo")
        first = self.history.current.id
        reply = api.chat("neu")
        self.assertTrue(reply["new_chat"])
        self.assertNotEqual(self.history.current.id, first)
        self.assertEqual(len(self.store.load(first).messages), 2)   # "neu" selbst wird nicht gespeichert

    def test_delete_chat(self):
        api.chat("Hallo")
        result = api.delete_chat(self.history.current.id)
        self.assertEqual(result, {"chats": [], "cleared": True})

    def test_unknown_or_invalid_ids(self):
        with self.assertRaises(ValueError):
            api.open_chat("../preferences")
        with self.assertRaises(ValueError):
            api.open_chat("0" * 32)
        with self.assertRaises(ValueError):
            api.delete_chat("x")

    def test_proactive_messages_land_in_the_running_chat(self):
        api.chat("Hallo")
        with mock.patch.object(api, "_speak"):
            api.proactive_message()
        messages = self.store.load(self.history.current.id).messages
        self.assertTrue(messages[-1]["proactive"])
