import datetime
import unittest

from backend.integrations.geo import Place
from backend.integrations.http import IntegrationError
from backend.integrations.vvs import TIMEZONE, Vvs, covers
from tests.integrations.fake_http import FakeHttp

HBF = Place("Arnulf-Klett-Platz 2, Stuttgart", 48.78433, 9.18143)
UNI = Place("Pfaffenwaldring 53, Stuttgart", 48.74514, 9.10596)
HEIDELBERG = Place("Bismarckplatz, Heidelberg", 49.4093, 8.6935)
ARRIVE_BY = datetime.datetime(2026, 11, 13, 8, 0, tzinfo=TIMEZONE)


def utc(hhmm):
    """Ortszeit "HH:MM" (Winterzeit) als EFA-Zeit in UTC."""
    moment = datetime.datetime(2026, 11, 13, int(hhmm[:2]), int(hhmm[3:]), tzinfo=TIMEZONE)
    return moment.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stop(name, platform="", kind="platform", coord=(48.78, 9.18), dep=None, dep_planned=None, arr=None,
         arr_planned=None):
    place = {"name": name, "type": kind, "coord": list(coord), "properties": {"platform": platform} if platform else {}}
    if kind == "platform":
        place["parent"] = {"name": name, "type": "stop"}
    if dep:
        place["departureTimePlanned"], place["departureTimeEstimated"] = utc(dep_planned or dep), utc(dep)
    if arr:
        place["arrivalTimePlanned"], place["arrivalTimeEstimated"] = utc(arr_planned or arr), utc(arr)
    return place


def footpath(origin, destination, minutes=5):
    return {"duration": minutes * 60, "origin": origin, "destination": destination,
            "transportation": {"product": {"class": 100, "name": "footpath"}},
            "coords": [origin["coord"], destination["coord"]]}


def ride(product_class, product, line, headsign, origin, destination, status=("MONITORED",), infos=()):
    return {"origin": origin, "destination": destination, "realtimeStatus": list(status), "infos": list(infos),
            "transportation": {"disassembledName": line, "number": line, "product": {"class": product_class,
                                                                                   "name": product},
                               "destination": {"name": headsign}},
            "coords": [origin["coord"], [48.76, 9.15], destination["coord"]]}


TICKETS = [
    {"name": "EinzelTicket Erwachsene (Automat)", "person": "ADULT", "timeValidity": "SINGLE", "priceBrutto": 3.7},
    {"name": "EinzelTicket Erwachsene", "person": "ADULT", "timeValidity": "SINGLE", "priceBrutto": 3.45},
    {"name": "EinzelZuschlag 1. Klasse", "person": "ADULT", "timeValidity": "SINGLE", "priceBrutto": 1.8},
    {"name": "EinzelTicket Kind", "person": "CHILD", "timeValidity": "SINGLE", "priceBrutto": 1.67},
    {"name": "MonatsTicket", "person": "ADULT", "timeValidity": "MONTH", "priceBrutto": 99.0},
]
LINE_INFO = {"type": "lineInfo", "infoLinks": [{"urlText": "Aufzug an der   Universität außer Betrieb"}]}
OTHER_END = {"type": "lineInfo", "priority": "normal", "infoLinks": [{"urlText": "Schorndorf: Gleis 3 gesperrt"}]}
URGENT = {"type": "lineInfo", "priority": "veryHigh", "infoLinks": [{"urlText": "S-Bahn-Streik"}]}
# Fußweg → Bus 42 → S1 (Umstieg am Hbf, 7 Min.) → Fußweg, an 07:50
BUS_AND_S1 = {"interchanges": 1, "fare": {"tickets": TICKETS}, "legs": [
    footpath(stop("Mitte, Arnulf-Klett-Platz 2", kind="address", dep="07:20"),
             stop("Hauptbahnhof (Arnulf-Klett-Platz)", arr="07:24")),
    ride(5, "Bus", "42", "Erwin-Schoettle-Platz", stop("Hauptbahnhof (Arnulf-Klett-Platz)", "C", dep="07:26",
                                                        dep_planned="07:24"),
         stop("Stuttgart Hauptbahnhof (tief)", arr="07:28")),
    ride(1, "S-Bahn", "S1", "Herrenberg", stop("Stuttgart Hauptbahnhof (tief)", "101", dep="07:35"),
         stop("Universität", "1", arr="07:45"), infos=[LINE_INFO, OTHER_END, URGENT]),
    footpath(stop("Universität", arr="07:45"), stop("Vaihingen, Pfaffenwaldring 53", kind="address", arr="07:50")),
]}
# nur S2, an 07:55 - knapper Umstieg in BUS_AND_S1 macht den Unterschied nicht
S2 = {"interchanges": 0, "fare": {"tickets": TICKETS}, "legs": [
    footpath(stop("Mitte, Arnulf-Klett-Platz 2", kind="address", dep="07:31"),
             stop("Stuttgart Hauptbahnhof (tief)", arr="07:40")),
    ride(1, "S-Bahn", "S2", "Filderstadt", stop("Stuttgart Hauptbahnhof (tief)", "101", dep="07:40"),
         stop("Universität", "1", arr="07:50"), status=()),
    footpath(stop("Universität", arr="07:50"), stop("Vaihingen, Pfaffenwaldring 53", kind="address", arr="07:55")),
]}


def vvs(*journeys, response=None):
    http = FakeHttp({"/XML_TRIP_REQUEST2": response if response is not None else {"journeys": list(journeys)}})
    return Vvs(http, "https://efa.example/vvs/"), http


class VvsTest(unittest.TestCase):
    def test_area(self):
        self.assertTrue(covers(HBF) and covers(UNI))
        self.assertFalse(covers(HEIDELBERG))
        self.assertFalse(Vvs(FakeHttp()).covers(HBF, HEIDELBERG))

    def test_request(self):
        client, http = vvs(S2)
        client.latest_journey(HBF, UNI, ARRIVE_BY, max_transfers=3, min_transfer_minutes=9, max_walk_minutes=20)
        method, url, params, headers = http.calls[0]
        self.assertEqual(url, "https://efa.example/vvs/XML_TRIP_REQUEST2")
        self.assertEqual(params["outputFormat"], "rapidJSON")
        self.assertEqual(params["name_origin"], "9.18143:48.78433:WGS84[dd.ddddd]")   # Länge zuerst
        self.assertEqual((params["itdDate"], params["itdTime"], params["itdTripDateTimeDepArr"]),
                         ("20261113", "0800", "arr"))
        self.assertEqual((params["maxChanges"], params["changeSpeed"], params["trITMOTvalue100"]), (3, "slow", 20))
        self.assertEqual(params["useRealtime"], 1)
        self.assertIn("PersonalDigitalAgent", headers["User-Agent"])

    def test_bus_and_train_with_realtime_platforms_and_fare(self):
        client, _ = vvs(BUS_AND_S1)
        journey = client.earliest_journey(HBF, UNI, datetime.datetime(2026, 11, 13, 7, 15, tzinfo=TIMEZONE))
        walk, bus, train, last = journey.legs
        self.assertEqual((walk.origin, last.destination), ("Start", "Ziel"))
        self.assertTrue(walk.walking)
        self.assertEqual((bus.mode, bus.line, bus.platform, bus.headsign), ("BUS", "Bus 42", "C",
                                                                            "Erwin-Schoettle-Platz"))
        self.assertEqual((bus.departure_delay, bus.realtime), (2, True))
        self.assertEqual((train.mode, train.line, train.platform, train.arrival_platform),
                         ("SUBURBAN", "S1", "101", "1"))
        self.assertEqual(train.messages,                                     # ohne den Hinweis zu Schorndorf
                         ("Aufzug an der Universität außer Betrieb", "S-Bahn-Streik"))
        self.assertEqual(train.geometry[1], (9.15, 48.76))                     # EFA: [Breite, Länge]
        self.assertEqual(train.departure, datetime.datetime(2026, 11, 13, 7, 35, tzinfo=TIMEZONE))
        self.assertEqual((journey.fare_eur, journey.fare_name), (3.45, "EinzelTicket Erwachsene"))
        self.assertIn("VVS", journey.attribution)
        self.assertEqual(journey.transfers, 1)

    def test_latest_in_time(self):
        client, _ = vvs(BUS_AND_S1, S2)
        journey = client.latest_journey(HBF, UNI, ARRIVE_BY)
        self.assertEqual([leg.line for leg in journey.rides], ["S2"])   # später los, ohne Umstieg
        self.assertFalse(journey.realtime)
        early = client.latest_journey(HBF, UNI, datetime.datetime(2026, 11, 13, 7, 52, tzinfo=TIMEZONE))
        self.assertEqual([leg.line for leg in early.rides], ["Bus 42", "S1"])

    def test_transfer_shorter_than_setting_is_dropped(self):
        client, _ = vvs(BUS_AND_S1)
        self.assertIsNone(client.latest_journey(HBF, UNI, ARRIVE_BY, min_transfer_minutes=8))   # 7 Min. am Hbf
        self.assertIsNotNone(client.latest_journey(HBF, UNI, ARRIVE_BY, min_transfer_minutes=7))

    def test_transfer_rounded_to_whole_minutes(self):
        legs = BUS_AND_S1["legs"]
        bus_arrival = dict(legs[1]["destination"], arrivalTimeEstimated="2026-11-13T06:28:06Z")   # 07:28:06
        journey = dict(BUS_AND_S1, legs=[legs[0], dict(legs[1], destination=bus_arrival), *legs[2:]])
        client, _ = vvs(journey)
        self.assertIsNotNone(client.latest_journey(HBF, UNI, ARRIVE_BY, min_transfer_minutes=7))   # 6,9 Min. ≈ 7

    def test_cancelled_trip_and_missing_fare(self):
        cancelled = dict(S2, legs=[S2["legs"][0], dict(S2["legs"][1], realtimeStatus=["TRIP_CANCELLED"]),
                                   S2["legs"][2]])
        client, _ = vvs(cancelled)
        self.assertIsNone(client.latest_journey(HBF, UNI, ARRIVE_BY))
        client, _ = vvs(dict(S2, fare={}))
        journey = client.latest_journey(HBF, UNI, ARRIVE_BY)
        self.assertEqual((journey.fare_eur, journey.fare_name), (None, ""))

    def test_footpath_without_times(self):
        walk = footpath(stop("Universität"), stop("Vaihingen, Pfaffenwaldring 53", kind="address"), minutes=4)
        client, _ = vvs(dict(S2, legs=[*S2["legs"][:2], walk]))
        journey = client.latest_journey(HBF, UNI, ARRIVE_BY)
        self.assertEqual(journey.arrival, datetime.datetime(2026, 11, 13, 7, 54, tzinfo=TIMEZONE))

    def test_invalid_response_and_no_journeys(self):
        client, _ = vvs(response=["kaputt"])
        with self.assertRaisesRegex(IntegrationError, "VVS"):
            client.latest_journey(HBF, UNI, ARRIVE_BY)
        client, _ = vvs(response={"systemMessages": []})
        self.assertIsNone(client.latest_journey(HBF, UNI, ARRIVE_BY))


if __name__ == "__main__":
    unittest.main()
