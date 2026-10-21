import datetime
import unittest

from backend.assistant.skills.travel import planner
from backend.assistant.skills.travel.planner import TravelSettings
from backend.integrations.db_timetables import Station, TrainConnection
from backend.integrations.openrouteservice import Route, Step
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
        ranked = planner.rank([slow_free, expensive, fast_cheap], self.settings)
        self.assertEqual([o.mode for o in ranked], [planner.CAR, planner.BIKE, planner.TAXI])


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


if __name__ == "__main__":
    unittest.main()
