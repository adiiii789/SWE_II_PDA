"""Transitous: Verbindungssuche im öffentlichen Verkehr wie im DB Navigator - Bahn, S-Bahn, U-Bahn,
Tram und Bus in ganz Deutschland (Fahrplandaten von DELFI), von Tür zu Tür samt Fußwegen.

Kostenlos und ohne Key: https://transitous.org/api/ - ein Gemeinschaftsprojekt, gedacht für freie
und nicht-kommerzielle Anwendungen, ohne Garantie. Bitte sparsam abfragen (der Reise-Assistent
fragt je Plan einmal) und mit einem User-Agent, der die Anwendung nennt. Dahinter läuft MOTIS
(https://github.com/motis-project/motis); config.TRANSITOUS_URL kann auch auf eine eigene
MOTIS-Instanz zeigen.

Echtzeit gibt es nur, wo die Verkehrsverbünde sie liefern (Leg.realtime); Preise liefert die API
nicht. Ergebnis im gemeinsamen Format von transit.py.
"""
from __future__ import annotations

import datetime
import logging
from collections.abc import Iterator
from typing import Any
from zoneinfo import ZoneInfo

from backend.integrations import transit
from backend.integrations.geo import Place
from backend.integrations.http import Http, IntegrationError
from backend.integrations.transit import NON_TRANSIT, Journey, Leg

log = logging.getLogger(__name__)

DEFAULT_URL = "https://api.transitous.org"
PLAN_PATH = "/api/v6/plan"
USER_AGENT = "PersonalDigitalAgent/1.0 (Reise-Assistent; Studienprojekt)"
ATTRIBUTION = "ÖPNV-Verbindungen: Transitous (MOTIS), Fahrplandaten u. a. DELFI"
TIMEZONE = ZoneInfo(transit.TIMEZONE_NAME)
NUM_ITINERARIES = 5


class Transitous:
    def __init__(self, http: Http, base_url: str = DEFAULT_URL):
        self.http = http
        self.base_url = base_url.rstrip("/")

    def latest_journey(self, start: Place, end: Place, arrive_by: datetime.datetime, max_transfers: int = 2,
                       min_transfer_minutes: int = 5, max_walk_minutes: int = 15,
                       not_before: datetime.datetime | None = None) -> Journey | None:
        """Späteste Verbindung, die bis arrive_by an der Zieladresse ist und frühestens not_before
        an der Startadresse losgeht; None, wenn keine fährt."""
        return transit.latest(self._plan(start, end, arrive_by, True, max_transfers, min_transfer_minutes,
                                         max_walk_minutes), arrive_by, not_before)

    def earliest_journey(self, start: Place, end: Place, depart_after: datetime.datetime, max_transfers: int = 2,
                         min_transfer_minutes: int = 5, max_walk_minutes: int = 15) -> Journey | None:
        """Verbindung ab depart_after (an der Startadresse), die am frühesten ankommt."""
        return transit.earliest(self._plan(start, end, depart_after, False, max_transfers, min_transfer_minutes,
                                           max_walk_minutes), depart_after)

    def _plan(self, start: Place, end: Place, moment: datetime.datetime, arrive_by: bool, max_transfers: int,
              min_transfer_minutes: int, max_walk_minutes: int) -> list[Journey]:
        walk_s = max_walk_minutes * 60
        params = {"fromPlace": f"{start.lat},{start.lon}", "toPlace": f"{end.lat},{end.lon}",
                  "time": moment.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "arriveBy": "true" if arrive_by else "false", "maxTransfers": max_transfers,
                  "minTransferTime": min_transfer_minutes, "numItineraries": NUM_ITINERARIES,
                  "maxPreTransitTime": walk_s, "maxPostTransitTime": walk_s, "language": "de"}
        data = self.http.get_json(self.base_url + PLAN_PATH, params, headers={"User-Agent": USER_AGENT})
        if not isinstance(data, dict) or not isinstance(data.get("itineraries"), list):
            raise IntegrationError("Ungültige Antwort von Transitous")
        journeys = []
        for itinerary in data["itineraries"]:
            try:   # unvollständig oder eine Fahrt fällt aus
                journey = Journey(tuple(_leg(leg) for leg in itinerary["legs"]), attribution=ATTRIBUTION)
            except (KeyError, TypeError, ValueError):
                log.debug("Transitous: Verbindung übersprungen: %r", itinerary)
                continue
            if journey.rides:   # nur zu Fuß: das vergleicht der Assistent schon selbst
                journeys.append(journey)
        return journeys


def _leg(raw: dict[str, Any]) -> Leg:
    origin, destination = raw["from"], raw["to"]
    mode = raw["mode"]
    walking = mode in NON_TRANSIT
    if raw.get("cancelled") and not walking:
        raise ValueError("Fahrt fällt aus")
    geometry = raw.get("legGeometry") or {}
    return Leg(
        mode=mode,
        line="" if walking else (raw.get("displayName") or raw.get("routeShortName") or raw.get("tripShortName")
                                 or mode.replace("_", " ").title()),
        origin=_name(origin, "Start"),
        destination=_name(destination, "Ziel"),
        departure=_time(raw["startTime"]),
        arrival=_time(raw["endTime"]),
        scheduled_departure=_time(raw.get("scheduledStartTime")),
        scheduled_arrival=_time(raw.get("scheduledEndTime")),
        platform=origin.get("track") or origin.get("scheduledTrack") or "",
        arrival_platform=destination.get("track") or destination.get("scheduledTrack") or "",
        headsign=raw.get("headsign") or "",
        realtime=bool(raw.get("realTime")),
        messages=_messages(raw),
        geometry=tuple(decode_polyline(geometry["points"], geometry.get("precision", 6)))
        if geometry.get("points") else ((origin["lon"], origin["lat"]), (destination["lon"], destination["lat"])),
        stops=tuple((stop.get("name") or "", _time(stop.get("departure") or stop.get("arrival")))
                    for stop in raw.get("intermediateStops") or [] if stop.get("name")),
        color=_color(raw.get("routeColor")),
        text_color=_color(raw.get("routeTextColor")),
    )


def _color(value: str | None) -> str:
    """"fddd04" → "#fddd04"; leer, wenn es keine Farbe ist."""
    value = (value or "").lstrip("#")
    return f"#{value.lower()}" if len(value) == 6 and all(c in "0123456789abcdefABCDEF" for c in value) else ""


def _name(place: dict[str, Any], fallback: str) -> str:
    name = place.get("name") or ""
    return fallback if name in ("", "START", "END") else name


def _messages(raw: dict[str, Any]) -> tuple[str, ...]:
    texts = [transit.short(alert.get("headerText") or alert.get("descriptionText") or "")
             for alert in [*(raw.get("alerts") or []), *(raw["from"].get("alerts") or [])]]
    return tuple(dict.fromkeys(text for text in texts if text))


def _time(text: str | None) -> datetime.datetime | None:
    if not text:
        return None
    return datetime.datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(TIMEZONE)


def decode_polyline(points: str, precision: int = 6) -> Iterator[tuple[float, float]]:
    """Google-Polyline (Breite, Länge abwechselnd, Differenzen) → (Länge, Breite)."""
    factor = 10 ** precision
    index = lat = lon = 0
    while index < len(points):
        deltas = []
        for _ in range(2):
            shift = result = 0
            while True:
                byte = ord(points[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lon += deltas[1]
        yield lon / factor, lat / factor
