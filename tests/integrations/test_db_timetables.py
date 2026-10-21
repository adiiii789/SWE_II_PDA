import datetime
import unittest

from backend.integrations.db_timetables import TIMEZONE, DbTimetables, Station
from backend.integrations.http import IntegrationError
from tests.integrations.fake_http import FakeHttp

MANNHEIM = Station("Mannheim Hbf", "8000244")
HEIDELBERG = Station("Heidelberg Hbf", "8000156")
ARRIVE_BY = datetime.datetime(2026, 10, 21, 10, 0, tzinfo=TIMEZONE)

HEIDELBERG_09 = """<timetable station="Heidelberg Hbf">
  <s id="111-2610210930-5"><tl c="RE" n="4711"/>
    <ar pt="2610210950" pp="2" l="10" ppth="Frankfurt(Main)Hbf|Mannheim Hbf"/><dp pt="2610210952" l="10"/></s>
  <s id="222-2610210900-3"><tl c="ICE" n="597"/><ar pt="2610210940" pp="5" ppth="Mannheim Hbf"/></s>
  <s id="333-2610210900-7"><tl c="S" n="9"/><ar pt="2610210955" ppth="Darmstadt Hbf"/></s>
  <s id="444-2610210900-1"><tl c="S" n="1"/><dp pt="2610210958" ppth="Mannheim Hbf"/></s>
</timetable>"""
HEIDELBERG_10 = """<timetable><s id="555-2610211000-2"><tl c="RE" n="1"/>
  <ar pt="2610211020" ppth="Mannheim Hbf"/></s></timetable>"""   # kommt zu spät an
MANNHEIM_09 = """<timetable station="Mannheim Hbf">
  <s id="111-2610210930-4"><tl c="RE" n="4711"/><dp pt="2610210932" pp="3" l="10" ppth="Heidelberg Hbf"/></s>
  <s id="222-2610210900-2"><tl c="ICE" n="597"/><dp pt="2610210925" pp="1" ppth="Heidelberg Hbf"/></s>
</timetable>"""


def timetables(responses):
    http = FakeHttp({**responses, "/plan/": "<timetable/>"})   # alle übrigen Stunden: keine Züge
    return DbTimetables(http, "client", "secret"), http


class FindStationTest(unittest.TestCase):
    def test_prefers_main_station_and_sends_keys(self):
        db, http = timetables({"/station/Mannheim": """<stations>
            <station name="Mannheim-Neckarau" eva="8003800"/><station name="Mannheim Hbf" eva="8000244"/>
        </stations>"""})
        self.assertEqual(db.find_station("Mannheim"), MANNHEIM)
        self.assertEqual(http.calls[0][3]["DB-Client-Id"], "client")
        self.assertEqual(http.calls[0][3]["DB-Api-Key"], "secret")

    def test_first_station_without_main_station(self):
        db, _ = timetables({"/station/": '<stations><station name="Schwetzingen" eva="8000141"/></stations>'})
        self.assertEqual(db.find_station("Schwetzingen").eva, "8000141")

    def test_name_is_url_encoded(self):
        db, http = timetables({"/station/": '<stations><station name="Köln Hbf" eva="8000207"/></stations>'})
        db.find_station("Köln")
        self.assertTrue(http.calls[0][1].endswith("/station/K%C3%B6ln"))

    def test_no_station(self):
        db, _ = timetables({"/station/": "<stations/>"})
        with self.assertRaisesRegex(IntegrationError, "Kein Bahnhof"):
            db.find_station("Nirgendwo")

    def test_invalid_xml(self):
        db, _ = timetables({"/station/": "kein xml"})
        with self.assertRaisesRegex(IntegrationError, "Ungültige Antwort"):
            db.find_station("Mannheim")


class LatestDirectTest(unittest.TestCase):
    def test_latest_train_that_arrives_in_time(self):
        db, _ = timetables({"/plan/8000156/261021/09": HEIDELBERG_09, "/plan/8000156/261021/10": HEIDELBERG_10,
                            "/plan/8000244/261021/09": MANNHEIM_09})
        connection = db.latest_direct(MANNHEIM, HEIDELBERG, ARRIVE_BY)
        self.assertEqual(connection.train, "RE 10")   # Linie statt Zugnummer, wenn bekannt
        self.assertFalse(connection.long_distance)
        self.assertEqual(connection.departure, datetime.datetime(2026, 10, 21, 9, 32, tzinfo=TIMEZONE))
        self.assertEqual(connection.arrival, datetime.datetime(2026, 10, 21, 9, 50, tzinfo=TIMEZONE))
        self.assertEqual(connection.platform, "3")

    def test_next_candidate_when_train_not_found_at_origin(self):
        origin_without_re = MANNHEIM_09.replace("111-", "999-")
        db, _ = timetables({"/plan/8000156/261021/09": HEIDELBERG_09, "/plan/8000244/261021/09": origin_without_re})
        connection = db.latest_direct(MANNHEIM, HEIDELBERG, ARRIVE_BY)
        self.assertEqual(connection.train, "ICE 597")
        self.assertTrue(connection.long_distance)

    def test_no_direct_train(self):
        db, _ = timetables({})
        self.assertIsNone(db.latest_direct(MANNHEIM, HEIDELBERG, ARRIVE_BY))

    def test_each_hour_is_fetched_once(self):
        db, http = timetables({"/plan/8000156/261021/09": HEIDELBERG_09})
        db.latest_direct(MANNHEIM, HEIDELBERG, ARRIVE_BY)
        db.latest_direct(MANNHEIM, HEIDELBERG, ARRIVE_BY)
        urls = [call[1] for call in http.calls]
        self.assertEqual(len(urls), len(set(urls)))

    def test_arrive_by_in_other_timezone(self):
        db, _ = timetables({"/plan/8000156/261021/09": HEIDELBERG_09, "/plan/8000244/261021/09": MANNHEIM_09})
        utc = ARRIVE_BY.astimezone(datetime.timezone.utc)   # 08:00 UTC = 10:00 in Berlin
        self.assertEqual(db.latest_direct(MANNHEIM, HEIDELBERG, utc).train, "RE 10")


if __name__ == "__main__":
    unittest.main()
