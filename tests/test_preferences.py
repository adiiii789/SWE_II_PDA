import tempfile
import unittest
from pathlib import Path

from backend.preferences import JsonPreferenceStore, PreferenceStore


class JsonPreferenceStoreTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "unter" / "preferences.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_implements_protocol(self):
        self.assertIsInstance(JsonPreferenceStore(self.path), PreferenceStore)

    def test_missing_file_is_empty(self):
        store = JsonPreferenceStore(self.path)
        self.assertEqual(store.all(), {})
        self.assertEqual(store.get("x", 1), 1)

    def test_set_persists(self):
        JsonPreferenceStore(self.path).set("wohnort", "Mannheim")
        self.assertEqual(JsonPreferenceStore(self.path).get("wohnort"), "Mannheim")

    def test_broken_file_is_empty(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{kaputt", encoding="utf-8")
        self.assertEqual(JsonPreferenceStore(self.path).all(), {})

    def test_all_returns_copy(self):
        store = JsonPreferenceStore(self.path)
        store.all()["x"] = 1
        self.assertIsNone(store.get("x"))


if __name__ == "__main__":
    unittest.main()
