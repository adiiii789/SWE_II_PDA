"""Prüft, dass die Schnittstellen für Präferenzen und Sprache von einfachen
Implementierungen erfüllt werden können."""
import unittest

from backend.preferences import PreferenceStore
from backend.speech import SpeechInput, SpeechOutput


class InMemoryPreferences:
    def __init__(self):
        self._values = {}

    def get(self, key, default=None):
        return self._values.get(key, default)

    def set(self, key, value):
        self._values[key] = value

    def all(self):
        return dict(self._values)


class FakeMicrophone:
    def start(self): ...

    def stop(self):
        return "Wie wird das Wetter?"

    def cancel(self): ...


class FakeSpeaker:
    def __init__(self):
        self.spoken = []

    def speak(self, text):
        self.spoken.append(text)

    def stop(self): ...


class PreferenceStoreTest(unittest.TestCase):
    def test_fake_satisfies_protocol(self):
        self.assertIsInstance(InMemoryPreferences(), PreferenceStore)

    def test_get_set_all(self):
        prefs = InMemoryPreferences()
        self.assertEqual(prefs.get("home_city", "unbekannt"), "unbekannt")
        prefs.set("home_city", "Mannheim")
        self.assertEqual(prefs.get("home_city"), "Mannheim")
        self.assertEqual(prefs.all(), {"home_city": "Mannheim"})


class SpeechTest(unittest.TestCase):
    def test_fakes_satisfy_protocols(self):
        self.assertIsInstance(FakeMicrophone(), SpeechInput)
        self.assertIsInstance(FakeSpeaker(), SpeechOutput)

    def test_record_and_speak(self):
        speaker, microphone = FakeSpeaker(), FakeMicrophone()
        microphone.start()
        speaker.speak(microphone.stop())
        self.assertEqual(speaker.spoken, ["Wie wird das Wetter?"])

    def test_unrelated_object_does_not_satisfy_protocols(self):
        self.assertNotIsInstance(object(), SpeechInput)
        self.assertNotIsInstance(object(), PreferenceStore)


if __name__ == "__main__":
    unittest.main()
