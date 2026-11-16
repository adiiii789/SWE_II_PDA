import datetime
import unittest

from backend.integrations.geo import Place
from backend.integrations.http import IntegrationError
from backend.integrations.transitous import TIMEZONE, Transitous, decode_polyline
from tests.integrations.fake_http import FakeHttp

HOME = Place("Paradeplatz, Mannheim", 49.4874, 8.466)
UNI = Place("Bismarckplatz, Heidelberg", 49.4093, 8.6935)
ARRIVE_BY = datetime.datetime(2026, 11, 13, 9, 0, tzinfo=TIMEZONE)
LINE = {"points": "_p~iF~ps|U_ulLnnqC", "precision": 5, "length": 2}   # (38.5, -120.2) → (40.7, -120.95)


def place(name, track="", lat=49.48, lon=8.47, alerts=()):
    return {"name": name, "lat": lat, "lon": lon, "track": track, "scheduledTrack": track, "alerts": list(alerts)}


def leg(mode, start, end, origin, destination, line="", headsign="", scheduled=None, realtime=False,
        cancelled=False, alerts=()):
    """start/end als "HH:MM" Ortszeit (Winterzeit, UTC+1)."""
    def utc(hhmm):
        moment = datetime.datetime(2026, 11, 13, int(hhmm[:2]), int(hhmm[3:]), tzinfo=TIMEZONE)
        return moment.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"mode": mode, "from": origin, "to": destination, "startTime": utc(start), "endTime": utc(end),
            "scheduledStartTime": utc(scheduled or start), "scheduledEndTime": utc(end), "realTime": realtime,
            "displayName": line or None, "headsign": headsign, "cancelled": cancelled, "alerts": list(alerts),
            "legGeometry": LINE}


def itinerary(*legs):
    return {"legs": list(legs), "transfers": sum(1 for x in legs if x["mode"] != "WALK") - 1}


# 1) Bus 33 → S3 (ein Umstieg), an 08:41
WITH_BUS = itinerary(
    leg("WALK", "07:58", "08:02", place("START"), place("Paradeplatz")),
    leg("BUS", "08:02", "08:12", place("Paradeplatz", "B"), place("Mannheim, Hauptbahnhof"), "Bus 33",
        "Hauptbahnhof", scheduled="08:00", realtime=True, alerts=[{"headerText": "Umleitung  wegen Baustelle"}]),
    leg("SUBURBAN", "08:19", "08:35", place("Mannheim, Hauptbahnhof", "9"), place("Heidelberg, Hauptbahnhof", "4"),
        "S3", "Karlsruhe"),
    leg("WALK", "08:35", "08:41", place("Heidelberg, Hauptbahnhof"), place("END")))
# 2) RE direkt, an 08:50, Abfahrt 08:20
DIRECT = itinerary(
    leg("WALK", "08:20", "08:30", place("START"), place("Mannheim, Hauptbahnhof")),
    leg("REGIONAL_RAIL", "08:32", "08:45", place("Mannheim, Hauptbahnhof", "11"), place("Heidelberg, Hauptbahnhof"),
        "RE10a (19259)"),
    leg("WALK", "08:45", "08:50", place("Heidelberg, Hauptbahnhof"), place("END")))
# 3) kommt zu spät an
TOO_LATE = itinerary(
    leg("WALK", "08:40", "08:50", place("START"), place("Mannheim, Hauptbahnhof")),
    leg("SUBURBAN", "08:52", "09:08", place("Mannheim, Hauptbahnhof"), place("Heidelberg, Hauptbahnhof"), "S1"))
WALK_ONLY = itinerary(leg("WALK", "07:00", "08:30", place("START"), place("END")))


def transitous(*itineraries, response=None):
    http = FakeHttp({"/api/v6/plan": response if response is not None else {"itineraries": list(itineraries)}})
    return Transitous(http, "https://motis.example/"), http


class TransitousTest(unittest.TestCase):
    def test_request(self):
        client, http = transitous(DIRECT)
        client.latest_journey(HOME, UNI, ARRIVE_BY, max_transfers=3, min_transfer_minutes=4, max_walk_minutes=20)
        method, url, params, headers = http.calls[0]
        self.assertEqual(url, "https://motis.example/api/v6/plan")
        self.assertEqual((params["fromPlace"], params["toPlace"]), ("49.4874,8.466", "49.4093,8.6935"))
        self.assertEqual((params["time"], params["arriveBy"]), ("2026-11-13T08:00:00Z", "true"))
        self.assertEqual((params["maxTransfers"], params["minTransferTime"]), (3, 4))
        self.assertEqual((params["maxPreTransitTime"], params["maxPostTransitTime"]), (1200, 1200))
        self.assertIn("PersonalDigitalAgent", headers["User-Agent"])

    def test_latest_journey_that_arrives_in_time(self):
        client, _ = transitous(WITH_BUS, DIRECT, TOO_LATE)
        journey = client.latest_journey(HOME, UNI, ARRIVE_BY)
        self.assertEqual([leg.line for leg in journey.rides], ["RE10a (19259)"])
        self.assertEqual(journey.departure, datetime.datetime(2026, 11, 13, 8, 20, tzinfo=TIMEZONE))
        self.assertEqual(journey.arrival.utcoffset(), datetime.timedelta(hours=1))   # Ortszeit
        self.assertEqual(journey.transfers, 0)

    def test_not_before_and_transfers(self):
        client, _ = transitous(WITH_BUS, DIRECT)
        not_before = datetime.datetime(2026, 11, 13, 8, 25, tzinfo=TIMEZONE)   # der RE-Fußweg ginge um 08:20 los
        self.assertIsNone(client.latest_journey(HOME, UNI, ARRIVE_BY, not_before=not_before))
        journey = client.latest_journey(HOME, UNI, ARRIVE_BY, not_before=not_before - datetime.timedelta(minutes=30))
        self.assertEqual(journey.transfers, 0)

    def test_legs_with_bus_platform_delay_and_messages(self):
        client, _ = transitous(WITH_BUS)
        journey = client.earliest_journey(HOME, UNI, datetime.datetime(2026, 11, 13, 7, 50, tzinfo=TIMEZONE))
        walk, bus, train, last = journey.legs
        self.assertTrue(walk.walking)
        self.assertEqual((walk.origin, last.destination), ("Start", "Ziel"))
        self.assertEqual((bus.line, bus.platform, bus.headsign, bus.departure_delay),
                         ("Bus 33", "B", "Hauptbahnhof", 2))
        self.assertFalse(bus.rail)
        self.assertTrue(bus.realtime and journey.realtime)
        self.assertEqual(bus.messages, ("Umleitung wegen Baustelle",))
        self.assertEqual((train.platform, train.arrival_platform), ("9", "4"))
        self.assertTrue(train.rail)
        self.assertFalse(journey.long_distance)
        self.assertEqual(journey.transfers, 1)
        self.assertEqual(bus.geometry, ((-120.2, 38.5), (-120.95, 40.7)))
        self.assertGreater(bus.distance_km, 200)

    def test_earliest_arrival(self):
        client, http = transitous(WITH_BUS, DIRECT)
        journey = client.earliest_journey(HOME, UNI, datetime.datetime(2026, 11, 13, 7, 50, tzinfo=TIMEZONE))
        # Bus + S-Bahn ist um 08:41 da, der RE um 08:50 - aber ohne Umstieg (zählt wie 10 Min.)
        self.assertEqual(journey.arrival, datetime.datetime(2026, 11, 13, 8, 50, tzinfo=TIMEZONE))
        self.assertEqual(http.calls[0][2]["arriveBy"], "false")
        client, _ = transitous(WITH_BUS)
        self.assertEqual(client.earliest_journey(HOME, UNI, datetime.datetime(2026, 11, 13, 7, 50, tzinfo=TIMEZONE))
                         .arrival, datetime.datetime(2026, 11, 13, 8, 41, tzinfo=TIMEZONE))

    def test_cancelled_and_walk_only_are_skipped(self):
        cancelled = itinerary(*DIRECT["legs"][:1], dict(DIRECT["legs"][1], cancelled=True), *DIRECT["legs"][2:])
        client, _ = transitous(cancelled, WALK_ONLY)
        self.assertIsNone(client.latest_journey(HOME, UNI, ARRIVE_BY))

    def test_long_distance(self):
        ice = itinerary(leg("LONG_DISTANCE", "08:00", "08:20", place("A"), place("B"), "ICE 1"))
        client, _ = transitous(ice)
        self.assertTrue(client.latest_journey(HOME, UNI, ARRIVE_BY).long_distance)

    def test_invalid_response(self):
        client, _ = transitous(response={"error": "kaputt"})
        with self.assertRaisesRegex(IntegrationError, "Transitous"):
            client.latest_journey(HOME, UNI, ARRIVE_BY)

    def test_decode_polyline(self):
        points = list(decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@", 5))   # Beispiel aus der Google-Doku
        self.assertEqual(points, [(-120.2, 38.5), (-120.95, 40.7), (-126.453, 43.252)])


if __name__ == "__main__":
    unittest.main()
