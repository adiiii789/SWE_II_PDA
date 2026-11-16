import json
import tempfile
import unittest
from pathlib import Path

from backend.integrations import db_stations
from backend.integrations.db_stations import DbStations
from backend.integrations.db_timetables import Station
from backend.integrations.geo import Place
from backend.integrations.http import IntegrationError
from tests.integrations.fake_http import FakeHttp

PARADEPLATZ = Place("Paradeplatz, Mannheim", 49.4874, 8.4660)   # 1 km zum Hbf
NECKARAU = Place("Neckarau, Mannheim", 49.4556, 8.4934)          # direkt am S-Bahn-Halt
DAY = 24 * 3600


def station(name, eva, lat, lon, category):
    numbers = [{"number": int(eva), "isMain": True, "geographicCoordinates": {"type": "Point", "coordinates": [lon, lat]}}]
    return {"name": name, "category": category, "evaNumbers": numbers}


STATIONS = [
    station("Mannheim Hbf", "8000244", 49.4794, 8.4689, 1),
    station("Mannheim-Neckarau", "8003800", 49.4560, 8.4930, 5),
    station("Mannheim ARENA/Maimarkt", "8003841", 49.4800, 8.5230, 6),
    station("Heidelberg Hbf", "8000156", 49.4036, 8.6757, 2),
    {"name": "Lindaunis", "category": 7, "evaNumbers": []},                    # ohne EVA: übersprungen
]
RESPONSE = {"offset": 0, "limit": 10000, "total": len(STATIONS), "result": STATIONS}


class Clock:
    def __init__(self, now=1_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


class DbStationsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.file = Path(self.dir.name) / "stations.json"
        self.clock = Clock()

    def tearDown(self):
        self.dir.cleanup()

    def stations(self, response=RESPONSE):
        http = FakeHttp({"/station-data/v2/stations": response})
        return DbStations(http, "client", "secret", self.file, self.clock), http

    def test_main_station_beats_small_stop_nearby(self):
        stations, http = self.stations()
        found = stations.nearest(PARADEPLATZ)
        self.assertEqual(found, Station("Mannheim Hbf", "8000244"))
        self.assertEqual((found.lat, found.lon), (49.4794, 8.4689))
        self.assertEqual(http.calls[0][3]["DB-Client-Id"], "client")
        self.assertEqual(http.calls[0][3]["DB-Api-Key"], "secret")

    def test_small_stop_when_main_station_is_far(self):
        stations, _ = self.stations()
        self.assertEqual(stations.nearest(NECKARAU).name, "Mannheim-Neckarau")   # Hbf 3,2 km, Halt 50 m + 2,5 km Aufschlag

    def test_only_major_stations(self):
        stations, _ = self.stations()
        self.assertEqual(stations.nearest(NECKARAU, max_category=2).name, "Mannheim Hbf")
        with self.assertRaisesRegex(IntegrationError, "Kein Bahnhof"):
            stations.nearest(NECKARAU, max_category=0)

    def test_no_station_nearby(self):
        stations, _ = self.stations()
        with self.assertRaisesRegex(IntegrationError, "Kein Bahnhof im Umkreis"):
            stations.nearest(Place("Zugspitze", 47.42, 10.98))

    def test_list_is_saved_and_reused(self):
        stations, http = self.stations()
        stations.nearest(PARADEPLATZ)
        stations.nearest(PARADEPLATZ)
        self.assertEqual(len(http.calls), 1)
        saved = json.loads(self.file.read_text(encoding="utf-8"))
        self.assertEqual(len(saved["stations"]), 4)
        again, http_again = self.stations()
        self.assertEqual(again.nearest(PARADEPLATZ).eva, "8000244")
        self.assertEqual(http_again.calls, [])   # aus der Datei, kein neuer Download

    def test_refresh_after_a_week_and_keep_old_list_on_error(self):
        self.stations()[0].nearest(PARADEPLATZ)
        self.clock.now += db_stations.REFRESH_S + DAY
        stations, http = self.stations(IntegrationError("StaDa weg"))
        self.assertEqual(stations.nearest(PARADEPLATZ).eva, "8000244")   # alte Liste gilt weiter
        stations.nearest(PARADEPLATZ)
        self.assertEqual(len(http.calls), 1)                             # nicht gleich wieder versucht
        self.clock.now += db_stations.RETRY_S + 1
        stations.nearest(PARADEPLATZ)
        self.assertEqual(len(http.calls), 2)

    def test_without_list_and_without_stada(self):
        stations, _ = self.stations(IntegrationError("403 nicht abonniert"))
        with self.assertRaisesRegex(IntegrationError, "403"):
            stations.nearest(PARADEPLATZ)

    def test_unreadable_file_is_loaded_again(self):
        self.file.write_text("kaputt", encoding="utf-8")
        stations, http = self.stations()
        self.assertEqual(stations.nearest(PARADEPLATZ).eva, "8000244")
        self.assertEqual(len(http.calls), 1)

    def test_invalid_response(self):
        stations, _ = self.stations({"error": "?"})
        with self.assertRaisesRegex(IntegrationError, "Ungültige Antwort"):
            stations.nearest(PARADEPLATZ)

    def test_pages_until_total(self):
        pages = [{"total": 3, "result": STATIONS[:2]}, {"total": 3, "result": STATIONS[3:4]}]

        class PagedHttp(FakeHttp):
            def get_json(self, url, params=None, headers=None):
                self.calls.append(("GET", url, params, headers))
                return pages[len(self.calls) - 1]

        http = PagedHttp()
        stations = DbStations(http, "c", "k", self.file, self.clock)
        self.assertEqual(stations.nearest(Place("Bismarckplatz, Heidelberg", 49.4093, 8.6935)).name, "Heidelberg Hbf")
        self.assertEqual([call[2]["offset"] for call in http.calls], [0, 2])

    def test_main_eva_number_of_station_with_several(self):
        hbf = station("Mannheim Hbf", "8000244", 49.4794, 8.4689, 1)
        hbf["evaNumbers"].insert(0, {"number": 8089001, "isMain": False,
                                     "geographicCoordinates": {"coordinates": [8.47, 49.48]}})
        stations, _ = self.stations({"total": 1, "result": [hbf]})
        self.assertEqual(stations.nearest(PARADEPLATZ).eva, "8000244")

    def test_lookup_by_eva_or_name_with_category(self):
        stations, _ = self.stations()
        by_eva, by_name = stations.lookup("8000156"), stations.lookup("Heidelberg Hbf")
        self.assertEqual(by_eva, Station("Heidelberg Hbf", "8000156"))
        self.assertEqual((by_name.lat, by_name.lon, by_name.category), (49.4036, 8.6757, 2))
        self.assertIsNone(stations.lookup("Nirgendwo"))
        self.assertEqual(stations.nearest(PARADEPLATZ).category, 1)

    def test_lookup_without_list(self):
        stations, _ = self.stations(IntegrationError("403 nicht abonniert"))
        self.assertIsNone(stations.lookup("8000244"))


if __name__ == "__main__":
    unittest.main()
