"""Auswahl der Stimme in den Einstellungen (backend/voice_settings.py)."""
import tempfile
import unittest
from pathlib import Path

from backend.assistant.settings import VOICE_KEY
from backend.speech import Voice
from backend.voice_settings import STANDARD, VOICES, VoiceSettings
from tests.assistant.test_settings import MemoryStore


class VoiceSettingsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.voice_dir = Path(tmp.name)
        self.store = MemoryStore()
        self.settings = VoiceSettings(self.store, self.voice_dir, "de_DE-pavoque-low")

    def choices(self):
        field = next(field for field in self.settings.form()["fields"] if field["key"] == "voice")
        return {choice["value"]: choice["label"] for choice in field["choices"]}

    def test_default_is_the_configured_voice(self):
        self.assertEqual(self.settings.voice(), Voice("de_DE-pavoque-low"))
        self.assertIn("de_DE-pavoque-low", self.choices()[STANDARD])

    def test_all_thorsten_voices_are_offered(self):
        self.assertEqual(len(VOICES), 11)
        self.assertTrue(all("thorsten" in option.value for option in VOICES))
        self.assertTrue(set(option.value for option in VOICES) <= set(self.choices()))

    def test_emotional_voice_selects_speaker_and_speed(self):
        self.settings.store_validated(self.settings.validated(
            {"voice": "de_DE-thorsten_emotional-medium:whisper", "speed": "langsam"}))
        self.assertEqual(self.settings.voice(), Voice("de_DE-thorsten_emotional-medium", "whisper", 1.25))

    def test_missing_voice_says_it_downloads_first(self):
        self.assertIn("MB", self.choices()["de_DE-thorsten-high"])
        (self.voice_dir / "de_DE-thorsten-high.onnx").write_bytes(b"")
        self.assertNotIn("MB", self.choices()["de_DE-thorsten-high"])

    def test_unknown_voice_is_rejected(self):
        with self.assertRaises(ValueError):
            self.settings.validated({"voice": "de_DE-jemand-low"})
        with self.assertRaises(ValueError):
            self.settings.voice({"speed": "rasend"})

    def test_voice_removed_after_update_falls_back_to_standard(self):
        self.store.set(VOICE_KEY, {"voice": "de_DE-alt-low"})
        self.assertEqual(self.settings.voice(), Voice("de_DE-pavoque-low"))


if __name__ == "__main__":
    unittest.main()
