import datetime
import unittest

from backend.integrations.geo import Place
from backend.integrations.http import IntegrationError
from backend.integrations.weather import OpenMeteo, Weather
from tests.integrations.fake_http import FakeHttp

MANNHEIM = Place("Mannheim", 49.48731, 8.46601)
T0 = 1792562400   # 2026-10-21 06:00 UTC
FORECAST = {"hourly": {
    "time": [T0, T0 + 3600, T0 + 7200],
    "temperature_2m": [6.4, 7.9, None],
    "precipitation": [0.0, 1.2, 0.0],
    "precipitation_probability": [10, 80, None],
    "wind_speed_10m": [12.0, 41.5, 5.0],
    "weather_code": [3, 63, 0],
}}


def at(hours, minutes=0):
    return datetime.datetime.fromtimestamp(T0, datetime.timezone.utc) + datetime.timedelta(hours=hours, minutes=minutes)


class OpenMeteoTest(unittest.TestCase):
    def test_nearest_hour_and_request(self):
        http = FakeHttp({"open-meteo": FORECAST})
        weather = OpenMeteo(http).at(MANNHEIM, at(1, 20))
        self.assertEqual(weather, Weather(at(1), 7.9, 1.2, 80, 41.5, 63))
        params = http.calls[0][2]
        self.assertEqual((params["latitude"], params["longitude"]), (49.487, 8.466))
        self.assertEqual(params["timeformat"], "unixtime")
        self.assertIn("precipitation", params["hourly"])

    def test_missing_values_count_as_zero(self):
        weather = OpenMeteo(FakeHttp({"open-meteo": FORECAST})).at(MANNHEIM, at(2))
        self.assertEqual((weather.temperature_c, weather.precipitation_probability), (0.0, 0))

    def test_no_forecast(self):
        with self.assertRaisesRegex(IntegrationError, "keine Vorhersage"):
            OpenMeteo(FakeHttp({"open-meteo": {}})).at(MANNHEIM, at(0))

    def test_too_far_from_forecast(self):
        with self.assertRaisesRegex(IntegrationError, "für diese Zeit"):
            OpenMeteo(FakeHttp({"open-meteo": FORECAST})).at(MANNHEIM, at(10))


class WeatherTest(unittest.TestCase):
    def test_wet(self):
        self.assertTrue(Weather(at(0), 10, 0.5, 0, 0).wet)
        self.assertTrue(Weather(at(0), 10, 0, 70, 0).wet)
        self.assertTrue(Weather(at(0), 10, 0, 0, 0, 61).wet)
        self.assertFalse(Weather(at(0), 10, 0.1, 30, 0, 3).wet)

    def test_description(self):
        self.assertEqual(Weather(at(0), 7.9, 1.2, 80, 41.5, 63).description,
                         "Regen, 8 °C, Wind 42 km/h, 80 % Regenwahrscheinlichkeit")
        self.assertEqual(Weather(at(0), -2, 0, 0, 5, 0).description, "klar, -2 °C, Wind 5 km/h")
        self.assertEqual(Weather(at(0), 1, 0, 0, 5, 75).description, "Schnee, 1 °C, Wind 5 km/h")


if __name__ == "__main__":
    unittest.main()
