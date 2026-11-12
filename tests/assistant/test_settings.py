"""Einstellungen aus dem Popup: Schema, Prüfen und Speichern, Übersetzung in Anweisungen fürs Modell."""
import unittest

from backend.assistant.settings import (ANSWER_KEY, ANSWER_SETTINGS, MAX_TEXT_CHARS, TOOL_GROUPS, TOOLS_KEY,
                                        AssistantSettings, Choice, Setting, ToolGroup)
from backend.preferences import JsonPreferenceStore


class MemoryStore:
    def __init__(self, **values):
        self.values = dict(values)

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value

    def all(self):
        return dict(self.values)


TOOLS = [("list_emails", "Listet Mails"), ("calculate", "Rechnet"), ("get_weather", "Wetter von einem neuen Server")]


class SettingTest(unittest.TestCase):
    def test_clean_accepts_valid_values(self):
        choice = Setting("c", "C", "choice", "a", (Choice("a", "A"), Choice("b", "B")))
        multi = Setting("m", "M", "multi", [], (Choice("x", "X"), Choice("y", "Y")))
        self.assertEqual(choice.clean("b"), "b")
        self.assertEqual(multi.clean(["y", "x"]), ["x", "y"])   # Reihenfolge wie im Schema
        self.assertIs(Setting("b", "B", "bool", False).clean(True), True)
        self.assertEqual(Setting("n", "N", "number", 1, minimum=1, maximum=5).clean(3.0), 3)
        self.assertEqual(Setting("t", "T", "text", "").clean("  hallo  "), "hallo")
        self.assertEqual(len(Setting("t", "T", "text", "").clean("x" * 5000)), MAX_TEXT_CHARS)

    def test_clean_rejects_invalid_values(self):
        cases = [
            (Setting("c", "C", "choice", "a", (Choice("a", "A"),)), "z"),
            (Setting("m", "M", "multi", [], (Choice("x", "X"),)), ["z"]),
            (Setting("m", "M", "multi", [], (Choice("x", "X"),)), "x"),
            (Setting("b", "B", "bool", False), "ja"),
            (Setting("n", "N", "number", 1, minimum=1, maximum=5), 9),
            (Setting("n", "N", "number", 1, minimum=1, maximum=5), 2.5),
            (Setting("n", "N", "number", 1, minimum=1, maximum=5), True),
            (Setting("t", "T", "text", ""), 3),
        ]
        for setting, value in cases:
            with self.subTest(kind=setting.kind, value=value), self.assertRaises(ValueError):
                setting.clean(value)

    def test_schema_for_frontend(self):
        data = Setting("n", "Anzahl", "number", 3, minimum=1, maximum=9, help="Hilfe").to_dict()
        self.assertEqual(data, {"key": "n", "label": "Anzahl", "kind": "number", "default": 3, "help": "Hilfe",
                                "minimum": 1, "maximum": 9, "step": 1})

    def test_decimal_numbers_with_small_step(self):
        setting = Setting("f", "Faktor", "number", 1.5, minimum=1, maximum=5, step=0.1)
        self.assertEqual(setting.clean(2.345), 2.35)
        self.assertEqual(setting.clean(2), 2.0)
        self.assertEqual(setting.to_dict()["step"], 0.1)
        for value in (0.5, True, "2"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                setting.clean(value)

    def test_defaults_are_valid(self):
        for setting in (*ANSWER_SETTINGS, *(s for group in TOOL_GROUPS for s in group.settings)):
            with self.subTest(key=setting.key):
                self.assertEqual(setting.clean(setting.default), setting.default)


class ValuesTest(unittest.TestCase):
    def test_defaults_without_saved_values(self):
        settings = AssistantSettings(MemoryStore())
        self.assertEqual(settings.answer_values()["length"], "kurz")
        self.assertTrue(settings.tool_enabled("list_emails"))
        self.assertEqual(settings.tool_values("list_emails")["max"], 10)

    def test_invalid_stored_values_fall_back_to_default(self):
        # z. B. eine Auswahl, die es nach einem Update nicht mehr gibt
        store = MemoryStore(**{ANSWER_KEY: {"length": "episch", "tone": "sachlich"}})
        values = AssistantSettings(store).answer_values()
        self.assertEqual((values["length"], values["tone"]), ("kurz", "sachlich"))

    def test_tools_share_group_settings(self):
        settings = AssistantSettings(MemoryStore())
        settings.save(tools={"mail": {"enabled": False}})
        self.assertFalse(settings.tool_enabled("read_email"))
        self.assertFalse(settings.tool_enabled("send_email"))
        self.assertTrue(settings.tool_enabled("calculate"))

    def test_unknown_tool_gets_own_group(self):
        settings = AssistantSettings(MemoryStore())
        group = settings.group_of("get_weather")
        self.assertEqual((group.id, group.title, group.tools), ("tool:get_weather", "get_weather", ("get_weather",)))
        settings.save(tools={"tool:get_weather": {"view": "aus", "notes": "Temperatur fett"}})
        self.assertIsNone(settings.view_limit("get_weather"))
        self.assertEqual(settings.tool_values("get_weather")["notes"], "Temperatur fett")

    def test_view_limit(self):
        settings = AssistantSettings(MemoryStore())
        self.assertEqual(settings.view_limit("calculate"), 300)
        settings.save(tools={"basics": {"view": "voll"}})
        self.assertEqual(settings.view_limit("calculate"), 8000)


class SaveTest(unittest.TestCase):
    def test_save_merges_and_persists(self):
        store = MemoryStore()
        settings = AssistantSettings(store)
        settings.save(answer={"length": "ausfuehrlich"})
        settings.save(answer={"address": "sie"})
        self.assertEqual(store.values[ANSWER_KEY], {"length": "ausfuehrlich", "address": "sie"})

    def test_invalid_value_saves_nothing(self):
        store = MemoryStore()
        settings = AssistantSettings(store)
        with self.assertRaisesRegex(ValueError, "Höchstens so viele Mails"):
            settings.save(answer={"length": "mittel"}, tools={"mail": {"max": 999}})
        self.assertEqual(store.values, {})

    def test_unknown_keys_and_groups_are_rejected(self):
        settings = AssistantSettings(MemoryStore())
        with self.assertRaisesRegex(ValueError, "Unbekannte Einstellung"):
            settings.save(answer={"farbe": "blau"})
        with self.assertRaisesRegex(ValueError, "Unbekannte Werkzeuggruppe"):
            settings.save(tools={"gibtsnicht": {}})
        with self.assertRaisesRegex(ValueError, "Unbekannte Werkzeuggruppe"):
            settings.save(tools={"tool:": {}})

    def test_reset(self):
        store = MemoryStore()
        settings = AssistantSettings(store)
        settings.save(answer={"length": "mittel"}, tools={"mail": {"max": 3}})
        settings.reset()
        self.assertEqual(settings.answer_values()["length"], "kurz")
        self.assertEqual(settings.tool_values("list_emails")["max"], 10)

    def test_survives_restart_with_json_store(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preferences.json"
            AssistantSettings(JsonPreferenceStore(path)).save(answer={"tone": "locker"})
            self.assertEqual(AssistantSettings(JsonPreferenceStore(path)).answer_values()["tone"], "locker")


class InstructionsTest(unittest.TestCase):
    def test_default_answer_instructions(self):
        text = AssistantSettings(MemoryStore()).instructions()
        self.assertIn("Wünsche des Nutzers an deine Antworten:", text)
        for sentence in ("Antworte kurz", "Antworte immer auf Deutsch.", "Verwende niemals Emojis.",
                         "Duze den Nutzer.", "frag kurz nach"):
            self.assertIn(sentence, text)
        self.assertNotIn("Weitere Wünsche", text)   # leerer Freitext sagt nichts
        self.assertNotIn("Werkzeug-Ergebnissen", text)   # keine Werkzeuge angeboten

    def test_changed_answer_instructions(self):
        settings = AssistantSettings(MemoryStore())
        settings.save(answer={"length": "ausfuehrlich", "format": "stichpunkte", "address": "sie",
                              "emojis": True, "extra": "Nenne immer Quellen"})
        text = settings.instructions()
        for sentence in ("Antworte ausführlich", "Stichpunkte", "Sieze den Nutzer.", "Emojis sind erlaubt",
                         "Weitere Wünsche des Nutzers: Nenne immer Quellen"):
            self.assertIn(sentence, text)
        self.assertNotIn("Antworte kurz", text)

    def test_mail_instructions(self):
        settings = AssistantSettings(MemoryStore())
        settings.save(tools={"mail": {"fields": ["sender", "attachments"], "content": "wichtiges",
                                      "layout": "tabelle", "max": 5, "notes": "Absender fett"}})
        text = settings.instructions(["list_emails", "read_email"])
        mail_line = next(line for line in text.splitlines() if line.startswith("- E-Mail:"))
        for sentence in ("Zeige bei jeder Mail: Absender, Anhänge", "nur Fristen, Termine",
                         "Markdown-Tabelle", "höchstens 5 Mails", "Entwurf", 'Darstellung von "E-Mail": Absender fett'):
            self.assertIn(sentence, mail_line)

    def test_only_offered_and_enabled_groups(self):
        settings = AssistantSettings(MemoryStore())
        settings.save(tools={"tool:get_weather": {"detail": "kurz"}, "basics": {"enabled": False, "detail": "kurz"}})
        text = settings.instructions(["get_weather", "calculate"])
        self.assertIn('- get_weather (get_weather): Gib Ergebnisse von "get_weather" nur knapp wieder', text)
        self.assertNotIn("Uhrzeit und Rechnen", text)   # abgeschaltet
        self.assertNotIn("E-Mail", text)                # nicht angeboten

    def test_group_without_wishes_is_left_out(self):
        text = AssistantSettings(MemoryStore()).instructions(["calculate"])
        self.assertNotIn("Werkzeug-Ergebnissen", text)   # Standard sagt nichts Besonderes


class FormTest(unittest.TestCase):
    def test_form_lists_known_groups_and_new_tools(self):
        form = AssistantSettings(MemoryStore()).form(TOOLS)
        self.assertEqual([field["key"] for field in form["answer"]["fields"]], [s.key for s in ANSWER_SETTINGS])
        groups = {group["id"]: group for group in form["tools"]}
        self.assertEqual(list(groups), ["mail", "calendar", "tasks", "basics", "tool:get_weather"])
        self.assertTrue(groups["mail"]["available"])
        self.assertIn("max", [field["key"] for field in groups["mail"]["fields"]])
        weather = groups["tool:get_weather"]
        self.assertEqual(weather["description"], "Wetter von einem neuen Server")
        self.assertEqual([field["key"] for field in weather["fields"]], ["enabled", "detail", "view", "notes"])

    def test_known_group_without_tools_is_marked_unavailable(self):
        groups = {group["id"]: group for group in AssistantSettings(MemoryStore()).form([])["tools"]}
        self.assertFalse(groups["mail"]["available"])

    def test_custom_groups(self):
        weather = ToolGroup("weather", "Wetter", ("get_weather", "get_forecast"),
                            extra=(Setting("unit", "Einheit", "choice", "c", (Choice("c", "°C"), Choice("f", "°F"))),))
        settings = AssistantSettings(MemoryStore(), [weather])
        self.assertIs(settings.group_of("get_forecast"), weather)
        settings.save(tools={"weather": {"unit": "f"}})
        self.assertEqual(settings.tool_values("get_weather")["unit"], "f")


if __name__ == "__main__":
    unittest.main()
