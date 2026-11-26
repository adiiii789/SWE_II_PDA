"""Tankerkönig: aktuelle Spritpreise in der Nähe (Daten der Markttransparenzstelle, CC BY 4.0).

Kostenloser Key: https://creativecommons.tankerkoenig.de → PDA_TANKERKOENIG_KEY.
"""
from __future__ import annotations

from statistics import mean

from backend.integrations.geo import Place
from backend.integrations.http import Http, IntegrationError

LIST_URL = "https://creativecommons.tankerkoenig.de/json/list.php"
FUELS = ("e5", "e10", "diesel")
RADIUS_KM = 5


class Tankerkoenig:
    def __init__(self, http: Http, api_key: str):
        self.http = http
        self.api_key = api_key

    def price(self, place: Place, fuel: str) -> float | None:
        """Durchschnittspreis (€/l) der geöffneten Tankstellen im Umkreis; None, wenn keine meldet."""
        if fuel not in FUELS:
            raise ValueError(f"Unbekannte Sorte {fuel!r} (erlaubt: {', '.join(FUELS)})")
        data = self.http.get_json(LIST_URL, {"lat": place.lat, "lng": place.lon, "rad": RADIUS_KM,
                                             "sort": "dist", "type": "all", "apikey": self.api_key})
        if not data.get("ok"):
            raise IntegrationError(f"Tankerkönig: {data.get('message', 'unbekannter Fehler')}")
        prices = [station[fuel] for station in data.get("stations", [])
                  if station.get("isOpen") and isinstance(station.get(fuel), (int, float)) and station[fuel] > 0]
        return round(mean(prices), 3) if prices else None
