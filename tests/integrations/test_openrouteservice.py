import unittest

from backend.integrations.geo import Place, distance_km
from backend.integrations.http import IntegrationError
from backend.integrations.openrouteservice import CAR, OpenRouteService, Route
from tests.integrations.fake_http import FakeHttp

MANNHEIM = Place("Mannheim", 49.4875, 8.4660)
HEIDELBERG = Place("Heidelberg", 49.3988, 8.6724)


def feature(lon, lat, label):
    return {"geometry": {"coordinates": [lon, lat]}, "properties": {"label": label, "locality": "Mannheim"}}


ROUTE = {"features": [{
    "properties": {"summary": {"distance": 21000.0, "duration": 1500.0},
                   "segments": [{"steps": [{"instruction": "Losfahren", "distance": 100, "duration": 20},
                                           {"instruction": "Ziel erreicht", "distance": 0, "duration": 0}]}]},
    "geometry": {"coordinates": [[8.466, 49.4875], [8.6, 49.43], [8.6724, 49.3988]]},
}]}


class OpenRouteServiceTest(unittest.TestCase):
    def test_geocode_returns_first_match(self):
        http = FakeHttp({"/geocode/search": {"features": [feature(8.466, 49.4875, "Mannheim, BW")]}})
        place = OpenRouteService(http, "key").geocode("Mannheim")
        self.assertEqual(place, Place("Mannheim, BW", 49.4875, 8.466))
        self.assertEqual(http.calls[0][2]["api_key"], "key")

    def test_geocode_without_match(self):
        http = FakeHttp({"/geocode/search": {"features": []}})
        with self.assertRaisesRegex(IntegrationError, "nicht gefunden"):
            OpenRouteService(http, "key").geocode("Nirgendwo")

    def test_locality(self):
        http = FakeHttp({"/geocode/reverse": {"features": [feature(8.466, 49.4875, "Mannheim, BW")]}})
        self.assertEqual(OpenRouteService(http, "key").locality(MANNHEIM), "Mannheim")
        self.assertEqual(http.calls[0][2]["layers"], "locality")

    def test_locality_falls_back_to_name_and_fails_without_match(self):
        http = FakeHttp({"/geocode/reverse": {"features": [{"properties": {"name": "Dorf"}}]}})
        self.assertEqual(OpenRouteService(http, "key").locality(MANNHEIM), "Dorf")
        with self.assertRaises(IntegrationError):
            OpenRouteService(FakeHttp({"/geocode/reverse": {}}), "key").locality(MANNHEIM)

    def test_route_sends_lon_lat_and_reads_summary(self):
        http = FakeHttp({"/v2/directions/driving-car/geojson": ROUTE})
        route = OpenRouteService(http, "key").route(CAR, MANNHEIM, HEIDELBERG)
        self.assertEqual((route.distance_m, route.duration_s), (21000.0, 1500.0))
        self.assertEqual([s.instruction for s in route.steps], ["Losfahren", "Ziel erreicht"])
        self.assertEqual(route.geometry[0], (8.466, 49.4875))
        method, _, body, headers = http.calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(body["coordinates"], [[8.466, 49.4875], [8.6724, 49.3988]])   # [Länge, Breite]
        self.assertEqual(headers, {"Authorization": "key"})

    def test_route_to_same_point_has_no_summary(self):
        http = FakeHttp({"/directions/": {"features": [{"properties": {}, "geometry": {"coordinates": []}}]}})
        self.assertEqual(OpenRouteService(http, "key").route(CAR, MANNHEIM, MANNHEIM), Route(0.0, 0.0))

    def test_route_without_features(self):
        with self.assertRaisesRegex(IntegrationError, "Keine Route"):
            OpenRouteService(FakeHttp({"/directions/": {"features": []}}), "key").route(CAR, MANNHEIM, HEIDELBERG)


class DistanceTest(unittest.TestCase):
    def test_mannheim_heidelberg(self):
        self.assertAlmostEqual(distance_km(MANNHEIM, HEIDELBERG), 17.8, delta=0.5)

    def test_same_place(self):
        self.assertEqual(distance_km(MANNHEIM, MANNHEIM), 0)


if __name__ == "__main__":
    unittest.main()
