import os
import sys
import tempfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from backend import api, api_keys, config


class ApiKeysTest(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)
        self.env = self.dir / ".env"
        patcher = mock.patch.object(config, "ENV_FILE", self.env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_save_keeps_comments_and_other_lines(self):
        self.env.write_text("# Kommentar\nPDA_SMTP_HOST=smtp.example.com\nPDA_ORS_KEY=alt\nPDA_ORS_KEY=doppelt\n"
                            "# PDA_TANKERKOENIG_KEY=auskommentiert\n", encoding="utf-8")
        api_keys.save({"PDA_ORS_KEY": "  neu  ", "PDA_TANKERKOENIG_KEY": "tk"})
        self.assertEqual(self.env.read_text(encoding="utf-8"),
                         "# Kommentar\nPDA_SMTP_HOST=smtp.example.com\nPDA_ORS_KEY=neu\n"
                         "# PDA_TANKERKOENIG_KEY=auskommentiert\nPDA_TANKERKOENIG_KEY=tk\n")
        self.assertEqual(api_keys.get("PDA_ORS_KEY"), "neu")
        api_keys.save({"PDA_ORS_KEY": ""})                                   # leer = löschen
        self.assertEqual(api_keys.get("PDA_ORS_KEY"), "")
        if sys.platform != "win32":
            self.assertEqual(self.env.stat().st_mode & 0o777, 0o600)

    def test_status_never_contains_values(self):
        api_keys.save({"GEMINI_API_KEY": "geheim-123"})
        rows = api_keys.status()
        self.assertNotIn("geheim-123", repr(rows))
        gemini = next(row for row in rows if row["name"] == "GEMINI_API_KEY")
        self.assertEqual((gemini["set"], gemini["source"]), (True, "file"))
        self.assertNotIn("geheim-123", repr(api.get_settings()))           # auch nicht übers Formular

    def test_only_known_keys_without_line_breaks(self):
        for changes in ({"PDA_MAIL_RECIPIENTS": "boese@example.com"},          # keine beliebigen Einträge
                        {"PDA_ORS_KEY": "abc\nPDA_MAIL_RECIPIENTS=boese@example.com"},   # keine neue Zeile
                        {"PDA_ORS_KEY": "abc def"}, {"PDA_ORS_KEY": "\"abc\""}, {"PDA_ORS_KEY": 5},
                        {"PDA_ORS_KEY": "x" * 2000}):
            with self.subTest(changes=changes), self.assertRaises(ValueError) as caught:
                api_keys.save(changes)
            self.assertNotIn("abc", str(caught.exception))                   # Fehler nennen nie den Wert
        self.assertFalse(self.env.exists())
        api_keys.save({"PDA_SMTP_PASSWORD": "abcd efgh ijkl mnop"})          # Leerzeichen innen sind erlaubt
        self.assertEqual(api_keys.get("PDA_SMTP_PASSWORD"), "abcd efgh ijkl mnop")

    def test_environment_variable_wins_and_is_not_editable(self):
        api_keys.save({"PDA_ORS_KEY": "aus-datei"})
        with mock.patch.dict(os.environ, {"PDA_ORS_KEY": "aus-umgebung"}):
            self.assertEqual(api_keys.get("PDA_ORS_KEY"), "aus-umgebung")
            row = next(row for row in api_keys.status() if row["name"] == "PDA_ORS_KEY")
            self.assertEqual(row["source"], "env")
            with self.assertRaisesRegex(ValueError, "Umgebungsvariablen"):
                api_keys.save({"PDA_ORS_KEY": "neu"})
        with mock.patch.dict(os.environ, {"PDA_ORS_KEY": ""}):                # leer zählt nicht
            self.assertEqual(api_keys.get("PDA_ORS_KEY"), "aus-datei")

    def test_settings_form_saves_keys_and_invalid_key_saves_nothing(self):
        with mock.patch.object(api, "_settings") as settings:
            with self.assertRaises(ValueError):
                api.save_settings({"answer": {"length": "kurz"}, "keys": {"PDA_ORS_KEY": "a\nb"}})
            settings.return_value.save.assert_not_called()
            api.save_settings({"keys": {"PDA_ORS_KEY": "ors"}})
        self.assertEqual(api_keys.get("PDA_ORS_KEY"), "ors")
        with mock.patch.object(api, "_settings"), mock.patch.object(api, "_proactive_settings"), \
                mock.patch.object(api, "_travel_settings"):
            api.reset_settings()
        self.assertEqual(api_keys.get("PDA_ORS_KEY"), "ors")                  # Zurücksetzen lässt Keys stehen

    def test_legacy_files_move_into_the_env(self):
        (self.dir / "gemini-api-key.txt").write_text("gemini-key\n", encoding="utf-8")
        (self.dir / "alphavantage-api-key.txt").write_text("av-key\n", encoding="utf-8")
        self.env.write_text("PDA_ALPHAVANTAGE_KEY=schon-da\n", encoding="utf-8")
        self.assertEqual(api_keys.migrate_legacy_files(self.dir), ["GEMINI_API_KEY"])
        self.assertEqual(api_keys.get("GEMINI_API_KEY"), "gemini-key")
        self.assertFalse((self.dir / "gemini-api-key.txt").exists())
        self.assertEqual(api_keys.get("PDA_ALPHAVANTAGE_KEY"), "schon-da")
        self.assertTrue((self.dir / "alphavantage-api-key.txt").exists())   # steht schon drin: nicht anfassen
        self.assertEqual(api_keys.migrate_legacy_files(self.dir), [])

    def test_tests_never_touch_the_real_files(self):
        # tests/conftest.py: eigene .env und eigener App-Datenordner im Temp-Ordner
        temp = Path(tempfile.gettempdir()).resolve()
        self.assertTrue(config.APP_DATA_DIR.resolve().is_relative_to(temp), config.APP_DATA_DIR)
        self.assertTrue(Path(os.environ["PDA_ENV_FILE"]).resolve().is_relative_to(temp))


if __name__ == "__main__":
    unittest.main()
