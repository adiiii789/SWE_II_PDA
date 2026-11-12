"""Wetter: stündliche Vorhersage von Open-Meteo (kostenlos, ohne Key, https://open-meteo.com).

Der Reise-Assistent nutzt sie, um Fahrrad und Fußweg bei Regen, Kälte oder Wind
schlechter zu bewerten (planner.apply_weather). Wetterdaten: Open-Meteo.com, CC BY 4.0.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass

from backend.integrations.geo import Place
from backend.integrations.http import Http, IntegrationError

BASE_URL = "https://api.open-meteo.com/v1/forecast"
ATTRIBUTION = "Wetter: Open-Meteo.com"
HOURLY = ("temperature_2m", "precipitation", "precipitation_probability", "wind_speed_10m", "weather_code")
MAX_GAP = datetime.timedelta(hours=2)   # weiter weg von der Vorhersage: lieber gar kein Wetter
FORECAST_DAYS = 3

# WMO-Wettercodes (Open-Meteo, "weather_code")
_DESCRIPTIONS = ((0, "klar"), (3, "bewölkt"), (48, "Nebel"), (57, "Niesel"), (67, "Regen"), (77, "Schnee"),
                 (82, "Regenschauer"), (86, "Schneeschauer"), (99, "Gewitter"))
_WET_CODES = frozenset(range(51, 68)) | frozenset(range(71, 78)) | frozenset(range(80, 87)) | frozenset(range(95, 100))
WET_MM = 0.2                  # ab so viel Niederschlag pro Stunde zählt es als nass
WET_PROBABILITY = 60          # oder ab dieser Regenwahrscheinlichkeit (%)


@dataclass(frozen=True)
class Weather:
    time: datetime.datetime
    temperature_c: float
    precipitation_mm: float
    precipitation_probability: int
    wind_kmh: float
    code: int = 0

    @property
    def wet(self) -> bool:
        return (self.precipitation_mm >= WET_MM or self.precipitation_probability >= WET_PROBABILITY
                or self.code in _WET_CODES)

    @property
    def description(self) -> str:
        """z. B. "Regen, 8 °C, Wind 25 km/h, 70 % Regenwahrscheinlichkeit"."""
        sky = next((text for limit, text in _DESCRIPTIONS if self.code <= limit), "")
        parts = [sky, f"{self.temperature_c:.0f} °C", f"Wind {self.wind_kmh:.0f} km/h"]
        if self.precipitation_probability:
            parts.append(f"{self.precipitation_probability} % Regenwahrscheinlichkeit")
        return ", ".join(part for part in parts if part)


class OpenMeteo:
    def __init__(self, http: Http):
        self.http = http

    def at(self, place: Place, moment: datetime.datetime) -> Weather:
        """Vorhersage für die Stunde, die moment am nächsten liegt."""
        data = self.http.get_json(BASE_URL, {
            "latitude": round(place.lat, 3), "longitude": round(place.lon, 3), "hourly": ",".join(HOURLY),
            "timeformat": "unixtime", "forecast_days": FORECAST_DAYS, "wind_speed_unit": "kmh",
        })
        hourly = data.get("hourly") or {}
        times = hourly.get("time") or []
        if not times:
            raise IntegrationError("Open-Meteo: keine Vorhersage")
        target = moment.timestamp()
        index = min(range(len(times)), key=lambda i: abs(times[i] - target))
        if abs(times[index] - target) > MAX_GAP.total_seconds():
            raise IntegrationError("Open-Meteo: keine Vorhersage für diese Zeit")

        def value(name: str) -> float:
            values = hourly.get(name) or []
            return values[index] if index < len(values) and values[index] is not None else 0

        return Weather(datetime.datetime.fromtimestamp(times[index], datetime.timezone.utc),
                       float(value("temperature_2m")), float(value("precipitation")),
                       int(value("precipitation_probability")), float(value("wind_speed_10m")),
                       int(value("weather_code")))
