import unittest

from backend.integrations.geo import Place
from backend.integrations.http import IntegrationError
from backend.integrations.tankerkoenig import Tankerkoenig
from tests.integrations.fake_http import FakeHttp

HERE = Place("Mannheim", 49.4875, 8.466)


class TankerkoenigTest(unittest.TestCase):
    def test_average_of_open_stations(self):
        http = FakeHttp({"list.php": {"ok": True, "stations": [
            {"isOpen": True, "e5": 1.70, "diesel": 1.60},
            {"isOpen": True, "e5": 1.80, "diesel": None},
            {"isOpen": False, "e5": 1.00},             # geschlossen zählt nicht
            {"isOpen": True, "e5": False},             # meldet keinen Preis
        ]}})
        self.assertEqual(Tankerkoenig(http, "key").price(HERE, "e5"), 1.75)
        self.assertEqual(http.calls[0][2]["apikey"], "key")

    def test_no_prices(self):
        http = FakeHttp({"list.php": {"ok": True, "stations": []}})
        self.assertIsNone(Tankerkoenig(http, "key").price(HERE, "diesel"))

    def test_error_from_api(self):
        http = FakeHttp({"list.php": {"ok": False, "message": "apikey nicht angegeben"}})
        with self.assertRaisesRegex(IntegrationError, "apikey"):
            Tankerkoenig(http, "").price(HERE, "e10")

    def test_unknown_fuel(self):
        with self.assertRaises(ValueError):
            Tankerkoenig(FakeHttp(), "key").price(HERE, "kerosin")


if __name__ == "__main__":
    unittest.main()
