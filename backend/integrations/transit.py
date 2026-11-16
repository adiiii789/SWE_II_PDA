"""Gemeinsames Format für Verbindungen im öffentlichen Verkehr von Tür zu Tür: Fußwege, Busse,
Trams und Züge. Liefern transitous.py (deutschlandweit) und vvs.py (Verkehrsverbund Stuttgart);
der Reise-Assistent bewertet beide gleich (planner.transit_option).

Verkehrsmittel heißen wie bei MOTIS (WALK, BUS, TRAM, SUBURBAN, REGIONAL_RAIL, LONG_DISTANCE …);
vvs.py übersetzt seine Produktklassen in diese Namen.
"""
from __future__ import annotations

import datetime
from collections.abc import Iterable
from dataclasses import dataclass, field

from backend.integrations.geo import Place, distance_km

TIMEZONE_NAME = "Europe/Berlin"
TRANSFER_PENALTY = datetime.timedelta(minutes=10)   # wie db_timetables: ein Umstieg zählt wie 10 Min.
MAX_MESSAGE_CHARS = 160

WALK = "WALK"
RAIL_MODES = frozenset({"RAIL", "HIGHSPEED_RAIL", "LONG_DISTANCE", "NIGHT_RAIL", "REGIONAL_FAST_RAIL",
                        "REGIONAL_RAIL", "SUBURBAN", "SUBWAY", "METRO"})
# Hier gilt das Deutschlandticket nicht (Fernzüge, Fernbusse)
LONG_DISTANCE_MODES = frozenset({"HIGHSPEED_RAIL", "LONG_DISTANCE", "NIGHT_RAIL", "COACH"})
NON_TRANSIT = frozenset({WALK, "BIKE", "RENTAL", "CAR", "CAR_PARKING", "CAR_DROPOFF", "HGV", "ODM",
                         "RIDE_SHARING", "FLEX"})


@dataclass(frozen=True)
class Leg:
    """Ein Stück der Verbindung: zu Fuß (mode WALK) oder mit einem Fahrzeug."""
    mode: str                            # z. B. WALK, BUS, TRAM, SUBWAY, REGIONAL_RAIL
    line: str                            # z. B. "S8", "RE10a (19259)", "Bus 42"; zu Fuß leer
    origin: str                          # Haltestelle bzw. "Start"
    destination: str
    departure: datetime.datetime         # mit Echtzeit: Prognose
    arrival: datetime.datetime
    scheduled_departure: datetime.datetime | None = None
    scheduled_arrival: datetime.datetime | None = None
    platform: str = ""                   # Gleis bzw. Steig der Abfahrt
    arrival_platform: str = ""
    headsign: str = ""                   # Richtung
    realtime: bool = False
    messages: tuple[str, ...] = ()       # Störungen und Hinweise
    geometry: tuple[tuple[float, float], ...] = field(default=(), repr=False)   # (Länge, Breite)
    stops: tuple[tuple[str, datetime.datetime | None], ...] = ()   # Zwischenhalte mit Abfahrtszeit
    color: str = ""                      # Linienfarbe "#rrggbb", wenn die Auskunft sie kennt
    text_color: str = ""

    @property
    def walking(self) -> bool:
        return self.mode in NON_TRANSIT

    @property
    def rail(self) -> bool:
        return self.mode in RAIL_MODES

    @property
    def long_distance(self) -> bool:
        return self.mode in LONG_DISTANCE_MODES

    @property
    def distance_km(self) -> float:
        return sum(distance_km(Place("", a[1], a[0]), Place("", b[1], b[0]))
                   for a, b in zip(self.geometry, self.geometry[1:]))

    @property
    def departure_delay(self) -> int:
        return delay(self.scheduled_departure, self.departure)

    @property
    def arrival_delay(self) -> int:
        return delay(self.scheduled_arrival, self.arrival)


@dataclass(frozen=True)
class Journey:
    """Verbindung von Tür zu Tür (beginnt und endet meist mit einem Fußweg)."""
    legs: tuple[Leg, ...]
    fare_eur: float | None = None        # echter Preis (Einzelfahrschein), wenn die Auskunft ihn kennt
    fare_name: str = ""                  # z. B. "EinzelTicket Erwachsene"
    attribution: str = ""                # Quelle für die Ansicht

    @property
    def rides(self) -> tuple[Leg, ...]:
        return tuple(leg for leg in self.legs if not leg.walking)

    @property
    def departure(self) -> datetime.datetime:
        return self.legs[0].departure

    @property
    def arrival(self) -> datetime.datetime:
        return self.legs[-1].arrival

    @property
    def transfers(self) -> int:
        return max(0, len(self.rides) - 1)

    @property
    def long_distance(self) -> bool:
        return any(leg.long_distance for leg in self.rides)

    @property
    def realtime(self) -> bool:
        return any(leg.realtime for leg in self.rides)

    def shortest_transfer_minutes(self) -> float | None:
        """Kürzeste Zeit zwischen Ankunft eines Fahrzeugs und Abfahrt des nächsten (inkl. Fußweg)."""
        rides = self.rides
        gaps = [(b.departure - a.arrival).total_seconds() / 60 for a, b in zip(rides, rides[1:])]
        return min(gaps, default=None)


def latest(journeys: Iterable[Journey], arrive_by: datetime.datetime,
           not_before: datetime.datetime | None = None) -> Journey | None:
    """Späteste Verbindung, die bis arrive_by ankommt und frühestens not_before losgeht;
    ein Umstieg zählt wie TRANSFER_PENALTY spätere Abfahrt weniger."""
    candidates = [j for j in journeys if j.arrival <= arrive_by and (not_before is None or j.departure >= not_before)]
    return max(candidates, key=lambda j: (j.departure - j.transfers * TRANSFER_PENALTY, -j.arrival.timestamp()),
               default=None)


def earliest(journeys: Iterable[Journey], depart_after: datetime.datetime) -> Journey | None:
    """Verbindung ab depart_after, die (mit TRANSFER_PENALTY je Umstieg) am frühesten ankommt."""
    candidates = [j for j in journeys if j.departure >= depart_after]
    return min(candidates, key=lambda j: (j.arrival + j.transfers * TRANSFER_PENALTY, -j.departure.timestamp()),
               default=None)


def short(text: str) -> str:
    """Hinweistext auf eine Zeile und MAX_MESSAGE_CHARS gekürzt."""
    text = " ".join(text.split())
    return text if len(text) <= MAX_MESSAGE_CHARS else text[:MAX_MESSAGE_CHARS - 1].rsplit(" ", 1)[0] + " …"


def delay(scheduled: datetime.datetime | None, actual: datetime.datetime) -> int:
    if scheduled is None:
        return 0
    return max(0, round((actual - scheduled).total_seconds() / 60))
