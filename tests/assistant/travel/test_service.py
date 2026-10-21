import datetime
import unittest

from backend.assistant.skills.travel.planner import BIKE, CAR, FOOT, TAXI, TRAIN
from backend.assistant.skills.travel.service import HomeAddressMissing, TravelSetupError
from backend.integrations import openrouteservice as ors
from backend.integrations.http import IntegrationError
from backend.integrations.openrouteservice import Route
from tests.assistant.travel.fakes import (NOW, FakeCalendar, FakeFuel, FakeOrs, FakeRail, ROUTES, event,
                                          make_service)

ARRIVE = NOW + datetime.timedelta(hours=2)


class PlanTest(unittest.TestCase):
    def test_compares_all_modes(self):
        plan = make_service(rail=FakeRail(), fuel=FakeFuel()).plan("Zuhause", "Universität", ARRIVE)
        self.assertEqual({o.mode for o in plan.options}, {CAR, TAXI, BIKE, TRAIN})   # > 5 km: nicht zu Fuß
        self.assertEqual(plan.notes, ())
        costs = [o.cost(plan.settings) for o in plan.options]
        self.assertEqual(costs, sorted(costs))
        car = next(o for o in plan.options if o.mode == CAR)
        self.assertFalse(car.price_estimated)   # Spritpreis von Tankerkönig

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

    def test_long_walk_to_station_becomes_transit(self):
        routes = {**ROUTES, ors.FOOT: Route(3000, 2400)}
        plan = make_service(FakeOrs(routes), rail=FakeRail()).plan("Zuhause", "Universität", ARRIVE)
        train = next(o for o in plan.options if o.mode == TRAIN)
        self.assertIn("Bus/Tram", train.steps[0])

    def test_without_rail_api(self):
        plan = make_service().plan("Zuhause", "Universität", ARRIVE)
        self.assertNotIn(TRAIN, {o.mode for o in plan.options})
        self.assertIn("PDA_DB_CLIENT_ID", plan.notes[0])

    def test_no_direct_train(self):
        plan = make_service(rail=FakeRail(connection=None)).plan("Zuhause", "Universität", ARRIVE)
        self.assertIn("keine Direktverbindung", plan.notes[0])

    def test_same_station(self):
        ors_client = FakeOrs()
        ors_client.locality = lambda place: "Mannheim"
        plan = make_service(ors_client, rail=FakeRail()).plan("Zuhause", "Universität", ARRIVE)
        self.assertIn("selben Bahnhof", plan.notes[0])

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
        self.assertIsNone(make_service(calendar=FakeCalendar(past)).next_trip())

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
