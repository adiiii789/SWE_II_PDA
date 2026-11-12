"""Modelle für den 3D-Begleiter samt Einstellungsdatei (backend/companion_models.py)."""
import json
import tempfile
import unittest
from pathlib import Path

from backend.companion_models import DEFAULTS, list_models, model_options


class OptionsTest(unittest.TestCase):
    def test_defaults_without_file(self):
        self.assertEqual(model_options(None), DEFAULTS)

    def test_valid_values_are_taken(self):
        options = model_options({"yaw": 35, "size": 0.8, "hover": False, "eyes": "iris", "iris_hue": [350, 20]})
        self.assertEqual((options["yaw"], options["size"], options["hover"], options["eyes"]), (35.0, 0.8, False, "iris"))
        self.assertEqual(options["iris_hue"], [350.0, 20.0])

    def test_invalid_values_fall_back(self):
        options = model_options({"yaw": "links", "size": 99, "hover": "ja", "eyes": "laser", "iris_hue": [1]})
        self.assertEqual(options["yaw"], 0.0)
        self.assertEqual(options["size"], 3.0)          # begrenzt
        self.assertTrue(options["hover"])
        self.assertEqual(options["eyes"], "glow")
        self.assertEqual(options["iris_hue"], DEFAULTS["iris_hue"])


class ListTest(unittest.TestCase):
    def test_lists_models_with_title_and_file_url(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / "auto.glb").write_bytes(b"glTF")
            (folder / "auto.json").write_text(json.dumps({"title": "Rennauto", "hover": False}), encoding="utf-8")
            (folder / "mein_roboter.glb").write_bytes(b"glTF")
            (folder / "bild.png").write_bytes(b"png")
            (folder / "kaputt.gltf").write_bytes(b"{}")
            (folder / "kaputt.json").write_text("{kein json", encoding="utf-8")
            with self.assertLogs("backend.companion_models", "WARNING"):
                models = list_models(folder)
        self.assertEqual([model["title"] for model in models], ["kaputt", "mein roboter", "Rennauto"])
        auto = models[2]
        self.assertEqual(auto["id"], "auto.glb")
        self.assertTrue(auto["url"].startswith("file:///") and auto["url"].endswith("auto.glb"))
        self.assertFalse(auto["options"]["hover"])

    def test_missing_folder(self):
        self.assertEqual(list_models(Path("gibt/es/nicht")), [])


if __name__ == "__main__":
    unittest.main()
