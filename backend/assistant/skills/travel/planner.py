"""Bewertung der Verkehrsmittel - reine Rechenlogik, ohne Netzwerk.

Empfohlen wird das Verkehrsmittel mit den geringsten Kosten:
    Kosten = Preis + Reisezeit × Zeitwert
Zeit zählt also mit: Bei 25 €/h ist eine 20 Minuten schnellere Fahrt 8,33 € wert.

Persönliche Werte stehen in den Präferenzen (preferences.json) unter "travel_<feld>",
z. B. "travel_value_of_time": 40 oder "travel_deutschlandticket": true.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field, fields
from typing import Any

from backend.integrations.db_timetables import TrainConnection
from backend.integrations.geo import Place
from backend.integrations.openrouteservice import Route
from backend.preferences import PreferenceStore

PREFERENCE_PREFIX = "travel_"
HOME_ADDRESS = "travel_home_address"

CAR, TRAIN, TAXI, BIKE, FOOT = "car", "train", "taxi", "bike", "foot"
LABELS = {CAR: "Auto", TRAIN: "Bahn", TAXI: "Taxi", BIKE: "Fahrrad", FOOT: "Zu Fuß"}


@dataclass(frozen=True)
class TravelSettings:
    value_of_time: float = 25.0          # €/h - was dir eine Stunde Reisezeit wert ist
    buffer_minutes: int = 5              # so viel früher als Terminbeginn ankommen
    deutschlandticket: bool = False      # Nahverkehr (RE, RB, S, Bus) kostet dann nichts
    fuel: str = "e5"                     # e5, e10 oder diesel
    consumption: float = 7.0             # l/100 km
    fuel_price: float = 1.80             # €/l, wenn Tankerkönig nichts liefert
    car_time_factor: float = 1.15        # ORS kennt keinen Stau: Fahrzeit × Faktor
    taxi_base: float = 4.50              # € Grundpreis
    taxi_per_km: float = 2.60            # €/km
    taxi_wait_minutes: int = 5           # bis das Taxi da ist
    max_walk_km: float = 5.0             # weiter wird zu Fuß nicht vorgeschlagen (Luftlinie)
    max_bike_km: float = 25.0            # dito Fahrrad
    station_walk_minutes: int = 20       # länger zum Bahnhof: Bus/Tram (geschätzt) statt zu Fuß
    local_transit_fare: float = 3.00     # € Bus/Tram zum Bahnhof ohne Deutschlandticket
    rail_regional_per_km: float = 0.20   # €/km Nahverkehr (Schätzung)
    rail_long_distance_per_km: float = 0.25   # €/km Fernverkehr, eher Flexpreis als Sparpreis
    rail_min_fare: float = 2.50          # €

    @classmethod
    def from_preferences(cls, preferences: PreferenceStore) -> TravelSettings:
        values: dict[str, Any] = {}
        for f in fields(cls):
            value = preferences.get(PREFERENCE_PREFIX + f.name)
            default = f.default
            if value is None:
                continue
            if isinstance(default, bool):
                values[f.name] = bool(value)
            elif isinstance(default, (int, float)) and isinstance(value, (int, float)) and not isinstance(value, bool):
                values[f.name] = type(default)(value)
            elif isinstance(default, str) and isinstance(value, str):
                values[f.name] = value
        return cls(**values)


@dataclass(frozen=True)
class Option:
    mode: str
    duration_s: float
    price_eur: float
    distance_m: float = 0.0
    price_estimated: bool = False        # Schätzung statt echtem Preis (in der Ansicht mit ≈)
    detail: str = ""                     # z. B. "RE 4 ab Mannheim Hbf 08:12, Gleis 3"
    steps: tuple[str, ...] = ()
    geometry: tuple[tuple[float, float], ...] = field(default=(), repr=False)
    depart_at: datetime.datetime | None = None
    arrive_at: datetime.datetime | None = None

    @property
    def label(self) -> str:
        return LABELS[self.mode]

    def cost(self, settings: TravelSettings) -> float:
        return self.price_eur + self.duration_s / 3600 * settings.value_of_time


@dataclass(frozen=True)
class TripPlan:
    origin: Place
    destination: Place
    arrive_by: datetime.datetime         # Terminbeginn
    options: tuple[Option, ...]          # nach Kosten sortiert, die erste ist die Empfehlung
    settings: TravelSettings
    notes: tuple[str, ...] = ()          # z. B. "Bahn: keine Direktverbindung gefunden"

    @property
    def recommended(self) -> Option | None:
        return self.options[0] if self.options else None


def car_option(route: Route, fuel_price: float, fuel_price_estimated: bool,
               settings: TravelSettings, arrive_by: datetime.datetime) -> Option:
    liters = route.distance_m / 1000 * settings.consumption / 100
    return _door_to_door(CAR, route, route.duration_s * settings.car_time_factor, liters * fuel_price,
                         fuel_price_estimated, settings, arrive_by,
                         f"Sprit {liters:.1f} l × {fuel_price:.2f} €/l".replace(".", ","))


def taxi_option(route: Route, settings: TravelSettings, arrive_by: datetime.datetime) -> Option:
    price = settings.taxi_base + route.distance_m / 1000 * settings.taxi_per_km
    duration = route.duration_s * settings.car_time_factor + settings.taxi_wait_minutes * 60
    return _door_to_door(TAXI, route, duration, price, True, settings, arrive_by,
                         f"inkl. {settings.taxi_wait_minutes} Min. Wartezeit")


def bike_option(route: Route, settings: TravelSettings, arrive_by: datetime.datetime) -> Option:
    return _door_to_door(BIKE, route, route.duration_s, 0.0, False, settings, arrive_by)


def walk_option(route: Route, settings: TravelSettings, arrive_by: datetime.datetime) -> Option:
    return _door_to_door(FOOT, route, route.duration_s, 0.0, False, settings, arrive_by)


@dataclass(frozen=True)
class Leg:
    """Weg zum oder vom Bahnhof."""
    duration_s: float
    price_eur: float = 0.0
    description: str = ""                # z. B. "12 Min. zu Fuß"


def walk_or_transit_leg(walk: Route, car: Route | None, settings: TravelSettings) -> Leg:
    """Zu Fuß zum Bahnhof, wenn es kurz genug ist; sonst Bus/Tram, geschätzt aus der Autofahrzeit."""
    if walk.duration_s <= settings.station_walk_minutes * 60 or car is None:
        return Leg(walk.duration_s, 0.0, f"{_minutes(walk.duration_s)} Min. zu Fuß")
    duration = car.duration_s * 2 + 5 * 60   # Umwege und Wartezeit
    price = 0.0 if settings.deutschlandticket else settings.local_transit_fare
    return Leg(duration, price, f"≈ {_minutes(duration)} Min. Bus/Tram")


def train_option(connection: TrainConnection, access: Leg, egress: Leg, rail_distance_km: float,
                 settings: TravelSettings) -> Option:
    if connection.long_distance:
        fare = max(settings.rail_min_fare, rail_distance_km * settings.rail_long_distance_per_km)
    elif settings.deutschlandticket:
        fare = 0.0
    else:
        fare = max(settings.rail_min_fare, rail_distance_km * settings.rail_regional_per_km)
    depart_at = connection.departure - datetime.timedelta(seconds=access.duration_s)
    arrive_at = connection.arrival + datetime.timedelta(seconds=egress.duration_s)
    platform = f", Gleis {connection.platform}" if connection.platform else ""
    steps = (f"{access.description} zu {connection.origin.name}",
             f"{connection.train} ab {connection.departure:%H:%M}{platform}, an {connection.destination.name} "
             f"{connection.arrival:%H:%M}",
             f"{egress.description} zum Ziel")
    return Option(TRAIN, (arrive_at - depart_at).total_seconds(), fare + access.price_eur + egress.price_eur,
                  rail_distance_km * 1000, price_estimated=True,
                  detail=f"{connection.train} ab {connection.origin.name} {connection.departure:%H:%M}{platform}",
                  steps=steps, depart_at=depart_at, arrive_at=arrive_at)


def rank(options: list[Option], settings: TravelSettings) -> tuple[Option, ...]:
    return tuple(sorted(options, key=lambda option: option.cost(settings)))


def _door_to_door(mode: str, route: Route, duration_s: float, price: float, estimated: bool,
                  settings: TravelSettings, arrive_by: datetime.datetime, detail: str = "") -> Option:
    arrive_at = arrive_by - datetime.timedelta(minutes=settings.buffer_minutes)
    return Option(mode, duration_s, price, route.distance_m, estimated, detail,
                  tuple(step.instruction for step in route.steps if step.instruction), route.geometry,
                  arrive_at - datetime.timedelta(seconds=duration_s), arrive_at)


def _minutes(seconds: float) -> int:
    return max(1, round(seconds / 60))
