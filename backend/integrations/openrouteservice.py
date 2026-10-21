"""openrouteservice (ORS): Adressen suchen und Routen für Auto, Fahrrad und zu Fuß.

Kostenloser Key: https://openrouteservice.org/dev/#/signup → PDA_ORS_KEY.
Freikontingent u. a. 2.000 Routen und 1.000 Adresssuchen pro Tag. Ohne Echtzeit-Verkehr.
Kartendaten: © OpenStreetMap contributors. Koordinaten erwartet ORS als [Länge, Breite].
"""
from __future__ import annotations

from dataclasses import dataclass, field

from backend.integrations.geo import Place
from backend.integrations.http import Http, IntegrationError

BASE_URL = "https://api.openrouteservice.org"
ATTRIBUTION = "© openrouteservice.org, Kartendaten © OpenStreetMap contributors"

# Verkehrsmittel → ORS-Profil
CAR, BIKE, FOOT = "driving-car", "cycling-regular", "foot-walking"


@dataclass(frozen=True)
class Step:
    instruction: str      # z. B. "Biegen Sie links ab auf Hauptstraße"
    distance_m: float
    duration_s: float


@dataclass(frozen=True)
class Route:
    distance_m: float
    duration_s: float
    steps: tuple[Step, ...] = ()
    geometry: tuple[tuple[float, float], ...] = field(default=(), repr=False)   # (lon, lat)


class OpenRouteService:
    def __init__(self, http: Http, api_key: str):
        self.http = http
        self.api_key = api_key

    def geocode(self, text: str) -> Place:
        """Beste Übereinstimmung für eine Adresse oder einen Ortsnamen."""
        data = self.http.get_json(f"{BASE_URL}/geocode/search",
                                  {"api_key": self.api_key, "text": text, "size": 1, "lang": "de"})
        features = data.get("features") or []
        if not features:
            raise IntegrationError(f"Adresse nicht gefunden: {text!r}")
        return _place(features[0])

    def locality(self, place: Place) -> str:
        """Ortsname zu Koordinaten (z. B. "Mannheim"), für die Bahnhofssuche."""
        data = self.http.get_json(f"{BASE_URL}/geocode/reverse",
                                  {"api_key": self.api_key, "point.lat": place.lat, "point.lon": place.lon,
                                   "size": 1, "layers": "locality", "lang": "de"})
        features = data.get("features") or []
        if not features:
            raise IntegrationError(f"Kein Ort zu {place.label!r} gefunden")
        properties = features[0].get("properties", {})
        return properties.get("locality") or properties.get("name") or place.label

    def route(self, profile: str, start: Place, end: Place) -> Route:
        data = self.http.post_json(
            f"{BASE_URL}/v2/directions/{profile}/geojson",
            {"coordinates": [[start.lon, start.lat], [end.lon, end.lat]], "language": "de", "instructions": True},
            {"Authorization": self.api_key})
        features = data.get("features") or []
        if not features:
            raise IntegrationError(f"Keine Route ({profile}) von {start.label!r} nach {end.label!r}")
        properties = features[0].get("properties", {})
        summary = properties.get("summary", {})   # Start = Ziel: ORS lässt die Werte weg
        steps = tuple(Step(step.get("instruction", ""), step.get("distance", 0.0), step.get("duration", 0.0))
                      for segment in properties.get("segments", []) for step in segment.get("steps", []))
        geometry = tuple((lon, lat) for lon, lat, *_ in features[0].get("geometry", {}).get("coordinates", []))
        return Route(summary.get("distance", 0.0), summary.get("duration", 0.0), steps, geometry)


def _place(feature: dict) -> Place:
    lon, lat = feature["geometry"]["coordinates"][:2]
    return Place(feature.get("properties", {}).get("label", ""), lat, lon)
