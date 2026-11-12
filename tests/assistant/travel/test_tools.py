"""Werkzeuge, Ansicht, Erinnerung und der Befehl "reise"."""
import datetime
import threading
import unittest
from dataclasses import replace
from unittest import mock

from backend import config
from backend.assistant.skills import travel
from backend.assistant.skills.travel import view
from backend.assistant.skills.travel.planner import BUS, RAIL, TRANSIT, WALK, Option, Segment, TravelSettings, TripPlan
from backend.assistant.skills.travel.reminder import TravelReminder
from backend.assistant.skills.travel.tools import TravelTools
from backend.assistant.tools import ToolProvider, UnknownToolError
from backend.integrations import transit
from backend.integrations.http import IntegrationError
from backend.rendering import ViewRenderer
from backend.assistant.skills.travel import planner
from tests.assistant.travel.fakes import (HOME, NOW, RAIN, UNI, FakeCalendar, FakeRail, FakeTransit, event,
                                          make_service, transit_journey)


def render(template_view):
    return ViewRenderer(config.TEMPLATE_DIR, config.FRONTEND_DIR).render(template_view)


class TravelToolsTest(unittest.TestCase):
    def setUp(self):
        self.service = make_service(calendar=FakeCalendar(event()), rail=FakeRail())
        self.tools = TravelTools(lambda: self.service)

    def test_is_tool_provider(self):
        self.assertIsInstance(self.tools, ToolProvider)
        self.assertEqual([s.name for s in self.tools.list_tools()],
                         ["plan_trip_to_next_appointment", "plan_trip", "plan_trip_home", "set_place_address",
                          "set_home_address"])

    def test_next_appointment(self):
        result = self.tools.call_tool("plan_trip_to_next_appointment", {})
        self.assertFalse(result.is_error)
        self.assertIn("Vorlesung", result.content)
        self.assertIn("Los um", result.content)
        self.assertEqual(result.view.template, "travel")
        self.assertIn("<!DOCTYPE html>", render(result.view))

    def test_no_appointment(self):
        self.service.calendar = FakeCalendar()
        self.assertIn("kein Termin", self.tools.call_tool("plan_trip_to_next_appointment", {}).content)

    def test_plan_trip_with_time(self):
        result = self.tools.call_tool("plan_trip", {"destination": "Universität", "arrive_by": "2026-10-21T14:00"})
        self.assertFalse(result.is_error, result.content)
        self.assertEqual(result.view.data["arrive_by"], "Mi 21.10. 14:00 Uhr")

    def test_plan_trip_defaults(self):
        result = self.tools.call_tool("plan_trip", {"destination": "Universität", "origin": "Zuhause"})
        self.assertFalse(result.is_error, result.content)
        self.assertEqual(result.view.data["arrive_by"], "")                # ohne Zeit: jetzt los …
        self.assertEqual(result.view.data["depart_after"], "Mi 21.10. 08:00 Uhr")   # … (NOW)

    def test_plan_trip_with_departure_time(self):
        result = self.tools.call_tool("plan_trip", {"destination": "Universität", "depart_at": "2026-10-21T14:00"})
        self.assertFalse(result.is_error, result.content)
        self.assertEqual(result.view.data["depart_after"], "Mi 21.10. 14:00 Uhr")
        self.assertEqual(result.view.data["arrive_by"], "")
        self.assertIn("Abfahrt ab Mi 21.10. 14:00 Uhr", render(result.view))

    def test_next_appointment_is_home_trip_after_the_last_one(self):
        self.service.calendar = FakeCalendar(event(title="Seminar", start=NOW - datetime.timedelta(hours=1)))
        result = self.tools.call_tool("plan_trip_to_next_appointment", {})
        self.assertIn("Heimweg von „Seminar (21.10. 08:30)“", result.content)
        self.assertEqual(result.view.data["title"], "Heimweg von: Seminar")

    def test_home_trip_from_last_event(self):
        self.service.calendar = FakeCalendar(event(title="Seminar", start=NOW - datetime.timedelta(hours=1)))
        result = self.tools.call_tool("plan_trip_home", {})
        self.assertFalse(result.is_error, result.content)
        self.assertTrue(result.content.startswith("Heimweg von „Seminar“"))
        self.assertEqual(result.view.data["route"], "Universität, Heidelberg → Zuhause, Mannheim")
        later = self.tools.call_tool("plan_trip_home", {"depart_at": "2026-10-21T17:00"})
        self.assertEqual(later.view.data["depart_after"], "Mi 21.10. 17:00 Uhr")
        self.assertEqual(later.view.data["title"], "Heimweg von: Seminar")

    def test_home_trip_from_given_place(self):
        result = self.tools.call_tool("plan_trip_home", {"origin": "Universität"})
        self.assertFalse(result.is_error, result.content)
        self.assertEqual(result.view.data["title"], "Heimweg")
        self.assertEqual(result.view.data["depart_after"], "Mi 21.10. 08:00 Uhr")   # jetzt

    def test_home_trip_without_event_asks_for_origin(self):
        result = self.tools.call_tool("plan_trip_home", {})   # Termin liegt noch vor uns
        self.assertTrue(result.is_error)
        self.assertIn("origin", result.content)

    def test_invalid_time(self):
        result = self.tools.call_tool("plan_trip", {"destination": "Universität", "arrive_by": "morgen"})
        self.assertTrue(result.is_error)
        self.assertIn("Ungültige Zeit", result.content)

    def test_missing_home_asks_model_to_ask_user(self):
        self.service.preferences.set("travel_home_address", "")
        result = self.tools.call_tool("plan_trip", {"destination": "Universität"})
        self.assertTrue(result.is_error)
        self.assertIn("set_home_address", result.content)

    def test_room_in_the_calendar_asks_for_the_building(self):
        self.service.calendar = FakeCalendar(event(location="LE1-C3.05 Vorlesung"))
        result = self.tools.call_tool("plan_trip_to_next_appointment", {})
        self.assertTrue(result.is_error)
        self.assertIn("'LE1-C3.05 Vorlesung'", result.content)
        self.assertIn("set_place_address", result.content)
        saved = self.tools.call_tool("set_place_address", {"key": "LE1", "address": "Universität"})
        self.assertEqual(saved.content, "Ortskürzel gespeichert: LE1 = Universität, Heidelberg")
        self.service._trips.clear()
        result = self.tools.call_tool("plan_trip_to_next_appointment", {})
        self.assertFalse(result.is_error, result.content)
        self.assertEqual(result.view.data["route"], "Zuhause, Mannheim → Universität, Heidelberg")

    def test_set_home_address(self):
        result = self.tools.call_tool("set_home_address", {"address": "Universität"})
        self.assertEqual(result.content, "Heimatadresse gespeichert: Universität, Heidelberg")

    def test_service_error(self):
        result = self.tools.call_tool("set_home_address", {"address": "Atlantis"})
        self.assertTrue(result.is_error)

    def test_unknown_tool(self):
        with self.assertRaises(UnknownToolError):
            self.tools.call_tool("fly_me", {})


class ViewTest(unittest.TestCase):
    def plan(self, *options, notes=(), weather=None, arrive_by=NOW + datetime.timedelta(days=400)):
        """Termin nach allen Ankunftszeiten der Tests (die liegen ein Jahr in der Zukunft)."""
        return TripPlan(HOME, UNI, arrive_by, options, TravelSettings(), notes, weather)

    def test_summary_and_view(self):
        later = NOW + datetime.timedelta(days=365)   # nicht "spät dran", egal wann der Test läuft
        best = Option("train", 3900, 4.5, price_estimated=True, detail="RE 10 ab Mannheim Hbf 09:00",
                      steps=("zu Fuß", "RE 10"), depart_at=later, arrive_at=later)
        other = Option("bike", 600, 0.0, geometry=((8.46, 49.48), (8.5, 49.45), (8.67, 49.41)))
        plan = self.plan(best, other, notes=("Hinweis <b>",))

        text = view.summary(plan, "Vorlesung")
        self.assertIn("am besten mit Bahn (RE 10 ab Mannheim Hbf 09:00)", text)
        self.assertIn("1 Std. 5 Min., ≈ 4,50 €", text)
        self.assertIn("Alternativen: Fahrrad 10 Min./kostenlos", text)
        self.assertNotIn("spät", text)

        html = render(view.trip_view(plan, "Vorlesung"))
        self.assertIn("Weg zu: Vorlesung", html)
        self.assertIn("class=\"line straight\"", html)   # Bahn: Luftlinie
        self.assertIn("Hinweis &lt;b&gt;", html)          # Autoescaping

    def test_route_geometry_and_late(self):
        best = Option("car", 1500, 3.0, geometry=((8.46, 49.48), (8.67, 49.41)),
                      depart_at=NOW, arrive_at=NOW)   # NOW liegt in der Vergangenheit
        data = view.trip_view(self.plan(best)).data
        self.assertTrue(data["best"]["late"])
        self.assertFalse(data["options"][0]["map"]["straight"])
        self.assertEqual(data["title"], "Reiseplan")
        for x, y in (data["options"][0]["map"]["start"], data["options"][0]["map"]["end"]):
            self.assertTrue(0 <= x <= view.MAP_WIDTH and 0 <= y <= view.MAP_HEIGHT)
        self.assertIn("spät dran", view.summary(self.plan(best)))

    def test_map_tiles_under_the_route(self):
        class Tiles:
            def __init__(self):
                self.requested = []

            def data_uri(self, zoom, x, y):
                self.requested.append((zoom, x, y))
                return "data:image/png;base64,AAAA"

        tiles = Tiles()
        best = Option("car", 1500, 3.0, geometry=((8.46, 49.48), (8.67, 49.41)))
        data = view.trip_view(self.plan(best), tiles=tiles).data["options"][0]["map"]
        self.assertEqual(len(data["tiles"]), len(tiles.requested))
        self.assertLessEqual(len(tiles.requested), 20)   # 960 × 540 Kachelpixel: höchstens 5 × 4 Kacheln
        self.assertEqual(len({zoom for zoom, _, _ in tiles.requested}), 1)
        left = min(tile["x"] for tile in data["tiles"])
        right = max(tile["x"] + tile["size"] for tile in data["tiles"])
        top = min(tile["y"] for tile in data["tiles"])
        bottom = max(tile["y"] + tile["size"] for tile in data["tiles"])
        self.assertTrue(left <= 0 and top <= 0 and right >= view.MAP_WIDTH and bottom >= view.MAP_HEIGHT)
        self.assertIn("OpenStreetMap", data["attribution"])
        renderer = ViewRenderer(config.TEMPLATE_DIR, config.FRONTEND_DIR)
        html = renderer.render(view.trip_view(self.plan(best), tiles=tiles))
        self.assertIn('<image id="tile-', html)
        self.assertIn('href="data:image/png;base64,AAAA"', html)
        self.assertIn('<use class="tile" href="#tile-', html)
        self.assertIn("Karte © OpenStreetMap-Mitwirkende", html)

    def test_map_without_tiles_when_offline(self):
        class Offline:
            def data_uri(self, zoom, x, y):
                raise IntegrationError("offline")

        best = Option("car", 1500, 3.0, geometry=((8.46, 49.48), (8.67, 49.41)))
        data = view.trip_view(self.plan(best), tiles=Offline()).data["options"][0]["map"]
        self.assertEqual((data["tiles"], data["attribution"]), ([], ""))
        self.assertFalse(data["straight"])

    def test_weather_and_transfer_are_shown(self):
        later = NOW + datetime.timedelta(days=365)
        bike = Option("bike", 600, 0.0, weather_factor=2.0, weather_note="Regen: Zeit zählt ×2,0",
                      depart_at=later, arrive_at=later)
        plan = self.plan(Option("car", 900, 3.0, depart_at=later, arrive_at=later), bike, weather=RAIN)
        text = view.summary(plan)
        self.assertIn("Wetter: Regen, 8 °C, Wind 20 km/h, 90 % Regenwahrscheinlichkeit", text)
        html = render(view.trip_view(plan))
        self.assertIn("Fahrrad (Regen: Zeit zählt ×2,0)", html)
        self.assertIn("Wetter: Regen", html)
        self.assertIn("Open-Meteo", html)
        self.assertNotIn("Wetter", view.summary(self.plan(Option("car", 900, 3.0, depart_at=later, arrive_at=later),
                                                          weather=RAIN)))   # hat nichts geändert

    def test_every_option_has_its_own_panel_and_map(self):
        later = NOW + datetime.timedelta(days=365)
        road = ((8.46, 49.48), (8.55, 49.45), (8.67, 49.41))
        car = Option("car", 1500, 3.0, geometry=road, steps=("Losfahren",), depart_at=later, arrive_at=later)
        taxi = Option("taxi", 1800, 30.0, geometry=road, depart_at=later, arrive_at=later)
        bike = Option("bike", 4200, 0.0, geometry=((8.46, 49.48), (8.67, 49.41)), steps=("Radweg",),
                      depart_at=later, arrive_at=later)
        data = view.trip_view(self.plan(car, taxi, bike)).data
        options = data["options"]
        self.assertEqual([o["label"] for o in options], ["Auto", "Taxi", "Fahrrad"])
        self.assertEqual([o["recommended"] for o in options], [True, False, False])
        self.assertIs(options[0]["map"], options[1]["map"])       # gleiche Route: eine Karte
        self.assertIsNot(options[0]["map"], options[2]["map"])
        self.assertEqual(options[2]["steps"], ["Radweg"])
        html = render(view.trip_view(self.plan(car, taxi, bike)))
        self.assertEqual(html.count('class="pick"'), 3)
        self.assertIn('id="mode-0" aria-label="Auto" checked', html)
        self.assertIn('#mode-2:checked ~ .panels #panel-2 { display: block; }', html)
        self.assertIn('<label for="mode-1">', html)                       # Reiter
        self.assertIn('<label class="pick-row" for="mode-2">Fahrrad</label>', html)   # Tabellenzeile
        self.assertEqual(html.count('<svg class="map"'), 3)

    def test_tiles_are_embedded_once_for_all_maps(self):
        class Tiles:
            def __init__(self):
                self.requested = []

            def data_uri(self, zoom, x, y):
                self.requested.append((zoom, x, y))
                return "data:image/png;base64,AAAA"

        tiles = Tiles()
        road = ((8.46, 49.48), (8.67, 49.41))
        plan = self.plan(Option("car", 1500, 3.0, geometry=road), Option("bike", 4200, 0.0, geometry=road[::-1]))
        data = view.trip_view(plan, tiles=tiles).data
        self.assertEqual(len(tiles.requested), len(set(tiles.requested)))
        self.assertEqual(len(data["tiles"]), len(tiles.requested))
        used = {tile["id"] for option in data["options"] for tile in option["map"]["tiles"]}
        self.assertEqual(used, {tile["id"] for tile in data["tiles"]})
        html = ViewRenderer(config.TEMPLATE_DIR, config.FRONTEND_DIR).render(view.trip_view(plan, tiles=tiles))
        self.assertEqual(html.count("data:image/png"), len(data["tiles"]))

    def test_train_map_with_walks_trains_and_transfers(self):
        later = NOW + datetime.timedelta(days=365)
        segments = (
            Segment(WALK, ((8.46, 49.48), (8.469, 49.479)), "10 Min. zu Fuß zu Mannheim Hbf", "Mannheim Hbf"),
            Segment(RAIL, ((8.469, 49.479), (9.182, 48.784)), "ICE 1: Mannheim Hbf → Stuttgart Hbf", "Stuttgart Hbf"),
            Segment(RAIL, ((9.182, 48.784), (9.983, 48.399)), "IC 2: Stuttgart Hbf → Ulm Hbf", "Ulm Hbf"),
            Segment(TRANSIT, ((9.983, 48.399), (9.99, 48.40)), "≈ 12 Min. Bus/Tram zum Ziel"),
        )
        train = Option("train", 9000, 60.0, segments=segments, depart_at=later, arrive_at=later,
                       geometry=tuple(p for segment in segments for p in segment.points))
        data = view.trip_view(self.plan(train)).data["options"][0]["map"]
        self.assertEqual([line["kind"] for line in data["lines"]], [WALK, RAIL, RAIL, TRANSIT])
        first, second = data["lines"][1]["color"], data["lines"][2]["color"]
        self.assertNotEqual(first, second)                                   # jeder Zug eine Farbe
        self.assertEqual([(stop["name"], stop["transfer"]) for stop in data["stops"]],
                         [("Mannheim Hbf", False), ("Stuttgart Hbf", True), ("Ulm Hbf", False)])
        self.assertEqual(len(data["legend"]), 4)
        self.assertFalse(data["straight"])
        html = render(view.trip_view(self.plan(train)))
        self.assertIn('class="line rail"', html)
        self.assertIn('class="line walk"', html)
        self.assertIn("<title>Umstieg: Stuttgart Hbf</title>", html)
        self.assertIn("IC 2: Stuttgart Hbf → Ulm Hbf", html)

    def test_bus_legs_and_transfer_over_a_footpath(self):
        segments = (
            Segment(WALK, ((8.46, 49.48), (8.462, 49.481)), "5 Min. zu Fuß zu Paradeplatz", "Paradeplatz"),
            Segment(BUS, ((8.462, 49.481), (8.469, 49.479)), "Bus 33: Paradeplatz → Hbf", "Hbf"),
            Segment(WALK, ((8.469, 49.479), (8.4695, 49.4788)), "2 Min. zu Fuß zu Hbf Gleis 9", "Hbf Gleis 9"),
            Segment(RAIL, ((8.4695, 49.4788), (8.675, 49.404)), "S3: Hbf Gleis 9 → Heidelberg", "Heidelberg"),
            Segment(WALK, ((8.675, 49.404), (8.67, 49.41)), "4 Min. zu Fuß zum Ziel"),
        )
        option = Option("train", 2400, 3.0, segments=segments, title="ÖPNV",
                        geometry=tuple(p for segment in segments for p in segment.points))
        data = view.trip_view(self.plan(option)).data
        self.assertEqual(data["options"][0]["label"], "ÖPNV")
        lines = data["options"][0]["map"]["lines"]
        self.assertNotEqual(lines[1]["color"], lines[3]["color"])            # Bus und S-Bahn verschieden
        self.assertEqual([(s["name"], s["transfer"]) for s in data["options"][0]["map"]["stops"]],
                         [("Paradeplatz", False), ("Hbf", True), ("Hbf Gleis 9", True), ("Heidelberg", False)])
        self.assertIn('class="line bus"', render(view.trip_view(self.plan(option))))
        transit = Option("train", 2400, 3.0, attribution="Transitous")
        self.assertIn("· Transitous", view.trip_view(self.plan(transit, transit)).data["attribution"])
        self.assertEqual(view.trip_view(self.plan(transit, transit)).data["attribution"].count("Transitous"), 1)

    def test_bus_and_train_like_the_app(self):
        later = NOW + datetime.timedelta(days=365)
        walk, bus, train, last = transit_journey(later).legs
        train = replace(train, realtime=True, stops=(("Friedrichsfeld", later), ("Wieblingen", None)),
                        color="#fddd04", text_color="#231f20")
        option = planner.transit_option(transit.Journey((walk, bus, train, last)), TravelSettings())
        journey = view.trip_view(self.plan(option)).data["options"][0]["journey"]
        self.assertEqual((journey["transfers"], journey["realtime"]), ("1 Umstieg", True))
        self.assertEqual([part["kind"] for part in journey["bar"]], [WALK, BUS, RAIL, WALK])
        self.assertEqual(journey["bar"][1]["background"], view.MODE_COLORS["BUS"][0])   # nach Verkehrsmittel
        self.assertEqual(journey["bar"][2]["background"], "#fddd04")                    # Farbe der Linie
        halts = journey["items"][::2]
        self.assertEqual([halt["kind"] for halt in halts], ["start", "stop", "transfer", "stop", "end"])
        self.assertEqual(halts[0]["name"], HOME.label)                     # Start heißt wie die Adresse
        self.assertEqual(halts[-1]["name"], UNI.label)
        self.assertEqual((halts[1]["platform"], halts[2]["platform"]), ("Steig B", "Gl. 9"))
        self.assertEqual(halts[2]["wait"], "Umstieg · 6 Min.")
        # Linienstücke am Punkt: Bus kommt an (lila), S3 fährt weiter (Linienfarbe) - Leiste ohne Lücke
        self.assertEqual((halts[2]["line_in"], halts[2]["line_out"]),
                         ({"kind": "ride", "color": view.MODE_COLORS["BUS"][0]}, {"kind": "ride", "color": "#fddd04"}))
        self.assertEqual((halts[0]["line_in"]["kind"], halts[0]["line_out"]["kind"]), ("", "walk"))
        self.assertEqual((halts[-1]["line_in"]["kind"], halts[-1]["line_out"]["kind"]), ("walk", ""))
        self.assertTrue(halts[2]["depart"]["late"])                        # S3 2 Min. später
        self.assertTrue(halts[2]["depart"]["actual"])
        ride = journey["items"][5]
        self.assertEqual((ride["kind"], ride["line"], ride["headsign"]), ("ride", "S3", "Karlsruhe"))
        self.assertEqual([stop["name"] for stop in ride["stops"]], ["Friedrichsfeld", "Wieblingen"])
        self.assertEqual(ride["messages"], ["Bauarbeiten"])
        self.assertEqual(journey["items"][1]["label"], "5 Min. Fußweg")
        html = render(view.trip_view(self.plan(option)))
        for text in ('class="line-badge"', "Umstieg · 6 Min.", "2 Zwischenhalte", "→ Karlsruhe", "⚠ Bauarbeiten",
                     'class="halt halt-transfer in-ride out-ride"', "--out: #fddd04",
                     'class="conn-bar"'):
            self.assertIn(text, html)
        self.assertNotIn("<h3>Wegbeschreibung</h3>", html)                 # die Zeitleiste ersetzt sie
        self.assertIn('<details class="compare">', html)                   # Vergleich zugeklappt
        self.assertLess(html.index('class="map-box"'), html.index('class="conn"'))   # Karte ganz oben
        self.assertIn('id="zoom-0"', html)                                 # Klick: Karte groß

    def test_no_deutschlandticket_is_marked_red(self):
        later = NOW + datetime.timedelta(days=365)
        walk, bus, train, last = transit_journey(later).legs
        ice = replace(train, mode="LONG_DISTANCE", line="ICE 911")
        option = planner.transit_option(transit.Journey((walk, bus, ice, last)), TravelSettings(deutschlandticket=True))
        journey = view.trip_view(self.plan(option)).data["options"][0]["journey"]
        self.assertEqual(journey["no_ticket"], ["ICE 911"])
        self.assertEqual([part["no_ticket"] for part in journey["bar"]], [False, False, True, False])
        halts, links = journey["items"][::2], journey["items"][1::2]
        self.assertEqual([link["no_ticket"] for link in links], [False, False, True, False])
        self.assertEqual([(h["no_ticket_in"], h["no_ticket_out"]) for h in halts],   # Bereich: Einstieg bis Ausstieg
                         [(False, False), (False, False), (False, True), (True, False), (False, False)])
        html = render(view.trip_view(self.plan(option)))
        self.assertIn("kein D-Ticket", html)
        self.assertIn("ICE 911: nicht im Deutschlandticket", html)
        self.assertIn("no-ticket no-ticket-start", html)
        self.assertIn("no-ticket no-ticket-end", html)
        regional = planner.transit_option(transit_journey(later), TravelSettings())
        self.assertNotIn("kein D-Ticket", render(view.trip_view(self.plan(regional))))

    def test_transfer_on_foot_and_estimated_bus(self):
        later = NOW + datetime.timedelta(days=365)
        walk, bus, train, last = transit_journey(later).legs
        footpath = replace(walk, origin=bus.destination, destination="Hbf Gleis 9", departure=bus.arrival,
                           arrival=bus.arrival + datetime.timedelta(minutes=3))
        option = planner.transit_option(transit.Journey((walk, bus, footpath, train, last)), TravelSettings())
        items = view.trip_view(self.plan(option)).data["options"][0]["journey"]["items"]
        self.assertEqual([item["kind"] for item in items[::2]],
                         ["start", "stop", "transfer", "transfer", "stop", "end"])
        self.assertEqual(items[5]["label"], "Umstieg · 3 Min. Fußweg")
        estimated = Option("train", 3000, 4.0, stages=(
            planner.Stage(TRANSIT, "Start", "A Hbf", later, later + datetime.timedelta(minutes=20), "Bus/Tram"),
            planner.Stage(RAIL, "A Hbf", "B Hbf", later + datetime.timedelta(minutes=25),
                          later + datetime.timedelta(minutes=45), "RE 1", "REGIONAL_RAIL"),
            planner.Stage(WALK, "B Hbf", "Ziel", later + datetime.timedelta(minutes=45),
                          later + datetime.timedelta(minutes=50))))
        items = view.trip_view(self.plan(estimated)).data["options"][0]["journey"]["items"]
        self.assertEqual(items[1]["kind"], "transit")
        self.assertIn("geschätzt", items[1]["label"])

    def test_too_late_is_shown(self):
        later = NOW + datetime.timedelta(days=365)
        option = planner.transit_option(transit_journey(later), TravelSettings())   # an um +41 Min.
        plan = self.plan(option, arrive_by=later + datetime.timedelta(minutes=30))
        self.assertEqual(view.trip_view(plan).data["options"][0]["minutes_late"], 11)
        self.assertIn("du kommst 11 Min. zu spät", view.summary(plan))
        self.assertIn("kommt 11 Min. zu spät", render(view.trip_view(plan)))
        car = Option("car", 900, 3.0, depart_at=later, arrive_at=later + datetime.timedelta(minutes=50))
        self.assertIn("(20 Min. zu spät)", render(view.trip_view(self.plan(car, arrive_by=option.arrive_at
                                                                          - datetime.timedelta(minutes=11)))))

    def test_free_option_first_is_explained(self):
        bike = Option("bike", 3600, 0.0)
        car = Option("car", 1200, 4.0)
        plan = TripPlan(HOME, UNI, NOW, planner.rank([car, bike], TravelSettings()), TravelSettings())
        self.assertEqual(plan.recommended.mode, "bike")
        data = view.trip_view(plan).data
        self.assertIn("nach Kosten (Preis und Zeit) wäre Auto besser", data["free_note"])
        self.assertTrue(data["options"][0]["free"] and data["options"][0]["preferred"])
        self.assertIn("Fahrrad ist kostenlos und deshalb vorn", view.summary(plan))
        self.assertIn('<span class="free">kostenlos</span>', render(view.trip_view(
            TripPlan(HOME, UNI, NOW, (car, bike), TravelSettings()))))          # Reiter zeigt kostenlos
        settings = TravelSettings(prefer_free=False)
        cost_first = TripPlan(HOME, UNI, NOW, planner.rank([car, bike], settings), settings)
        self.assertEqual(view.trip_view(cost_first).data["free_note"], "")

    def test_home_texts(self):
        later = NOW + datetime.timedelta(days=365)
        plan = self.plan(Option("car", 900, 3.0, depart_at=later, arrive_at=later))
        self.assertTrue(view.summary(plan, "Seminar", home=True).startswith("Heimweg von „Seminar“: am besten"))
        self.assertTrue(view.summary(plan, home=True).startswith("Heimweg: am besten"))
        self.assertEqual(view.trip_view(plan, home=True).data["title"], "Heimweg")
        self.assertIn("Heimweg", view.summary(self.plan(), home=True))

    def test_no_options(self):
        plan = self.plan(notes=("Auto/Taxi: kaputt",))
        self.assertIn("keinen Weg", view.summary(plan))
        self.assertIn("Auto/Taxi: kaputt", render(view.trip_view(plan)))

    def test_formatting(self):
        self.assertEqual(view.duration(30), "1 Min.")
        self.assertEqual(view.duration(7260), "2 Std. 1 Min.")
        self.assertEqual(view.euro(3.456), "3,46 €")


class ReminderTest(unittest.TestCase):
    def setUp(self):
        self.service = make_service(calendar=FakeCalendar(event(start=NOW + datetime.timedelta(minutes=60))))
        self.pushed, self.settings = [], []
        self.reminder = TravelReminder(self.service, self.notify, interval_s=60)

    def notify(self, reply, settings):
        self.pushed.append(reply)
        self.settings.append(settings)

    def at(self, moment):
        self.service.test_clock["now"] = moment

    def test_reminds_once_shortly_before_departure(self):
        depart = self.service.next_trip().plan.recommended.depart_at
        self.at(depart - datetime.timedelta(minutes=20))
        self.assertFalse(self.reminder.check())
        self.at(depart - datetime.timedelta(minutes=10))
        self.assertTrue(self.reminder.check())
        self.assertFalse(self.reminder.check())   # nur einmal je Termin
        self.assertIn("In 10 Minuten solltest du los", self.pushed[0].text)
        self.assertEqual(self.pushed[0].view.template, "travel")
        self.assertEqual(self.service.calendar.calls[-1], False)   # nie interaktiv anmelden
        self.assertEqual(self.settings[0].reminder_display, "popup")

    def test_fresh_plan_right_before_reminding(self):
        transit = FakeTransit()
        service = make_service(calendar=FakeCalendar(event(start=NOW + datetime.timedelta(hours=2))),
                               transit=transit, modes=["train"])
        reminder = TravelReminder(service, self.notify, interval_s=60)
        depart = service.next_trip().plan.recommended.depart_at              # Plan von 08:00
        planned = len(transit.calls)
        # Verspätung: kurz vor der Abfahrt fährt die Verbindung 20 Min. später
        transit.journey = lambda departure: transit_journey(departure + datetime.timedelta(minutes=20))
        service.test_clock["now"] = depart - datetime.timedelta(minutes=10)
        self.assertFalse(reminder.check())                                   # neu gerechnet: noch nicht Zeit
        self.assertEqual(len(transit.calls), planned + 1)
        self.assertFalse(reminder.check())                                   # Plan ist frisch: nicht schon wieder
        self.assertEqual(len(transit.calls), planned + 1)
        service.test_clock["now"] = depart + datetime.timedelta(minutes=10)
        self.assertTrue(reminder.check())
        self.assertIn("In 10 Minuten solltest du los", self.pushed[0].text)
        self.assertEqual(service.next_trip().plan.recommended.depart_at, depart + datetime.timedelta(minutes=20))

    def test_old_plan_when_refresh_fails(self):
        depart = self.service.next_trip().plan.recommended.depart_at
        self.at(depart - datetime.timedelta(minutes=10))
        with mock.patch.object(self.service, "plan", side_effect=IntegrationError("offline")):
            self.assertTrue(self.reminder.check())                           # erinnert mit dem alten Plan

    def test_lead_time_and_display_from_settings(self):
        self.service.preferences.set("travel_settings", {"reminder_minutes": 30, "reminder_display": "notice"})
        depart = self.service.next_trip().plan.recommended.depart_at
        self.at(depart - datetime.timedelta(minutes=25))
        self.assertTrue(self.reminder.check())
        self.assertEqual(self.settings[0].reminder_display, "notice")

    def test_switched_off(self):
        self.service.preferences.set("travel_settings", {"reminder": False})
        self.at(self.service.next_trip().plan.recommended.depart_at)
        self.assertFalse(self.reminder.check())

    def test_reminds_before_the_way_home(self):
        last = event("letzter", "Seminar", start=NOW - datetime.timedelta(minutes=30), minutes=60)   # bis 08:30
        self.service.calendar = FakeCalendar(last)
        self.at(last.end - datetime.timedelta(minutes=20))
        self.assertFalse(self.reminder.check())
        self.at(last.end - datetime.timedelta(minutes=15))
        self.assertTrue(self.reminder.check())
        self.assertTrue(self.pushed[0].text.startswith("In 15 Minuten geht es nach Hause (nach „Seminar“)."))
        self.assertEqual(self.pushed[0].view.data["title"], "Heimweg von: Seminar")
        self.assertFalse(self.reminder.check())

    def test_way_home_reminder_ends_after_departure(self):
        last = event("letzter", "Seminar", start=NOW - datetime.timedelta(minutes=30), minutes=60)
        self.service.calendar = FakeCalendar(last)
        self.at(last.end + datetime.timedelta(minutes=29))
        self.assertTrue(TravelReminder(self.service, self.notify, 60).check())
        self.service._trips.clear()
        self.at(last.end + datetime.timedelta(minutes=45))
        self.assertFalse(TravelReminder(self.service, self.notify, 60).check())

    def test_already_late(self):
        depart = self.service.next_trip().plan.recommended.depart_at
        self.at(depart + datetime.timedelta(minutes=2))
        self.assertTrue(self.reminder.check())
        self.assertTrue(self.pushed[0].text.startswith("Jetzt"))

    def test_no_reminder_when_the_next_appointment_is_in_the_same_building(self):
        morning = event("v1", "Vorlesung", start=NOW + datetime.timedelta(hours=1), location="LE1-C3.05 Vorlesung")
        afternoon = event("v2", "Vorlesung", start=NOW + datetime.timedelta(hours=4), location="LE1-C3.09 Praktikum")
        self.service.preferences.set("travel_settings", {"places": "LE1 = Universität"})
        self.service.calendar = FakeCalendar(morning, afternoon)
        self.at(afternoon.start - datetime.timedelta(minutes=20))           # nach der ersten, vor der zweiten
        trip = self.service.next_trip()
        self.assertTrue(trip.plan.same_place)
        self.assertFalse(self.reminder.check())
        self.assertIn("kein Weg nötig", view.summary(trip.plan, "Vorlesung"))

    def test_same_warning_only_once(self):
        self.service.calendar = FakeCalendar(event(location="Raum 7"))
        with self.assertLogs("backend.assistant.skills.travel.reminder", "WARNING") as logs:
            self.assertFalse(self.reminder.check())
            self.assertFalse(self.reminder.check())
        self.assertEqual(len(logs.records), 1)
        self.assertIn("Ort nicht gefunden: 'Raum 7'", logs.output[0])

    def test_errors_are_quiet(self):
        self.service.calendar = None   # nicht eingerichtet
        self.assertFalse(self.reminder.check())
        self.service.calendar = mock.Mock(events=mock.Mock(side_effect=IntegrationError("offline")))
        self.assertFalse(self.reminder.check())
        self.service.calendar = FakeCalendar()   # kein Termin
        self.assertFalse(self.reminder.check())

    def test_thread_survives_errors_and_stops(self):
        checked = threading.Event()

        def failing_check():
            checked.set()
            raise RuntimeError("kaputt")

        self.reminder.check = failing_check
        stop = self.reminder.start()
        self.assertTrue(checked.wait(2))
        stop()


class SkillTest(unittest.TestCase):
    def test_reise_command_without_key_explains_setup(self):
        reply = travel.next_trip_reply()   # Tests laufen ohne PDA_ORS_KEY (tests/conftest.py)
        self.assertIn("PDA_ORS_KEY", reply.text)
        self.assertEqual(reply.view.template, "default")

    def test_reise_command_with_service(self):
        service = make_service(calendar=FakeCalendar(event()))
        with mock.patch.object(travel, "service", lambda: service):
            self.assertEqual(travel.next_trip_reply().view.template, "travel")
            service.calendar = FakeCalendar()
            self.assertIn("kein Termin", travel.next_trip_reply().text)
            service.calendar = FakeCalendar(event())
            service.preferences.set("travel_home_address", "")
            service._trips.clear()
            self.assertIn("travel_home_address", travel.next_trip_reply().text)

    def test_no_reminder_without_key(self):
        self.assertIsNone(travel.SKILL.start())

    def test_reminder_is_shown_like_a_proactive_message(self):
        reply = travel.AssistantReply("Los!", None)
        settings = TravelSettings(reminder_display="notice", reminder_speak=True)
        with mock.patch("backend.api._announce_reply") as announce:
            travel._notify(reply, settings)
        announce.assert_called_once_with(reply, "Zeit loszufahren", "Reise-Assistent", "notice", True)

    def test_reminder_starts_with_key(self):
        with mock.patch.object(config, "ORS_KEY", "key"), \
                mock.patch.object(travel, "service", lambda: make_service()), \
                mock.patch("backend.assistant.skills.travel.reminder.TravelReminder.start", return_value="stop"):
            self.assertEqual(travel.SKILL.start(), "stop")

    def test_real_service_wiring(self):
        service = travel.service()
        self.assertIsNone(service.ors)    # ohne Keys
        self.assertIsNone(service.rail)
        self.assertIsNone(service.fuel)
        self.assertIsNotNone(service.calendar)
        self.assertIsNotNone(service.weather)   # Open-Meteo braucht keinen Key


if __name__ == "__main__":
    unittest.main()
