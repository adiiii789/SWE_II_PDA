import datetime
import unittest

from backend.integrations.db_timetables import TIMEZONE, DbTimetables, Journey, Station, TrainConnection
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

# Mit Umstieg: Mannheim → Stuttgart (ICE) → Tübingen (RE); kein Zug fährt durch
TUEBINGEN = Station("Tübingen Hbf", "8000141")
STUTTGART = Station("Stuttgart Hbf", "8000096")
ARRIVE_TUEBINGEN = datetime.datetime(2026, 10, 21, 10, 50, tzinfo=TIMEZONE)   # der RE um 10:52 ist zu spät
MANNHEIM_TRANSFER = """<timetable>
  <s id="700-2610210900-1"><tl c="ICE" n="611"/><dp pt="2610210905" pp="4" ppth="Stuttgart Hbf|Ulm Hbf"/></s>
  <s id="701-2610210900-1"><tl c="IC" n="2061"/><dp pt="2610210830" pp="2" ppth="Karlsruhe Hbf"/></s>
</timetable>"""
MANNHEIM_08 = """<timetable>
  <s id="702-2610210800-1"><tl c="ICE" n="513"/><dp pt="2610210805" pp="4" ppth="Stuttgart Hbf"/></s>
</timetable>"""
STUTTGART_09 = """<timetable>
  <s id="700-2610210900-2"><tl c="ICE" n="611"/><ar pt="2610210943" pp="9" ppth="Mannheim Hbf"/>
    <dp pt="2610210948" ppth="Ulm Hbf"/></s>
  <s id="800-2610210900-1"><tl c="RE" n="6"/><dp pt="2610210946" pp="3" l="6" ppth="Tübingen Hbf"/></s>
  <s id="801-2610210900-1"><tl c="RE" n="6"/><dp pt="2610210955" pp="3" l="6" ppth="Tübingen Hbf"/></s>
</timetable>"""
STUTTGART_08 = """<timetable>
  <s id="702-2610210800-2"><tl c="ICE" n="513"/><ar pt="2610210843" pp="8" ppth="Mannheim Hbf"/></s>
  <s id="803-2610210800-1"><tl c="RE" n="6"/><dp pt="2610210855" pp="3" l="6" ppth="Tübingen Hbf"/></s>
</timetable>"""
TUEBINGEN_09 = """<timetable>
  <s id="803-2610210800-5"><tl c="RE" n="6"/><ar pt="2610210955" ppth="Stuttgart Hbf|Plochingen"/></s>
</timetable>"""
TUEBINGEN_10 = """<timetable>
  <s id="800-2610210900-5"><tl c="RE" n="6"/><ar pt="2610211045" ppth="Stuttgart Hbf|Plochingen"/></s>
  <s id="801-2610210900-5"><tl c="RE" n="6"/><ar pt="2610211052" ppth="Stuttgart Hbf|Plochingen"/></s>
</timetable>"""
STATIONS = {"/station/Stuttgart": '<stations><station name="Stuttgart Hbf" eva="8000096"/></stations>',
            "/station/Plochingen": '<stations><station name="Plochingen" eva="8000302"/></stations>'}


def timetables(responses):
    """Nur Timetables (Soll-Fahrplan) - OpenBoards: siehe OpenBoardsTest."""
    http = FakeHttp({**responses, "/plan/": "<timetable/>"})   # alle übrigen Stunden: keine Züge
    return DbTimetables(http, "client", "secret", open_boards=False), http


def transfer_timetables():
    return timetables({**STATIONS, "/plan/8000244/261021/09": MANNHEIM_TRANSFER, "/plan/8000244/261021/08": MANNHEIM_08,
                       "/plan/8000096/261021/09": STUTTGART_09, "/plan/8000096/261021/08": STUTTGART_08,
                       "/plan/8000141/261021/09": TUEBINGEN_09, "/plan/8000141/261021/10": TUEBINGEN_10})


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
        self.assertTrue(http.calls[0][1].endswith("/station/K%C3%B6ln%20Hbf"))

    def test_searches_main_station_first(self):
        # Die echte Suche liefert zu "Mannheim" nur "Mannheim ARENA/Maimarkt"
        db, http = timetables({"/station/Mannheim%20Hbf": '<stations><station name="Mannheim Hbf" eva="8000244"/></stations>',
                               "/station/Mannheim": '<stations><station name="Mannheim ARENA/Maimarkt" eva="8003841"/></stations>'})
        self.assertEqual(db.find_station("Mannheim"), MANNHEIM)
        self.assertEqual(len(http.calls), 1)

    def test_place_name_when_main_station_has_other_spelling(self):
        db, http = timetables({"/station/Weinheim%20Hbf": "<stations/>",
                               "/station/Weinheim": '<stations><station name="Weinheim(Bergstr)Hbf" eva="8000377"/></stations>'})
        self.assertEqual(db.find_station("Weinheim"), Station("Weinheim(Bergstr)Hbf", "8000377"))

    def test_bus_stops_are_skipped(self):
        db, _ = timetables({"/station/Sinsheim%20Hbf": "<stations/>",
                            "/station/Sinsheim": '<stations><station name="Sinsheim (Elsenz) Hauptbahnhof" eva="379849"/></stations>'})
        with self.assertRaisesRegex(IntegrationError, "Kein Bahnhof"):
            db.find_station("Sinsheim")

    def test_no_station(self):
        db, _ = timetables({"/station/": "<stations/>"})
        with self.assertRaisesRegex(IntegrationError, "Kein Bahnhof"):
            db.find_station("Nirgendwo")

    def test_invalid_xml(self):
        db, _ = timetables({"/station/": "kein xml"})
        with self.assertRaisesRegex(IntegrationError, "Ungültige Antwort"):
            db.find_station("Mannheim")


class DirectTest(unittest.TestCase):
    def latest(self, responses, arrive_by=ARRIVE_BY):
        db, _ = timetables(responses)
        return db.latest_journey(MANNHEIM, HEIDELBERG, arrive_by)

    def test_latest_train_that_arrives_in_time(self):
        journey = self.latest({"/plan/8000156/261021/09": HEIDELBERG_09, "/plan/8000156/261021/10": HEIDELBERG_10,
                               "/plan/8000244/261021/09": MANNHEIM_09})
        self.assertEqual(journey.transfers, 0)
        self.assertEqual(journey.train, "RE 10")   # Linie statt Zugnummer, wenn bekannt
        self.assertFalse(journey.long_distance)
        self.assertEqual(journey.departure, datetime.datetime(2026, 10, 21, 9, 32, tzinfo=TIMEZONE))
        self.assertEqual(journey.arrival, datetime.datetime(2026, 10, 21, 9, 50, tzinfo=TIMEZONE))
        self.assertEqual(journey.platform, "3")
        self.assertEqual(journey.legs[0].arrival_platform, "2")

    def test_next_candidate_when_train_not_found_at_origin(self):
        origin_without_re = MANNHEIM_09.replace("111-", "999-")
        journey = self.latest({"/plan/8000156/261021/09": HEIDELBERG_09, "/plan/8000244/261021/09": origin_without_re})
        self.assertEqual(journey.train, "ICE 597")
        self.assertTrue(journey.long_distance)

    def test_no_train(self):
        self.assertIsNone(self.latest({}))

    def test_each_hour_is_fetched_once(self):
        db, http = timetables({"/plan/8000156/261021/09": HEIDELBERG_09})
        db.latest_journey(MANNHEIM, HEIDELBERG, ARRIVE_BY)
        db.latest_journey(MANNHEIM, HEIDELBERG, ARRIVE_BY)
        urls = [call[1] for call in http.calls]
        self.assertEqual(len(urls), len(set(urls)))

    def test_arrive_by_in_other_timezone(self):
        utc = ARRIVE_BY.astimezone(datetime.timezone.utc)   # 08:00 UTC = 10:00 in Berlin
        journey = self.latest({"/plan/8000156/261021/09": HEIDELBERG_09, "/plan/8000244/261021/09": MANNHEIM_09}, utc)
        self.assertEqual(journey.train, "RE 10")

    def test_earliest_after_departure_time(self):
        db, _ = timetables({"/plan/8000156/261021/09": HEIDELBERG_09, "/plan/8000244/261021/09": MANNHEIM_09})
        journey = db.earliest_journey(MANNHEIM, HEIDELBERG, datetime.datetime(2026, 10, 21, 9, 20, tzinfo=TIMEZONE))
        self.assertEqual(journey.train, "ICE 597")   # 09:25 → 09:40 ist früher da als der RE
        late = db.earliest_journey(MANNHEIM, HEIDELBERG, datetime.datetime(2026, 10, 21, 9, 30, tzinfo=TIMEZONE))
        self.assertEqual(late.train, "RE 10")


class TransferTest(unittest.TestCase):
    def test_latest_with_one_transfer(self):
        db, _ = transfer_timetables()
        journey = db.latest_journey(MANNHEIM, TUEBINGEN, ARRIVE_TUEBINGEN)
        self.assertEqual(journey.transfers, 1)
        first, second = journey.legs
        self.assertEqual((first.train, first.destination, first.arrival_platform), ("ICE 513", STUTTGART, "8"))
        self.assertEqual((second.train, second.origin, second.platform), ("RE 6", STUTTGART, "3"))
        # ICE 611 kommt 09:43 an, der RE um 09:46 wäre unter 5 Min. Umstieg, der um 09:55 kommt zu spät an.
        # Also der ICE eine Stunde früher - mit dem ersten RE danach (früher da als der um 09:46)
        self.assertEqual(journey.departure, datetime.datetime(2026, 10, 21, 8, 5, tzinfo=TIMEZONE))
        self.assertEqual(journey.arrival, datetime.datetime(2026, 10, 21, 9, 55, tzinfo=TIMEZONE))
        self.assertTrue(journey.long_distance)
        self.assertEqual(journey.train, "ICE 513 → RE 6")

    def test_shorter_transfer_time_allows_tighter_connection(self):
        db, _ = transfer_timetables()
        journey = db.latest_journey(MANNHEIM, TUEBINGEN, ARRIVE_TUEBINGEN, min_transfer_minutes=2)
        self.assertEqual(journey.departure, datetime.datetime(2026, 10, 21, 9, 5, tzinfo=TIMEZONE))
        self.assertEqual(journey.arrival, datetime.datetime(2026, 10, 21, 10, 45, tzinfo=TIMEZONE))

    def test_earliest_with_transfer(self):
        db, _ = transfer_timetables()
        journey = db.earliest_journey(MANNHEIM, TUEBINGEN, datetime.datetime(2026, 10, 21, 9, 0, tzinfo=TIMEZONE))
        self.assertEqual(journey.arrival, datetime.datetime(2026, 10, 21, 10, 52, tzinfo=TIMEZONE))

    def test_only_direct_when_transfers_are_off(self):
        db, http = transfer_timetables()
        self.assertIsNone(db.latest_journey(MANNHEIM, TUEBINGEN, ARRIVE_TUEBINGEN, max_transfers=0))
        self.assertFalse(any("/station/" in call[1] for call in http.calls))

    def test_unknown_transfer_station_is_skipped(self):
        db, _ = timetables({"/station/": IntegrationError("weg"), "/plan/8000244/261021/09": MANNHEIM_TRANSFER,
                            "/plan/8000141/261021/10": TUEBINGEN_10})
        self.assertIsNone(db.latest_journey(MANNHEIM, TUEBINGEN, ARRIVE_TUEBINGEN))

    def test_single_train_counts_as_journey_without_transfer(self):
        direct = Journey((TrainConnection("RE 1", False, MANNHEIM, TUEBINGEN,
                                          datetime.datetime(2026, 10, 21, 9, 0, tzinfo=TIMEZONE), ARRIVE_TUEBINGEN),))
        self.assertEqual(direct.transfers, 0)
        self.assertEqual(direct.legs[0].legs, (direct.legs[0],))
        self.assertEqual(direct.legs[0].transfers, 0)


# --- OpenBoards ------------------------------------------------------------------------------
EMPTY_BOARD = {"departures": [], "arrivals": [], "stopPlaces": [], "meta": {}}


class BoardsHttp(FakeHttp):
    """OpenBoards-Antworten je (Tafel, EVA, Stunde); GET (Timetables) wie FakeHttp."""

    def __init__(self, boards, responses=None):
        super().__init__({**(responses or {}), "/plan/": "<timetable/>"})   # erster Treffer gewinnt
        self.boards = boards

    def post_json(self, url, body, headers=None):
        self.calls.append(("POST", url, body, headers))
        if isinstance(self.boards, Exception):
            raise self.boards
        kind = url.rsplit("/", 1)[1]
        eva = body["stopPlaceOrStation"]["evaNumbers"][0]
        hour = body["timeWindow"]["timeStart"][11:13]
        return self.boards.get((kind, eva, hour), EMPTY_BOARD)


def at(hhmm):
    return f"2026-10-21T{hhmm}:00+02:00"


def entry(journey, category, time, scheduled=None, line="", number=1, platform="", via=(), origin="", destination="",
          messages=(), cancelled=False, kind="REGIONAL_TRAIN"):
    return {"journeyId": journey, "time": at(time), "timeSchedule": at(scheduled or time), "timeType": "PREVIEW",
            "platform": {"name": platform} if platform else None, "cancelled": cancelled, "messages": list(messages),
            "evaNumber": "x", "journeyInfo": {"origin": {"evaNumber": origin}, "destination": {"evaNumber": destination}},
            "transport": {"category": category, "type": kind, "journeyNumber": number,
                          "line": {"name": line} if line else None,
                          "via": [{"evaNumber": eva, "displayPriority": i + 1} for i, eva in enumerate(via)]}}


def board(kind, *entries, places=(), messages=None):
    return {kind: list(entries), "meta": {"consideredStopPlaces": []}, "messages": messages or {},
            "stopPlaces": [{"evaNumber": eva, "localizedNames": [{"language": "deu", "name": name}]}
                           for eva, name in places]}


REPAIR = {"notes": [{"messageID": 7, "descriptions": [{"language": "eng", "text": "Repair"},
                                                      {"language": "deu", "text": "Reparatur am Zug"}]}],
          "risCauseCodes": [{"messageID": 8, "code": "00", "descriptions": [{"language": "deu", "text": "keine"}]}]}
DIRECT_BOARDS = {
    ("departures", "8000244", "09"): board(
        "departures",
        entry("J1", "RE", "09:37", "09:32", line="10", platform="3", via=("8000156",), destination="8000156"),
        entry("J2", "ICE", "09:25", number=597, platform="1", destination="8000156", kind="HIGH_SPEED_TRAIN")),
    ("arrivals", "8000156", "09"): board(
        "arrivals",
        entry("J1", "RE", "09:55", "09:50", line="10", platform="2", origin="8000105", via=("8000244",),
              messages=(7, 8)),
        entry("J2", "ICE", "09:40", number=597, platform="5", origin="8000244", kind="HIGH_SPEED_TRAIN"),
        messages=REPAIR),
}


def open_boards(boards, responses=None, clock=lambda: 0.0):
    http = BoardsHttp(boards, responses)
    return DbTimetables(http, "client", "secret", clock=clock), http


class OpenBoardsTest(unittest.TestCase):
    def test_realtime_times_delay_and_messages(self):
        db, http = open_boards(DIRECT_BOARDS)
        journey = db.latest_journey(MANNHEIM, HEIDELBERG, ARRIVE_BY)
        self.assertTrue(journey.realtime)
        self.assertEqual(journey.train, "RE 10")
        leg = journey.legs[0]
        self.assertEqual(leg.departure, datetime.datetime(2026, 10, 21, 9, 37, tzinfo=TIMEZONE))
        self.assertEqual((leg.departure_delay, leg.arrival_delay), (5, 5))
        self.assertEqual((leg.platform, leg.arrival_platform), ("3", "2"))
        self.assertEqual(journey.messages, ("Reparatur am Zug",))   # Code 00 = keine Begründung
        self.assertFalse(any("/plan/" in call[1] for call in http.calls))

    def test_request_body_and_headers(self):
        db, http = open_boards(DIRECT_BOARDS)
        db.latest_journey(MANNHEIM, HEIDELBERG, ARRIVE_BY)
        method, url, body, headers = next(call for call in http.calls if call[0] == "POST")
        self.assertTrue(url.endswith("/open-boards/v1/departures"))
        self.assertEqual(body["stopPlaceOrStation"], {"evaNumbers": ["8000244"]})
        self.assertEqual(body["timeWindow"], {"timeStart": "2026-10-21T06:00:00+02:00",
                                              "timeEnd": "2026-10-21T07:00:00+02:00"})
        self.assertTrue(body["noCancellations"])
        self.assertEqual((headers["DB-Client-Id"], headers["DB-Api-Key"]), ("client", "secret"))
        self.assertIn("application/vnd.de.db.ris+json", headers["Accept"])

    def test_delayed_train_arrives_too_late(self):
        boards = dict(DIRECT_BOARDS)
        boards[("arrivals", "8000156", "09")] = board(
            "arrivals", entry("J2", "ICE", "09:40", number=597, origin="8000244", kind="HIGH_SPEED_TRAIN"))
        boards[("arrivals", "8000156", "10")] = board(
            "arrivals", entry("J1", "RE", "10:05", "09:50", line="10", origin="8000105"))
        db, _ = open_boards(boards)
        journey = db.latest_journey(MANNHEIM, HEIDELBERG, ARRIVE_BY)
        self.assertEqual(journey.train, "ICE 597")
        self.assertTrue(journey.long_distance)

    def test_cancelled_stop_is_ignored(self):
        boards = dict(DIRECT_BOARDS)
        boards[("arrivals", "8000156", "09")] = board(
            "arrivals", entry("J1", "RE", "09:55", line="10", cancelled=True),
            entry("J2", "ICE", "09:40", number=597, kind="HIGH_SPEED_TRAIN"))
        db, _ = open_boards(boards)
        self.assertEqual(db.latest_journey(MANNHEIM, HEIDELBERG, ARRIVE_BY).train, "ICE 597")

    def test_transfer_found_from_eva_paths(self):
        boards = {
            ("departures", "8000244", "08"): board(
                "departures", entry("ICE513", "ICE", "08:05", number=513, via=("8000096",), destination="8000170",
                                    kind="HIGH_SPEED_TRAIN"),
                places=(("8000096", "Stuttgart Hbf"),)),
            ("arrivals", "8000141", "09"): board(
                "arrivals", entry("RE6", "RE", "09:55", line="6", origin="8000096", via=("8000302",)),
                places=(("8000096", "Stuttgart Hbf"), ("8000302", "Plochingen"))),
            ("arrivals", "8000096", "08"): board(
                "arrivals", entry("ICE513", "ICE", "08:45", "08:43", number=513, platform="8",
                                  kind="HIGH_SPEED_TRAIN")),
            ("departures", "8000096", "08"): board(
                "departures", entry("RE6", "RE", "08:55", line="6", platform="3", destination="8000141")),
        }
        db, http = open_boards(boards)
        journey = db.latest_journey(MANNHEIM, TUEBINGEN, ARRIVE_TUEBINGEN)
        self.assertEqual(journey.train, "ICE 513 → RE 6")
        self.assertEqual(journey.legs[0].destination, STUTTGART)   # Name aus stopPlaces, ohne /station
        self.assertEqual((journey.legs[0].arrival_delay, journey.legs[1].platform), (2, "3"))
        self.assertFalse(any(call[0] == "GET" for call in http.calls))

    def test_missed_connection_because_of_delay(self):
        boards = {
            ("departures", "8000244", "08"): board(
                "departures", entry("ICE513", "ICE", "08:05", number=513, via=("8000096",), kind="HIGH_SPEED_TRAIN"),
                places=(("8000096", "Stuttgart Hbf"),)),
            ("arrivals", "8000141", "09"): board("arrivals", entry("RE6", "RE", "09:55", line="6", via=("8000096",))),
            ("arrivals", "8000096", "08"): board(
                "arrivals", entry("ICE513", "ICE", "08:53", "08:43", number=513, kind="HIGH_SPEED_TRAIN")),
            ("departures", "8000096", "08"): board("departures", entry("RE6", "RE", "08:55", line="6")),
        }
        db, _ = open_boards(boards)
        self.assertIsNone(db.latest_journey(MANNHEIM, TUEBINGEN, ARRIVE_TUEBINGEN))   # 2 Min. zum Umsteigen

    def test_falls_back_to_timetables_without_open_boards(self):
        db, http = open_boards(IntegrationError("apis.deutschebahn.com antwortet mit 403: not subscribed"),
                               {"/plan/8000156/261021/09": HEIDELBERG_09, "/plan/8000244/261021/09": MANNHEIM_09})
        journey = db.latest_journey(MANNHEIM, HEIDELBERG, ARRIVE_BY)
        self.assertEqual(journey.train, "RE 10")
        self.assertFalse(journey.realtime)
        self.assertEqual(journey.legs[0].departure_delay, 0)

    def test_not_found_means_empty_board(self):
        db, http = open_boards(IntegrationError("apis.deutschebahn.com antwortet mit 404: Not found"))
        self.assertIsNone(db.latest_journey(MANNHEIM, HEIDELBERG, ARRIVE_BY))
        self.assertFalse(any("/plan/" in call[1] for call in http.calls))

    def test_actual_stop_in_transfer_area(self):
        # Die Tafel von "Frankfurt Hbf (tief)" enthält auch die Züge oben im Hauptbahnhof
        tief, main = Station("Frankfurt Hbf (tief)", "8098105"), Station("Frankfurt(Main)Hbf", "8000105")
        arrival = entry("TGV", "TGV", "09:50", platform="3", origin="8000244", kind="HIGH_SPEED_TRAIN")
        arrival["evaNumber"] = main.eva
        db, _ = open_boards({
            ("departures", "8000244", "09"): board("departures", entry("TGV", "TGV", "09:10", destination=tief.eva)),
            ("arrivals", tief.eva, "09"): board("arrivals", arrival, places=((main.eva, main.name),)),
        })
        journey = db.latest_journey(MANNHEIM, tief, ARRIVE_BY)
        self.assertEqual(journey.destination, main)

    def test_traveller_label_and_long_messages(self):
        long_text = "Aufzug außer Betrieb. " * 20
        departures = board("departures", dict(entry("J1", "S", "09:30", line="1", destination="8000156"),
                                              messages=[1, 2]),
                           messages={"notes": [{"messageID": 1, "descriptions": [{"language": "deu", "text": long_text}]}],
                                     "risCauseCodes": [{"messageID": 2, "code": "43", "descriptions": [
                                         {"language": "deu", "text": "Verspätung eines vorausfahrenden Zuges"}]}]})
        arrivals = board("arrivals", entry("J1", "S", "09:45", line="1"))
        for item in departures["departures"] + arrivals["arrivals"]:
            item["transport"]["journeyDescription"] = "S1"
        db, _ = open_boards({("departures", "8000244", "09"): departures, ("arrivals", "8000156", "09"): arrivals})
        journey = db.latest_journey(MANNHEIM, HEIDELBERG, ARRIVE_BY)
        self.assertEqual(journey.train, "S1")
        reason, note = journey.messages
        self.assertEqual(reason, "Verspätung eines vorausfahrenden Zuges")   # Gründe vor Hinweisen
        self.assertLessEqual(len(note), 160)
        self.assertTrue(note.endswith(" …"))

    def test_no_departure_in_the_past(self):
        db, _ = open_boards(DIRECT_BOARDS)
        not_before = datetime.datetime(2026, 10, 21, 9, 30, tzinfo=TIMEZONE)   # der ICE um 09:25 ist schon weg
        journey = db.latest_journey(MANNHEIM, HEIDELBERG, ARRIVE_BY, not_before=not_before)
        self.assertEqual(journey.train, "RE 10")
        self.assertIsNone(db.latest_journey(MANNHEIM, HEIDELBERG, ARRIVE_BY,
                                            not_before=datetime.datetime(2026, 10, 21, 9, 40, tzinfo=TIMEZONE)))
        self.assertIsNone(db.latest_journey(MANNHEIM, HEIDELBERG, ARRIVE_BY, not_before=ARRIVE_BY))

    def test_via_stops_between_origin_and_destination(self):
        boards = dict(DIRECT_BOARDS)
        boards[("departures", "8000244", "09")] = board("departures", entry(
            "J1", "RE", "09:37", line="10", via=("8000300", "8000301", "8000156", "8000400"), destination="8000500"))
        db, _ = open_boards(boards)
        leg = db.latest_journey(MANNHEIM, HEIDELBERG, ARRIVE_BY).legs[0]
        self.assertEqual(leg.via, ("8000300", "8000301"))   # nur bis Heidelberg, in Fahrtrichtung

    def test_no_via_stops_from_timetables(self):
        db, _ = timetables({"/plan/8000156/261021/09": HEIDELBERG_09, "/plan/8000244/261021/09": MANNHEIM_09})
        self.assertEqual(db.latest_journey(MANNHEIM, HEIDELBERG, ARRIVE_BY).legs[0].via, ())

    def test_boards_are_cached_briefly(self):
        now = [0.0]
        db, http = open_boards(DIRECT_BOARDS, clock=lambda: now[0])
        db.latest_journey(MANNHEIM, HEIDELBERG, ARRIVE_BY)
        first = len(http.calls)
        db.latest_journey(MANNHEIM, HEIDELBERG, ARRIVE_BY)
        self.assertEqual(len(http.calls), first)
        now[0] = 61.0
        db.latest_journey(MANNHEIM, HEIDELBERG, ARRIVE_BY)
        self.assertEqual(len(http.calls), 2 * first)


# Zwei Umstiege: Mannheim → Stuttgart (ICE 1, über Hockenheim, Graben-Neudorf, Bruchsal) → Ulm (IC 2)
# → Friedrichshafen (RB 3). Kein Zug ab Mannheim kommt an einem Bahnhof vorbei, von dem einer nach
# Friedrichshafen fährt - erst die Tafeln von Stuttgart und Ulm verbinden.
FRIEDRICHSHAFEN = Station("Friedrichshafen Stadt", "8000112", 47.653, 9.474)
ULM = Station("Ulm Hbf", "8000170", 48.399, 9.983)
HOCKENHEIM, GRABEN, BRUCHSAL = "8000162", "8000140", "8000055"
ARRIVE_FN = datetime.datetime(2026, 10, 21, 11, 30, tzinfo=TIMEZONE)
NAMES = ((STUTTGART.eva, STUTTGART.name), (ULM.eva, ULM.name), (FRIEDRICHSHAFEN.eva, FRIEDRICHSHAFEN.name),
         (HOCKENHEIM, "Hockenheim"), (GRABEN, "Graben-Neudorf"), (BRUCHSAL, "Bruchsal"))
TWO_TRANSFER_BOARDS = {
    ("departures", "8000244", "08"): board(
        "departures", entry("ICE1", "ICE", "08:05", number=1, platform="4", via=(HOCKENHEIM, GRABEN, BRUCHSAL),
                            destination=STUTTGART.eva, kind="HIGH_SPEED_TRAIN"), places=NAMES),
    ("arrivals", STUTTGART.eva, "08"): board(
        "arrivals", entry("ICE1", "ICE", "08:45", number=1, via=(HOCKENHEIM, GRABEN, BRUCHSAL), origin="8000244",
                          kind="HIGH_SPEED_TRAIN")),
    ("departures", STUTTGART.eva, "08"): board(
        "departures", entry("IC2", "IC", "08:55", number=2, platform="7", destination=ULM.eva,
                            kind="INTERCITY_TRAIN")),
    ("arrivals", ULM.eva, "09"): board(
        "arrivals", entry("IC2", "IC", "09:50", number=2, origin=STUTTGART.eva, kind="INTERCITY_TRAIN")),
    ("departures", ULM.eva, "10"): board(
        "departures", entry("RB3", "RB", "10:00", line="3", platform="1", destination=FRIEDRICHSHAFEN.eva)),
    ("arrivals", FRIEDRICHSHAFEN.eva, "11"): board(
        "arrivals", entry("RB3", "RB", "11:05", line="3", origin=ULM.eva), places=NAMES),
}
STADA = {STUTTGART.eva: Station(STUTTGART.name, STUTTGART.eva, 48.784, 9.182, 1), ULM.eva: ULM,
         HOCKENHEIM: Station("Hockenheim", HOCKENHEIM, 49.32, 8.55, 4),
         GRABEN: Station("Graben-Neudorf", GRABEN, 49.17, 8.49, 4),
         BRUCHSAL: Station("Bruchsal", BRUCHSAL, 49.12, 8.59, 3),
         "8000244": Station("Mannheim Hbf", "8000244", 49.479, 8.469, 1), FRIEDRICHSHAFEN.eva: FRIEDRICHSHAFEN}


def boarded(http):
    """EVA-Nummern, deren Tafeln abgefragt wurden."""
    return {call[2]["stopPlaceOrStation"]["evaNumbers"][0] for call in http.calls if call[0] == "POST"}


class MoreTransfersTest(unittest.TestCase):
    def test_two_transfers(self):
        db, _ = open_boards(TWO_TRANSFER_BOARDS)
        journey = db.latest_journey(MANNHEIM, FRIEDRICHSHAFEN, ARRIVE_FN, max_transfers=2)
        self.assertEqual(journey.train, "ICE 1 → IC 2 → RB 3")
        self.assertEqual(journey.transfers, 2)
        first, second, third = journey.legs
        self.assertEqual((first.destination, second.origin, second.platform), (STUTTGART, STUTTGART, "7"))
        self.assertEqual((second.destination.name, third.origin.name, third.platform), ("Ulm Hbf", "Ulm Hbf", "1"))
        self.assertEqual(first.via, (HOCKENHEIM, GRABEN, BRUCHSAL))
        self.assertEqual((journey.departure, journey.arrival),
                         (datetime.datetime(2026, 10, 21, 8, 5, tzinfo=TIMEZONE),
                          datetime.datetime(2026, 10, 21, 11, 5, tzinfo=TIMEZONE)))

    def test_not_found_with_one_transfer(self):
        db, _ = open_boards(TWO_TRANSFER_BOARDS)
        self.assertIsNone(db.latest_journey(MANNHEIM, FRIEDRICHSHAFEN, ARRIVE_FN, max_transfers=1))

    def test_earliest_with_two_transfers(self):
        db, _ = open_boards(TWO_TRANSFER_BOARDS)
        journey = db.earliest_journey(MANNHEIM, FRIEDRICHSHAFEN, datetime.datetime(2026, 10, 21, 8, 0, tzinfo=TIMEZONE),
                                      max_transfers=3)
        self.assertEqual(journey.transfers, 2)

    def test_missed_connection_with_two_transfers(self):
        boards = dict(TWO_TRANSFER_BOARDS)
        boards[("arrivals", ULM.eva, "09")] = board(   # 4 Min. in Ulm: zu knapp
            "arrivals", entry("IC2", "IC", "09:56", number=2, origin=STUTTGART.eva, kind="INTERCITY_TRAIN"))
        db, _ = open_boards(boards)
        self.assertIsNone(db.latest_journey(MANNHEIM, FRIEDRICHSHAFEN, ARRIVE_FN, max_transfers=2))
        db, _ = open_boards(boards)
        self.assertIsNotNone(db.latest_journey(MANNHEIM, FRIEDRICHSHAFEN, ARRIVE_FN, max_transfers=2,
                                               min_transfer_minutes=3))

    def test_big_stations_first_with_station_data(self):
        db, http = open_boards(TWO_TRANSFER_BOARDS)
        db.locate = STADA.get
        journey = db.latest_journey(MANNHEIM, FRIEDRICHSHAFEN, ARRIVE_FN, max_transfers=2)
        self.assertEqual(journey.transfers, 2)
        self.assertIn(STUTTGART.eva, boarded(http))
        self.assertNotIn(HOCKENHEIM, boarded(http))   # kleiner Halt, Stuttgart und Bruchsal sind größer
        self.assertEqual(journey.legs[0].destination.category, 1)

    def test_stations_off_the_route_are_skipped(self):
        db, http = open_boards(TWO_TRANSFER_BOARDS)
        db.locate = {**STADA, STUTTGART.eva: Station(STUTTGART.name, STUTTGART.eva, 53.55, 10.0, 1)}.get   # Hamburg
        self.assertIsNone(db.latest_journey(MANNHEIM, FRIEDRICHSHAFEN, ARRIVE_FN, max_transfers=2))
        self.assertNotIn(STUTTGART.eva, boarded(http))

    def test_no_extra_stations_when_a_direct_train_exists(self):
        db, http = open_boards(DIRECT_BOARDS)
        self.assertEqual(db.latest_journey(MANNHEIM, HEIDELBERG, ARRIVE_BY, max_transfers=3).transfers, 0)
        self.assertEqual(boarded(http), {MANNHEIM.eva, HEIDELBERG.eva})

    def test_two_transfers_from_timetables(self):
        db, _ = timetables({
            "/station/": IntegrationError("nicht nötig"),
            "/plan/8000244/261021/08": '<timetable><s id="1-1"><tl c="ICE" n="1"/>'
                                       '<dp pt="2610210805" ppth="Stuttgart Hbf"/></s></timetable>',
            "/plan/8000112/261021/11": '<timetable><s id="3-3"><tl c="RB" n="3"/>'
                                       '<ar pt="2610211105" ppth="Ulm Hbf"/></s></timetable>',
            "/plan/8000096/261021/08": '<timetable><s id="1-2"><tl c="ICE" n="1"/><ar pt="2610210845"/></s>'
                                       '<s id="2-1"><tl c="IC" n="2"/><dp pt="2610210855" ppth="Ulm Hbf"/></s></timetable>',
            "/plan/8000170/261021/09": '<timetable><s id="2-2"><tl c="IC" n="2"/><ar pt="2610210950"/></s></timetable>',
            "/plan/8000170/261021/10": '<timetable><s id="3-1"><tl c="RB" n="3"/><dp pt="2610211000"/></s></timetable>',
        })
        db.locate = {"Stuttgart Hbf": STADA[STUTTGART.eva], "Ulm Hbf": ULM}.get   # Namen wie im Laufweg
        journey = db.latest_journey(MANNHEIM, FRIEDRICHSHAFEN, ARRIVE_FN, max_transfers=2)
        self.assertEqual(journey.train, "ICE 1 → IC 2 → RB 3")
        self.assertFalse(journey.realtime)


if __name__ == "__main__":
    unittest.main()
