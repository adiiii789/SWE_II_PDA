import datetime
import unittest
from dataclasses import replace

from backend.assistant.skills.travel import planner
from backend.assistant.skills.travel.planner import TravelSettings
from backend.integrations import transit
from backend.integrations.db_timetables import Journey, Station, TrainConnection
from backend.integrations.openrouteservice import Route, Step
from backend.integrations.weather import Weather
from tests.assistant.travel.fakes import transit_journey
from tests.test_interfaces import InMemoryPreferences

ARRIVE = datetime.datetime(2026, 10, 21, 10, 0, tzinfo=datetime.timezone.utc)
CAR_ROUTE = Route(20000, 1200, (Step("Links", 10, 5), Step("", 0, 0)))


class SettingsTest(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(TravelSettings.from_preferences(InMemoryPreferences()), TravelSettings())

    def test_values_from_preferences(self):
        prefs = InMemoryPreferences()
        for key, value in {"value_of_time": 40, "deutschlandticket": 1, "fuel": "diesel",
                           "buffer_minutes": 10.0, "consumption": "viel", "taxi_base": True}.items():
            prefs.set("travel_" + key, value)
        settings = TravelSettings.from_preferences(prefs)
        self.assertEqual(settings.value_of_time, 40.0)
        self.assertIs(settings.deutschlandticket, True)
        self.assertEqual(settings.fuel, "diesel")
        self.assertEqual(settings.buffer_minutes, 10)
        self.assertEqual(settings.consumption, TravelSettings.consumption)   # ungültig → Standard
        self.assertEqual(settings.taxi_base, TravelSettings.taxi_base)


class OptionTest(unittest.TestCase):
    settings = TravelSettings()

    def test_car_price_time_and_departure(self):
        option = planner.car_option(CAR_ROUTE, 2.0, False, self.settings, ARRIVE)
        self.assertAlmostEqual(option.price_eur, 20 * 7 / 100 * 2.0)   # 1,4 l × 2 €
        self.assertAlmostEqual(option.duration_s, 1200 * 1.15)
        self.assertEqual(option.arrive_at, ARRIVE - datetime.timedelta(minutes=5))
        self.assertEqual(option.depart_at, option.arrive_at - datetime.timedelta(seconds=1380))
        self.assertEqual(option.steps, ("Links",))
        self.assertEqual(option.label, "Auto")
        self.assertIn("1,4 l", option.detail)

    def test_taxi_includes_base_price_and_waiting(self):
        option = planner.taxi_option(CAR_ROUTE, self.settings, ARRIVE)
        self.assertAlmostEqual(option.price_eur, 4.50 + 20 * 2.60)
        self.assertAlmostEqual(option.duration_s, 1200 * 1.15 + 300)
        self.assertTrue(option.price_estimated)

    def test_bike_and_walk_are_free(self):
        self.assertEqual(planner.bike_option(CAR_ROUTE, self.settings, ARRIVE).price_eur, 0)
        self.assertEqual(planner.walk_option(CAR_ROUTE, self.settings, ARRIVE).mode, planner.FOOT)

    def test_cost_counts_time(self):
        option = planner.Option(planner.CAR, 1800, 5.0)
        self.assertAlmostEqual(option.cost(TravelSettings(value_of_time=30)), 5.0 + 15.0)

    def test_rank_by_cost(self):
        slow_free = planner.Option(planner.BIKE, 3600, 0.0)        # 25 €
        fast_cheap = planner.Option(planner.CAR, 1200, 4.0)        # 12,33 €
        expensive = planner.Option(planner.TAXI, 1000, 50.0)
        ranked = planner.rank([slow_free, expensive, fast_cheap], TravelSettings(prefer_free=False))
        self.assertEqual([o.mode for o in ranked], [planner.CAR, planner.BIKE, planner.TAXI])

    def test_free_options_first(self):
        bike = planner.Option(planner.BIKE, 3600, 0.0)                      # 25 €, aber kostenlos
        walk = planner.Option(planner.FOOT, 5400, 0.0)
        car = planner.Option(planner.CAR, 1200, 4.0)
        transit = planner.Option(planner.TRAIN, 1800, 0.0, price_estimated=False)   # Deutschlandticket
        ranked = planner.rank([car, walk, bike, transit], TravelSettings())
        self.assertEqual([o.mode for o in ranked], [planner.TRAIN, planner.BIKE, planner.FOOT, planner.CAR])
        self.assertTrue(transit.free)
        self.assertFalse(car.free)

    def test_on_time_before_late(self):
        free_but_late = planner.Option(planner.BIKE, 3600, 0.0, arrive_at=ARRIVE + datetime.timedelta(minutes=10))
        car = planner.Option(planner.CAR, 1200, 4.0, arrive_at=ARRIVE - datetime.timedelta(minutes=5))
        ranked = planner.rank([free_but_late, car], TravelSettings(), ARRIVE)
        self.assertEqual([o.mode for o in ranked], [planner.CAR, planner.BIKE])
        self.assertEqual(planner.minutes_late(free_but_late, ARRIVE), 10)
        self.assertEqual(planner.minutes_late(car, ARRIVE), 0)
        self.assertEqual(planner.minutes_late(free_but_late, None), 0)       # ohne Termin: nie zu spät
        self.assertEqual(planner.rank([free_but_late, car], TravelSettings())[0].mode, planner.BIKE)

    def test_free_but_bad_weather_or_too_slow(self):
        rainy_bike = planner.Option(planner.BIKE, 1500, 0.0, weather_factor=2.0)
        walk = planner.Option(planner.FOOT, 4800, 0.0)                      # 60 Min. länger als das Auto
        car = planner.Option(planner.CAR, 1200, 4.0)
        ranked = planner.rank([rainy_bike, walk, car], TravelSettings(free_max_extra_minutes=30))
        self.assertEqual([o.mode for o in ranked], [planner.CAR, planner.BIKE, planner.FOOT])   # nach Kosten
        ranked = planner.rank([rainy_bike, walk, car], TravelSettings())                       # ohne Grenze
        self.assertEqual(ranked[0].mode, planner.FOOT)


class TrainTest(unittest.TestCase):
    def connection(self, long_distance=False):
        return TrainConnection("ICE 1" if long_distance else "RE 1", long_distance, Station("A Hbf", "1"),
                               Station("B Hbf", "2"), ARRIVE - datetime.timedelta(minutes=60),
                               ARRIVE - datetime.timedelta(minutes=15), "4")

    def test_walk_leg_when_short(self):
        leg = planner.walk_or_transit_leg(Route(500, 600), Route(600, 120), TravelSettings())
        self.assertEqual((leg.duration_s, leg.price_eur, leg.description), (600, 0.0, "10 Min. zu Fuß"))

    def test_transit_leg_when_long_walk(self):
        leg = planner.walk_or_transit_leg(Route(3000, 2400), Route(3000, 300), TravelSettings())
        self.assertEqual(leg.duration_s, 300 * 2 + 300)
        self.assertEqual(leg.price_eur, 3.00)
        self.assertIn("Bus/Tram", leg.description)
        with_ticket = planner.walk_or_transit_leg(Route(3000, 2400), Route(3000, 300),
                                                  TravelSettings(deutschlandticket=True))
        self.assertEqual(with_ticket.price_eur, 0.0)

    def test_regional_train_door_to_door(self):
        access, egress = planner.Leg(600, 0, "10 Min. zu Fuß"), planner.Leg(300, 1.0, "5 Min. zu Fuß")
        option = planner.train_option(self.connection(), access, egress, 50, TravelSettings())
        self.assertEqual(option.depart_at, ARRIVE - datetime.timedelta(minutes=70))
        self.assertEqual(option.arrive_at, ARRIVE - datetime.timedelta(minutes=10))
        self.assertEqual(option.duration_s, 3600)
        self.assertAlmostEqual(option.price_eur, 50 * 0.20 + 1.0)
        self.assertTrue(option.price_estimated)
        self.assertIn("Gleis 4", option.detail)
        self.assertEqual(len(option.steps), 3)

    def test_deutschlandticket_only_for_regional_trains(self):
        legs = (planner.Leg(0), planner.Leg(0))
        ticket = TravelSettings(deutschlandticket=True)
        self.assertEqual(planner.train_option(self.connection(), *legs, 50, ticket).price_eur, 0.0)
        self.assertAlmostEqual(planner.train_option(self.connection(True), *legs, 100, ticket).price_eur, 25.0)

    def test_minimum_fare(self):
        legs = (planner.Leg(0), planner.Leg(0))
        self.assertEqual(planner.train_option(self.connection(), *legs, 1, TravelSettings()).price_eur, 2.50)

    def test_transfer_is_described(self):
        hub = Station("C Hbf", "3")
        first = TrainConnection("ICE 1", True, Station("A Hbf", "1"), hub, ARRIVE - datetime.timedelta(minutes=90),
                                ARRIVE - datetime.timedelta(minutes=50), "4", "7")
        second = TrainConnection("RE 2", False, hub, Station("B Hbf", "2"), ARRIVE - datetime.timedelta(minutes=40),
                                 ARRIVE - datetime.timedelta(minutes=15), "2")
        option = planner.train_option(Journey((first, second)), planner.Leg(0, 0, "zu Fuß"),
                                      planner.Leg(0, 0, "zu Fuß"), 100, TravelSettings(deutschlandticket=True))
        self.assertEqual(option.detail, "ICE 1 ab A Hbf 08:30, Gleis 4, Umstieg in C Hbf")
        self.assertIn("Umstieg in C Hbf: 10 Min., weiter von Gleis 2", option.steps)
        self.assertEqual(len(option.steps), 5)
        self.assertAlmostEqual(option.price_eur, 25.0)   # Fernverkehr dabei: Deutschlandticket reicht nicht
        self.assertEqual([stage.long_distance for stage in option.stages], [False, True, False, False])

    def test_several_transfers_are_described(self):
        a, b, c, d = (Station(f"{name} Hbf", str(i)) for i, name in enumerate("ABCD"))
        minutes = [datetime.timedelta(minutes=m) for m in (150, 120, 110, 80, 70, 15)]
        legs = (TrainConnection("ICE 1", True, a, b, ARRIVE - minutes[0], ARRIVE - minutes[1], "4"),
                TrainConnection("IC 2", True, b, c, ARRIVE - minutes[2], ARRIVE - minutes[3], "7"),
                TrainConnection("RB 3", False, c, d, ARRIVE - minutes[4], ARRIVE - minutes[5], "1"))
        option = planner.train_option(Journey(legs), planner.Leg(0, 0, "zu Fuß"), planner.Leg(0, 0, "zu Fuß"),
                                      200, TravelSettings())
        self.assertEqual(option.detail, "ICE 1 ab A Hbf 07:30, Gleis 4, 2 Umstiege: B Hbf und C Hbf")
        self.assertIn("Umstieg in C Hbf: 10 Min., weiter von Gleis 1", option.steps)
        self.assertEqual(len(option.steps), 7)

    def test_walk_leg_keeps_route_for_the_map(self):
        walk = Route(800, 600, geometry=((8.46, 49.48), (8.47, 49.479)))
        leg = planner.walk_or_transit_leg(walk, None, TravelSettings())
        self.assertEqual((leg.kind, leg.geometry), (planner.WALK, walk.geometry))
        transit = planner.walk_or_transit_leg(Route(5000, 3600, geometry=walk.geometry), Route(5000, 600),
                                              TravelSettings())
        self.assertEqual((transit.kind, transit.geometry), (planner.TRANSIT, ()))

    def test_delay_and_messages_from_realtime(self):
        departure = ARRIVE - datetime.timedelta(minutes=55)                    # Prognose, 5 Min. später
        late = TrainConnection("RE 1", False, Station("A Hbf", "1"), Station("B Hbf", "2"), departure,
                               ARRIVE - datetime.timedelta(minutes=15), "4",
                               scheduled_departure=departure - datetime.timedelta(minutes=5),
                               messages=("Reparatur am Zug", "Bauarbeiten", "Dritter Hinweis"), realtime=True)
        option = planner.train_option(late, planner.Leg(0, 0, "zu Fuß"), planner.Leg(0, 0, "zu Fuß"), 50,
                                      TravelSettings())
        self.assertEqual(option.detail, "RE 1 ab A Hbf 09:05 (+5), Gleis 4")
        self.assertEqual(option.depart_at, departure)
        self.assertIn("RE 1 ab A Hbf 09:05 (+5), Gleis 4, an B Hbf 09:45", option.steps)
        self.assertIn("Hinweis zu RE 1: Reparatur am Zug", option.steps)
        self.assertEqual(len(option.steps), 5)   # höchstens zwei Hinweise je Zug


class TransitTest(unittest.TestCase):
    DEPART = datetime.datetime(2026, 10, 21, 8, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=2)))

    def test_bus_and_train_door_to_door(self):
        option = planner.transit_option(transit_journey(self.DEPART), TravelSettings())
        self.assertEqual((option.mode, option.label), (planner.TRAIN, "ÖPNV"))   # mit Bus: nicht nur Bahn
        self.assertEqual(option.detail, "Bus 33 ab Paradeplatz 08:05, Steig B, Umstieg in Mannheim, Hauptbahnhof")
        self.assertEqual(option.steps, (
            "5 Min. zu Fuß zu Paradeplatz",
            "Bus 33 Richtung Hauptbahnhof ab Paradeplatz 08:05, Steig B, an Mannheim, Hauptbahnhof 08:15",
            "Umstieg in Mannheim, Hauptbahnhof: 6 Min., weiter von Gleis 9",
            "S3 Richtung Karlsruhe ab Mannheim, Hauptbahnhof 08:21 (+2), Gleis 9, an Heidelberg, Hauptbahnhof 08:37",
            "Hinweis zu S3: Bauarbeiten",
            "4 Min. zu Fuß zum Ziel"))
        self.assertEqual((option.depart_at, option.duration_s), (self.DEPART, 41 * 60))
        self.assertEqual([s.kind for s in option.segments], [planner.WALK, planner.BUS, planner.RAIL, planner.WALK])
        self.assertEqual([s.end for s in option.segments],
                         ["Paradeplatz", "Mannheim, Hauptbahnhof", "Heidelberg, Hauptbahnhof", ""])
        self.assertEqual(option.geometry[0], (8.46, 49.48))
        self.assertEqual(option.geometry[-1], (8.67, 49.41))
        self.assertTrue(option.price_estimated)
        self.assertGreater(option.price_eur, 0)

    def test_only_trains_is_called_bahn_and_deutschlandticket(self):
        option = planner.transit_option(transit_journey(self.DEPART, bus=False), TravelSettings(deutschlandticket=True))
        self.assertEqual(option.label, "Bahn")
        self.assertEqual(option.price_eur, 0.0)
        self.assertNotIn("Umstieg", option.detail)

    def test_real_fare_when_known(self):
        legs = transit_journey(self.DEPART).legs
        journey = transit.Journey(legs, 3.45, "EinzelTicket Erwachsene", "VVS")
        option = planner.transit_option(journey, TravelSettings())
        self.assertEqual((option.price_eur, option.price_estimated, option.attribution), (3.45, False, "VVS"))
        self.assertEqual(planner.transit_option(journey, TravelSettings(deutschlandticket=True)).price_eur, 0.0)

    def test_walk_between_two_stops_is_the_transfer(self):
        walk, bus, train, last = transit_journey(self.DEPART).legs
        footpath = transit.Leg("WALK", "", bus.destination, "Mannheim Hbf Gleis 9", bus.arrival,
                                  bus.arrival + datetime.timedelta(minutes=3))
        train = replace(train, origin="Mannheim Hbf Gleis 9")
        option = planner.transit_option(transit.Journey((walk, bus, footpath, train, last)), TravelSettings())
        self.assertIn("Umstieg: 3 Min. zu Fuß zu Mannheim Hbf Gleis 9", option.steps)
        self.assertFalse(any(step.startswith("Umstieg in") for step in option.steps))
        self.assertTrue(option.steps[-1].startswith("4 Min. zu Fuß zum Ziel"))


class PlaceAliasTest(unittest.TestCase):
    def test_room_in_the_calendar_becomes_the_building(self):
        settings = TravelSettings(places="LE1 = Lerchenstraße 1, 70174 Stuttgart\nJ: Jägerstraße 56\nkaputt\n"
                                         "LE1-C3 → Raum mit eigener Adresse")
        self.assertEqual(planner.resolve_place("LE1-C3.05 Vorlesung", settings), "Raum mit eigener Adresse")
        self.assertEqual(planner.resolve_place("le1-C2.01", settings), "Lerchenstraße 1, 70174 Stuttgart")
        self.assertEqual(planner.resolve_place("J 2.13", settings), "Jägerstraße 56")
        self.assertEqual(planner.resolve_place("JLE1 Seminar", settings), "JLE1 Seminar")   # nur ganze Wörter
        self.assertEqual(planner.resolve_place("Königstraße 1", settings), "Königstraße 1")

    def test_regular_expression_for_the_whole_place(self):
        settings = TravelSettings(places="LE.* = Lerchenstraße 1\n.*Hörsaal \\d+ = Audimax\n"
                                         "LE2 = Lerchenstraße 2\n(kaputt = bleibt Text")
        self.assertEqual(planner.resolve_place("LE1-C3.05 Vorlesung", settings), "Lerchenstraße 1")
        self.assertEqual(planner.resolve_place("le2-B1", settings), "Lerchenstraße 2")       # einfaches Kürzel vor
        self.assertEqual(planner.resolve_place("Leonberg Bahnhof", settings), "Leonberg Bahnhof")   # groß/klein zählt
        self.assertEqual(planner.resolve_place("Raum LE1", settings), "Raum LE1")           # ganzer Ort: beginnt mit
        self.assertEqual(planner.resolve_place("Altbau Hörsaal 12", settings), "Audimax")
        self.assertEqual(planner.resolve_place("(kaputt) Raum", settings), "bleibt Text")   # ungültig: als Text
        self.assertEqual([key for key, _ in planner.place_aliases(settings.places)],
                         ["(kaputt", "LE2", "LE.*", ".*Hörsaal \\d+"])

    def test_add_or_replace_alias(self):
        text = planner.with_place_alias("LE1 = alt\nJ = Jägerstraße", "le1", "Lerchenstraße 1")
        self.assertEqual(planner.place_aliases(text), [("le1", "Lerchenstraße 1"), ("J", "Jägerstraße")])


class WeatherTest(unittest.TestCase):
    options = [planner.Option(planner.BIKE, 3600, 0.0), planner.Option(planner.FOOT, 3600, 0.0),
               planner.Option(planner.CAR, 1800, 4.0)]

    def apply(self, weather, **settings):
        return {o.mode: o for o in planner.apply_weather(self.options, weather, TravelSettings(**settings))}

    def test_rain_cold_and_wind(self):
        stormy = self.apply(Weather(ARRIVE, 0.0, 3.0, 90, 50.0, 73))
        self.assertAlmostEqual(stormy[planner.BIKE].weather_factor, 2.0 * 1.3 * 1.3)
        self.assertEqual(stormy[planner.BIKE].weather_note, "Niederschlag, Kälte, Wind: Zeit zählt ×3,4")
        self.assertAlmostEqual(stormy[planner.FOOT].weather_factor, 2.0 * 1.3)   # Wind nur fürs Rad
        self.assertEqual(stormy[planner.CAR].weather_factor, 1.0)
        self.assertAlmostEqual(stormy[planner.BIKE].cost(TravelSettings()), 25 * 3.38)

    def test_nice_weather_changes_nothing(self):
        nice = self.apply(Weather(ARRIVE, 20.0, 0.0, 0, 10.0, 1))
        self.assertTrue(all(o.weather_factor == 1.0 and not o.weather_note for o in nice.values()))

    def test_switched_off_or_unknown(self):
        rain = Weather(ARRIVE, 10.0, 3.0, 90, 10.0, 63)
        self.assertEqual(planner.apply_weather(self.options, rain, TravelSettings(weather=False)), self.options)
        self.assertEqual(planner.apply_weather(self.options, None, TravelSettings()), self.options)

    def test_rain_can_flip_the_recommendation(self):
        bike, car = planner.Option(planner.BIKE, 1200, 0.0), planner.Option(planner.CAR, 900, 4.0)   # 8,33 € : 10,25 €
        settings = TravelSettings()
        self.assertEqual(planner.rank([bike, car], settings)[0].mode, planner.BIKE)
        wet = planner.apply_weather([bike, car], Weather(ARRIVE, 12.0, 2.0, 90, 10.0, 63), settings)
        self.assertEqual(planner.rank(wet, settings)[0].mode, planner.CAR)


if __name__ == "__main__":
    unittest.main()
