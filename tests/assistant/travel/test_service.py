import datetime
import unittest

from backend.assistant.skills.travel import planner
from backend.assistant.skills.travel.planner import BIKE, CAR, FOOT, TAXI, TRAIN
from backend.assistant.skills.travel.service import HomeAddressMissing, PlaceNotFound, TravelSetupError
from backend.integrations import openrouteservice as ors
from backend.integrations.http import IntegrationError
from backend.integrations.openrouteservice import Route
from tests.assistant.travel.fakes import (NOW, RAIN, FakeCalendar, FakeFuel, FakeOrs, FakeRail, FakeStations,
                                          FakeTransit, vvs_journey,
                                          FakeWeather, ROUTES, event, make_service)

ARRIVE = NOW + datetime.timedelta(hours=2)


class PlanTest(unittest.TestCase):
    def test_compares_all_modes(self):
        plan = make_service(rail=FakeRail(), fuel=FakeFuel(), prefer_free=False).plan("Zuhause", "Universität", ARRIVE)
        self.assertEqual({o.mode for o in plan.options}, {CAR, TAXI, BIKE, TRAIN})   # > 5 km: nicht zu Fuß
        self.assertEqual(plan.notes, ())
        costs = [o.cost(plan.settings) for o in plan.options]
        self.assertEqual(costs, sorted(costs))
        free_first = make_service(rail=FakeRail(), fuel=FakeFuel()).plan("Zuhause", "Universität", ARRIVE)
        self.assertEqual(free_first.recommended.mode, BIKE)                  # kostenlos
        car = next(o for o in plan.options if o.mode == CAR)
        self.assertFalse(car.price_estimated)   # Spritpreis von Tankerkönig

    def test_only_chosen_modes(self):
        ors_client = FakeOrs()
        plan = make_service(ors_client, rail=FakeRail(), modes=["train", "foot"]).plan("Zuhause", "Universität", ARRIVE)
        self.assertEqual({o.mode for o in plan.options}, {TRAIN})            # zu Fuß: zu weit
        self.assertNotIn(("route", ors.CAR), ors_client.calls)               # Auto gar nicht erst berechnet
        plan = make_service(rail=FakeRail(), modes=[]).plan("Zuhause", "Universität", ARRIVE)
        self.assertEqual({o.mode for o in plan.options}, {CAR, TAXI, BIKE, TRAIN})   # nichts gewählt: alle

    def test_walk_offered_for_short_distances(self):
        plan = make_service().plan("Zuhause", "Universität", ARRIVE)   # Luftlinie ≈ 17 km
        self.assertNotIn(FOOT, {o.mode for o in plan.options})
        plan = make_service(max_walk_km=50).plan("Zuhause", "Universität", ARRIVE)
        self.assertIn(FOOT, {o.mode for o in plan.options})

    def test_train_must_arrive_before_buffer_and_walk(self):
        rail = FakeRail()
        make_service(rail=rail).plan("Zuhause", "Universität", ARRIVE)
        walk_from_station = ROUTES[ors.FOOT].duration_s
        self.assertEqual(rail.arrive_by, ARRIVE - datetime.timedelta(minutes=5, seconds=walk_from_station))
        self.assertEqual(rail.not_before, NOW + datetime.timedelta(seconds=walk_from_station))   # nicht schon weg

    def test_long_walk_to_station_becomes_transit(self):
        routes = {**ROUTES, ors.FOOT: Route(3000, 2400)}
        plan = make_service(FakeOrs(routes), rail=FakeRail()).plan("Zuhause", "Universität", ARRIVE)
        train = next(o for o in plan.options if o.mode == TRAIN)
        self.assertIn("Bus/Tram", train.steps[0])

    def test_without_rail_api(self):
        plan = make_service().plan("Zuhause", "Universität", ARRIVE)
        self.assertNotIn(TRAIN, {o.mode for o in plan.options})
        self.assertIn("PDA_DB_CLIENT_ID", plan.notes[0])

    def test_no_train(self):
        plan = make_service(rail=FakeRail(connection=None)).plan("Zuhause", "Universität", ARRIVE)
        self.assertIn("keine Verbindung mit höchstens zwei Umstiegen", plan.notes[0])
        plan = make_service(rail=FakeRail(connection=None), train_transfers=1).plan("Zuhause", "Universität", ARRIVE)
        self.assertIn("keine Verbindung mit höchstens einem Umstieg", plan.notes[0])
        plan = make_service(rail=FakeRail(connection=None), train_transfers=0).plan("Zuhause", "Universität", ARRIVE)
        self.assertIn("keine Direktverbindung", plan.notes[0])

    def test_transfer_settings_are_passed_to_rail(self):
        rail = FakeRail()
        make_service(rail=rail, train_transfers=0, transfer_minutes=8).plan("Zuhause", "Universität", ARRIVE)
        self.assertEqual(rail.search, (0, 8))

    def test_depart_after_plans_forward(self):
        rail = FakeRail()
        start = NOW + datetime.timedelta(hours=1)
        plan = make_service(rail=rail).plan("Universität", "Zuhause", depart_after=start)
        self.assertIsNone(plan.arrive_by)
        self.assertEqual(plan.depart_after, start)
        car = next(o for o in plan.options if o.mode == CAR)
        self.assertEqual(car.depart_at, start)
        self.assertEqual(car.arrive_at, start + datetime.timedelta(seconds=car.duration_s))
        walk_to_station = ROUTES[ors.FOOT].duration_s
        self.assertEqual(rail.depart_after, start + datetime.timedelta(seconds=walk_to_station))
        train = next(o for o in plan.options if o.mode == TRAIN)
        self.assertEqual(train.depart_at, start + datetime.timedelta(minutes=5))   # Zug 5 Min. nach Ankunft am Bahnhof

    def test_needs_exactly_one_time(self):
        with self.assertRaises(ValueError):
            make_service().plan("Zuhause", "Universität")
        with self.assertRaises(ValueError):
            make_service().plan("Zuhause", "Universität", ARRIVE, depart_after=ARRIVE)

    def test_same_station(self):
        ors_client = FakeOrs()
        ors_client.locality = lambda place: "Mannheim"
        plan = make_service(ors_client, rail=FakeRail()).plan("Zuhause", "Universität", ARRIVE)
        self.assertIn("selben Bahnhof", plan.notes[0])

    def test_station_from_stada_coordinates(self):
        ors_client, stations = FakeOrs(), FakeStations()
        ors_client.locality = None   # wird nicht gebraucht
        plan = make_service(ors_client, rail=FakeRail(), stations=stations).plan("Zuhause", "Universität", ARRIVE)
        train = next(o for o in plan.options if o.mode == TRAIN)
        self.assertIn("Mannheim Süd", train.detail)                          # der nächste Bahnhof
        self.assertEqual([category for _, category in stations.calls], [None, 2, None, 2])
        self.assertFalse(any(call[0] == "geocode" and "Süd" in call[1] for call in ors_client.calls))   # Koordinaten

    def test_train_line_through_stations_for_the_map(self):
        stations = FakeStations()
        plan = make_service(rail=FakeRail(), stations=stations).plan("Zuhause", "Universität", ARRIVE)
        train = next(o for o in plan.options if o.mode == TRAIN)
        start, origin, destination, end = train.geometry
        self.assertEqual(start, (8.46, 49.48))                              # Zuhause
        self.assertEqual(origin, stations.known["eva-Mannheim Süd"])
        self.assertEqual(destination, stations.known["eva-Heidelberg Süd"])
        self.assertEqual(end, (8.67, 49.41))                                # Universität
        walk, rail, walk_again = train.segments
        self.assertEqual([s.kind for s in train.segments], [planner.WALK, planner.RAIL, planner.WALK])
        self.assertEqual((walk.end, rail.end), ("Mannheim Süd", "Heidelberg Süd"))
        self.assertEqual(rail.label, "RE 10: Mannheim Süd → Heidelberg Süd")
        self.assertEqual(walk_again.points[-1], end)

    def test_walk_to_the_station_follows_the_footpath(self):
        footpath = ((8.46, 49.48), (8.462, 49.481), (8.47, 49.49))
        ors_client = FakeOrs({**ROUTES, ors.FOOT: Route(800, 600, geometry=footpath)})
        plan = make_service(ors_client, rail=FakeRail(), stations=FakeStations()).plan("Zuhause", "Universität", ARRIVE)
        walk = next(o for o in plan.options if o.mode == TRAIN).segments[0]
        self.assertEqual(walk.points, footpath)

    def test_train_without_station_coordinates_stays_straight(self):
        plan = make_service(rail=FakeRail()).plan("Zuhause", "Universität", ARRIVE)
        train = next(o for o in plan.options if o.mode == TRAIN)
        self.assertEqual((train.geometry, train.segments), ((), ()))

    def test_second_try_from_major_stations(self):
        class OnlyFromMainStation(FakeRail):
            def latest_journey(self, origin, destination, arrive_by, **search):
                self.tried = getattr(self, "tried", []) + [(origin.name, destination.name)]
                return super().latest_journey(origin, destination, arrive_by, **search) if "Hbf" in origin.name else None

        rail = OnlyFromMainStation()
        plan = make_service(rail=rail, stations=FakeStations()).plan("Zuhause", "Universität", ARRIVE)
        self.assertEqual(rail.tried, [("Mannheim Süd", "Heidelberg Süd"), ("Mannheim Hbf", "Heidelberg Hbf")])
        self.assertIn("Mannheim Hbf", next(o for o in plan.options if o.mode == TRAIN).detail)
        self.assertEqual(plan.notes, ())

    def test_no_connection_from_either_station(self):
        plan = make_service(rail=FakeRail(connection=None), stations=FakeStations()).plan("Zuhause", "Universität", ARRIVE)
        self.assertIn("Mannheim Süd → Heidelberg Süd oder Mannheim Hbf → Heidelberg Hbf", plan.notes[0])

    def test_station_by_name_when_stada_fails(self):
        ors_client = FakeOrs()
        stations = FakeStations(IntegrationError("StaDa weg"))
        plan = make_service(ors_client, rail=FakeRail(), stations=stations).plan("Zuhause", "Universität", ARRIVE)
        self.assertIn(TRAIN, {o.mode for o in plan.options})
        self.assertIn(("geocode", "Mannheim Hbf"), ors_client.calls)

    def test_failing_service_only_drops_its_mode(self):
        routes = {**ROUTES, ors.CAR: IntegrationError("ORS überlastet")}
        plan = make_service(FakeOrs(routes), fuel=FakeFuel()).plan("Zuhause", "Universität", ARRIVE)
        self.assertEqual([o.mode for o in plan.options], [BIKE])
        self.assertIn("Auto/Taxi: ORS überlastet", plan.notes)

    def test_fuel_price_fallback(self):
        plan = make_service(fuel=FakeFuel(IntegrationError("down"))).plan("Zuhause", "Universität", ARRIVE)
        car = next(o for o in plan.options if o.mode == CAR)
        self.assertTrue(car.price_estimated)
        self.assertAlmostEqual(car.price_eur, 21 * 7 / 100 * 1.80)
        self.assertIn("Spritpreis: down", plan.notes)

    def test_no_fuel_price_nearby(self):
        plan = make_service(fuel=FakeFuel(None)).plan("Zuhause", "Universität", ARRIVE)
        self.assertTrue(next(o for o in plan.options if o.mode == CAR).price_estimated)
        self.assertFalse(any("Spritpreis" in note for note in plan.notes))

    def test_unknown_address(self):
        with self.assertRaisesRegex(IntegrationError, "nicht gefunden"):
            make_service().plan("Zuhause", "Atlantis", ARRIVE)

    def test_without_ors_key(self):
        service = make_service()
        service.ors = None
        with self.assertRaisesRegex(TravelSetupError, "PDA_ORS_KEY"):
            service.plan("Zuhause", "Universität", ARRIVE)


class TransitTest(unittest.TestCase):
    def train(self, plan):
        return next((o for o in plan.options if o.mode == TRAIN), None)

    def test_transitous_first(self):
        transit, rail = FakeTransit(), FakeRail()
        plan = make_service(transit=transit, rail=rail, train_transfers=3, transfer_minutes=7,
                            station_walk_minutes=25).plan("Zuhause", "Universität", ARRIVE)
        option = self.train(plan)
        self.assertEqual(option.label, "ÖPNV")
        self.assertIn("Bus 33", option.detail)
        self.assertIsNone(rail.search)                                       # DB-Tafeln nicht gebraucht
        kind, latest, transfers, minutes, walk, not_before = transit.calls[0]
        self.assertEqual((kind, transfers, minutes, walk, not_before), ("latest", 3, 7, 25, NOW))
        self.assertEqual(latest, ARRIVE - datetime.timedelta(minutes=5))     # Puffer
        self.assertEqual(plan.notes, ())

    def test_next_connection_when_nothing_arrives_in_time(self):
        class TooLate(FakeTransit):
            def latest_journey(self, *args, **kwargs):
                super().latest_journey(*args, **kwargs)
                return None

        transit = TooLate()
        plan = make_service(transit=transit).plan("Zuhause", "Universität", ARRIVE)
        self.assertEqual([call[0] for call in transit.calls], ["latest", "earliest"])
        self.assertEqual(transit.calls[1][1], NOW)                           # ab jetzt
        self.assertIsNotNone(self.train(plan))

    def test_home_trip_searches_forward(self):
        transit = FakeTransit()
        make_service(transit=transit).plan("Universität", "Zuhause", depart_after=NOW)
        self.assertEqual(transit.calls[0][:2], ("earliest", NOW))
        self.assertEqual(transit.calls[0][4], 20)   # Fußweg mindestens 15 Min., hier station_walk_minutes

    def test_falls_back_to_db_when_transitous_fails(self):
        rail = FakeRail()
        plan = make_service(transit=FakeTransit(IntegrationError("api.transitous.org nicht erreichbar")),
                            rail=rail).plan("Zuhause", "Universität", ARRIVE)
        self.assertEqual(self.train(plan).label, "Bahn")
        self.assertIn("RE 10", self.train(plan).detail)
        self.assertIn("ÖPNV (Transitous): api.transitous.org nicht erreichbar", plan.notes)

    def test_falls_back_to_db_without_transitous_connection(self):
        rail = FakeRail()
        plan = make_service(transit=FakeTransit(None), rail=rail).plan("Zuhause", "Universität", ARRIVE)
        self.assertIn("RE 10", self.train(plan).detail)
        self.assertIsNotNone(rail.search)

    def test_no_connection_without_db(self):
        plan = make_service(transit=FakeTransit(None)).plan("Zuhause", "Universität", ARRIVE)
        self.assertIsNone(self.train(plan))
        self.assertIn("ÖPNV: keine Verbindung mit höchstens zwei Umstiegen in den nächsten Stunden gefunden.",
                      plan.notes)
        self.assertFalse(any("PDA_DB_CLIENT_ID" in note for note in plan.notes))   # DB-Keys sind kein Muss


class PlaceAliasTest(unittest.TestCase):
    def test_alias_from_settings_and_unknown_place(self):
        service = make_service(places="LE1 = Universität")
        plan = service.plan("Zuhause", "LE1-C3.05 Vorlesung", ARRIVE)
        self.assertEqual(plan.destination.label, "Universität, Heidelberg")
        with self.assertRaises(PlaceNotFound) as caught:
            service.plan("Zuhause", "Raum 7", ARRIVE)
        self.assertEqual(caught.exception.place, "Raum 7")

    def test_set_alias_keeps_other_settings(self):
        service = make_service()
        service.preferences.set("travel_settings", {"reminder_minutes": 30})
        service.set_place_alias("LE1", "Universität")
        self.assertEqual(service.settings().places, "LE1 = Universität")
        self.assertEqual(service.settings().reminder_minutes, 30)
        with self.assertRaises(IntegrationError):
            service.set_place_alias("X", "Atlantis")                         # Adresse muss sich finden lassen


class VvsTest(unittest.TestCase):
    def train(self, plan):
        return next((o for o in plan.options if o.mode == TRAIN), None)

    def test_vvs_first_in_its_area(self):
        vvs, transit = FakeTransit(vvs_journey), FakeTransit()
        plan = make_service(vvs=vvs, transit=transit).plan("Zuhause", "Universität", ARRIVE)
        self.assertEqual(self.train(plan).price_eur, 3.45)                  # echter VVS-Preis
        self.assertFalse(self.train(plan).price_estimated)
        self.assertEqual((len(vvs.calls), transit.calls), (1, []))

    def test_transitous_outside_the_area(self):
        vvs, transit = FakeTransit(area=False), FakeTransit()
        make_service(vvs=vvs, transit=transit).plan("Zuhause", "Universität", ARRIVE)
        self.assertEqual((vvs.calls, len(transit.calls)), ([], 1))

    def test_transitous_when_vvs_fails_or_finds_nothing(self):
        for answer in (IntegrationError("www3.vvs.de nicht erreichbar"), None):
            with self.subTest(answer=answer):
                transit = FakeTransit()
                plan = make_service(vvs=FakeTransit(answer), transit=transit).plan("Zuhause", "Universität", ARRIVE)
                self.assertIn("Bus 33", self.train(plan).detail)
                self.assertEqual(len(transit.calls), 1)
                self.assertEqual(any("ÖPNV (VVS)" in note for note in plan.notes), answer is not None)


class NextTripTest(unittest.TestCase):
    def test_from_home_to_next_event_with_location(self):
        calendar = FakeCalendar(event("ohne-ort", location=""), event("t1"))
        trip = make_service(calendar=calendar).next_trip()
        self.assertEqual(trip.event.id, "t1")
        self.assertEqual(trip.origin_source, "home")
        self.assertEqual(trip.plan.origin.label, "Zuhause, Mannheim")
        self.assertEqual(calendar.calls, [True])

    def test_starts_at_previous_event_of_the_day(self):
        earlier = event("vorher", "Sport", start=NOW - datetime.timedelta(hours=2), minutes=60, location="Universität")
        target = event("t1", location="Zuhause")
        trip = make_service(calendar=FakeCalendar(earlier, target)).next_trip()
        self.assertEqual(trip.origin_source, "Sport")
        self.assertEqual(trip.plan.origin.label, "Universität, Heidelberg")

    def test_previous_day_does_not_count(self):
        yesterday = event("gestern", start=NOW - datetime.timedelta(days=1), location="Universität")
        target = event("t1", start=NOW + datetime.timedelta(days=1), location="Universität")
        trip = make_service(calendar=FakeCalendar(yesterday, target)).next_trip()
        self.assertEqual(trip.origin_source, "home")

    def test_no_upcoming_event(self):
        past = event("vorbei", start=NOW - datetime.timedelta(hours=1))
        self.assertIsNone(make_service(calendar=FakeCalendar(past), home_trip=False).next_trip())
        yesterday = event("gestern", start=NOW - datetime.timedelta(days=1))
        self.assertIsNone(make_service(calendar=FakeCalendar(yesterday)).next_trip())

    def test_plan_is_computed_once_per_event(self):
        ors_client = FakeOrs()
        service = make_service(ors_client, calendar=FakeCalendar(event()))
        first = service.next_trip(interactive=False)
        calls = len(ors_client.calls)
        self.assertIs(service.next_trip(interactive=False), first)
        self.assertEqual(len(ors_client.calls), calls)

    def test_missing_home_address(self):
        with self.assertRaises(HomeAddressMissing):
            make_service(calendar=FakeCalendar(event()), home=None).next_trip()

    def test_missing_calendar(self):
        with self.assertRaisesRegex(TravelSetupError, "Google Calendar"):
            make_service().next_trip()

    def test_without_ors_key_calendar_is_not_asked(self):
        calendar = FakeCalendar(event())
        service = make_service(calendar=calendar)
        service.ors = None
        with self.assertRaises(TravelSetupError):
            service.next_trip()
        self.assertEqual(calendar.calls, [])


class HomeTripTest(unittest.TestCase):
    def test_home_after_last_event_of_the_day(self):
        last = event("letzter", "Seminar", start=NOW - datetime.timedelta(hours=1), minutes=90)   # bis 08:30
        tomorrow = event("morgen", start=NOW + datetime.timedelta(days=1))
        trip = make_service(calendar=FakeCalendar(last, tomorrow)).next_trip()
        self.assertTrue(trip.home)
        self.assertEqual(trip.title, "Heimweg von „Seminar“")
        self.assertEqual(trip.origin_source, "Seminar")
        self.assertEqual((trip.plan.origin.label, trip.plan.destination.label),
                         ("Universität, Heidelberg", "Zuhause, Mannheim"))
        self.assertEqual(trip.plan.depart_after, last.end)
        self.assertEqual(trip.plan.recommended.depart_at, last.end)

    def test_later_event_today_comes_first(self):
        running = event("jetzt", start=NOW - datetime.timedelta(hours=1))
        later = event("später", "Sport", start=NOW + datetime.timedelta(hours=3), location="Zuhause")
        trip = make_service(calendar=FakeCalendar(running, later)).next_trip()
        self.assertFalse(trip.home)
        self.assertEqual(trip.title, "Weg zu „Sport“")

    def test_after_the_event_departure_is_now_rounded(self):
        last = event("vorbei", start=NOW - datetime.timedelta(hours=2), minutes=60)   # endete 07:00
        trip = make_service(calendar=FakeCalendar(last)).next_trip()
        self.assertEqual(trip.plan.depart_after, NOW)   # 08:00 ist schon rund
        service = make_service(calendar=FakeCalendar(last))
        service.test_clock["now"] = NOW + datetime.timedelta(minutes=7)
        self.assertEqual(service.next_trip().plan.depart_after, NOW + datetime.timedelta(minutes=15))

    def test_only_for_a_few_hours_after_the_last_event(self):
        last = event("früh", start=NOW - datetime.timedelta(hours=5), minutes=60)   # endete vor 4 Std.
        tomorrow = event("morgen", start=NOW + datetime.timedelta(days=1))
        trip = make_service(calendar=FakeCalendar(last, tomorrow)).next_trip()
        self.assertEqual(trip.event.id, "morgen")
        self.assertTrue(make_service(calendar=FakeCalendar(last), home_trip_hours=6).next_trip().home)

    def test_not_when_the_last_event_is_at_home(self):
        last = event("daheim", start=NOW - datetime.timedelta(hours=1), location="zuhause ")
        self.assertIsNone(make_service(calendar=FakeCalendar(last)).next_trip())

    def test_home_plan_is_cached(self):
        ors_client = FakeOrs()
        service = make_service(ors_client, calendar=FakeCalendar(event(start=NOW - datetime.timedelta(hours=1))))
        first = service.next_trip(interactive=False)
        calls = len(ors_client.calls)
        self.assertIs(service.next_trip(interactive=False), first)
        self.assertEqual(len(ors_client.calls), calls)


class WeatherTest(unittest.TestCase):
    def test_rain_makes_bike_worse(self):
        dry = make_service(weather=FakeWeather()).plan("Zuhause", "Universität", ARRIVE)
        wet = make_service(weather=FakeWeather(RAIN)).plan("Zuhause", "Universität", ARRIVE)
        dry_bike = next(o for o in dry.options if o.mode == BIKE)
        wet_bike = next(o for o in wet.options if o.mode == BIKE)
        self.assertEqual(dry_bike.weather_factor, 1.0)
        self.assertEqual(wet_bike.weather_factor, 2.0)
        self.assertIn("Regen", wet_bike.weather_note)
        self.assertGreater(wet_bike.cost(wet.settings), dry_bike.cost(dry.settings))
        self.assertEqual(wet.weather, RAIN)
        car = next(o for o in wet.options if o.mode == CAR)
        self.assertEqual(car.weather_factor, 1.0)

    def test_weather_at_start_shortly_before_arrival(self):
        weather = FakeWeather()
        plan = make_service(weather=weather).plan("Zuhause", "Universität", ARRIVE)
        self.assertEqual(weather.calls, [(plan.origin, ARRIVE - datetime.timedelta(minutes=30))])

    def test_weather_can_be_switched_off(self):
        weather = FakeWeather(RAIN)
        service = make_service(weather=weather)
        service.preferences.set("travel_settings", {"weather": False})   # wie aus dem Popup
        plan = service.plan("Zuhause", "Universität", ARRIVE)
        self.assertIsNone(plan.weather)
        self.assertEqual(weather.calls, [])

    def test_weather_failure_only_adds_a_note(self):
        plan = make_service(weather=FakeWeather(IntegrationError("offline"))).plan("Zuhause", "Universität", ARRIVE)
        self.assertIsNone(plan.weather)
        self.assertIn("Wetter: offline", plan.notes)
        self.assertTrue(plan.options)


class HomeAddressTest(unittest.TestCase):
    def test_set_home_address_checks_and_saves(self):
        service = make_service(home=None)
        self.assertEqual(service.set_home_address("Universität").label, "Universität, Heidelberg")
        self.assertEqual(service.home_address(), "Universität")

    def test_unknown_address_is_not_saved(self):
        service = make_service(home=None)
        with self.assertRaises(IntegrationError):
            service.set_home_address("Atlantis")
        with self.assertRaises(HomeAddressMissing):
            service.home_address()


if __name__ == "__main__":
    unittest.main()
