"""Orte und Entfernungen - gemeinsam für openrouteservice, Tankerkönig und den Reise-Assistenten."""
from __future__ import annotations

import math
from dataclasses import dataclass

EARTH_RADIUS_KM = 6371.0


@dataclass(frozen=True)
class Place:
    label: str        # lesbare Adresse, z. B. "Hauptstraße 1, Mannheim, BW, Deutschland"
    lat: float
    lon: float


def distance_km(a: Place, b: Place) -> float:
    """Luftlinie (Haversine)."""
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    dlat, dlon = lat2 - lat1, math.radians(b.lon - a.lon)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))
