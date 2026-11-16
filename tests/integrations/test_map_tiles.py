import base64
import os
import tempfile
import time
import unittest
from pathlib import Path

from backend.integrations import map_tiles
from backend.integrations.http import IntegrationError
from backend.integrations.map_tiles import MapTiles, pixel
from tests.integrations.fake_http import FakeHttp

PNG = b"\x89PNG\r\n\x1a\nkachel"


class Clock:
    def __init__(self, now=None):
        self.now = time.time() if now is None else now   # wie das Änderungsdatum der Dateien

    def __call__(self):
        return self.now


class PixelTest(unittest.TestCase):
    def test_web_mercator(self):
        self.assertEqual(pixel(0.0, 0.0, 0), (128.0, 128.0))
        x, y = pixel(8.4689, 49.4794, 10)   # Mannheim Hbf liegt in Kachel 10/536/349
        self.assertEqual((int(x // 256), int(y // 256)), (536, 349))

    def test_poles_are_clamped(self):
        self.assertAlmostEqual(pixel(0.0, 90.0, 0)[1], 0.0, places=3)


class MapTilesTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()

    def tearDown(self):
        self.dir.cleanup()

    def tiles(self, response=PNG):
        http = FakeHttp({"tile.openstreetmap.org": response})
        return MapTiles(http, Path(self.dir.name), self.clock), http

    def test_data_uri_with_own_user_agent(self):
        tiles, http = self.tiles()
        uri = tiles.data_uri(10, 536, 350)
        self.assertEqual(base64.b64decode(uri.removeprefix("data:image/png;base64,")), PNG)
        method, url, _, headers = http.calls[0]
        self.assertEqual(url, "https://tile.openstreetmap.org/10/536/350.png")
        self.assertIn("PersonalDigitalAgent", headers["User-Agent"])

    def test_tiles_are_cached_on_disk(self):
        tiles, http = self.tiles()
        tiles.data_uri(10, 536, 350)
        again, http_again = self.tiles()
        again.data_uri(10, 536, 350)
        self.assertEqual((len(http.calls), len(http_again.calls)), (1, 0))
        self.assertTrue((Path(self.dir.name) / "10" / "536" / "350.png").exists())

    def test_old_tile_is_fetched_again_and_kept_on_error(self):
        self.tiles()[0].data_uri(10, 536, 350)
        old = self.clock.now - map_tiles.CACHE_S - 1
        os.utime(Path(self.dir.name) / "10" / "536" / "350.png", (old, old))
        tiles, http = self.tiles(IntegrationError("offline"))
        self.assertTrue(tiles.data_uri(10, 536, 350).startswith("data:image/png"))   # alte Kachel
        self.assertEqual(len(http.calls), 1)

    def test_offline_fails_fast(self):
        tiles, http = self.tiles(IntegrationError("offline"))
        with self.assertRaises(IntegrationError):
            tiles.data_uri(10, 536, 350)
        with self.assertRaises(IntegrationError):
            tiles.data_uri(10, 537, 350)
        self.assertEqual(len(http.calls), 1)   # nicht jede Kachel einzeln warten lassen
        self.clock.now += map_tiles.OFFLINE_S + 1
        with self.assertRaises(IntegrationError):
            tiles.data_uri(10, 537, 350)
        self.assertEqual(len(http.calls), 2)

    def test_no_png(self):
        tiles, _ = self.tiles(b"<html>blocked</html>")
        with self.assertRaisesRegex(IntegrationError, "PNG"):
            tiles.data_uri(10, 536, 350)


if __name__ == "__main__":
    unittest.main()
