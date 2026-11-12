"""VVS (Verkehrs- und Tarifverbund Stuttgart): Verbindungssuche wie auf vvs.de - S-Bahn,
Stadtbahn, Bus, Zahnradbahn und Regionalzüge im VVS-Gebiet, von Tür zu Tür samt Fußwegen,
mit Echtzeit, Gleisen/Steigen und dem echten VVS-Preis (EinzelTicket Erwachsene).

Abgefragt wird die EFA-Auskunft (Mentz), die auch die VVS-Website nutzt (XML_TRIP_REQUEST2,
outputFormat=rapidJSON) - ohne Key, aber auch ohne dokumentierte Nutzungsbedingungen. Deshalb
sparsam (eine Abfrage je Plan, eigener User-Agent) und nur für Wege, die ganz im VVS-Gebiet liegen
(AREA); sonst und bei Ausfall nimmt der Reise-Assistent Transitous (transitous.py). Die offizielle
Schnittstelle für Baden-Württemberg wäre TRIAS über MobiData BW (Zugang auf Antrag bei der NVBW).
Ergebnis im gemeinsamen Format von transit.py.
"""
from __future__ import annotations

import datetime
import logging
import re
from typing import Any
from zoneinfo import ZoneInfo

from backend.integrations import transit
from backend.integrations.geo import Place
from backend.integrations.http import Http, IntegrationError
from backend.integrations.transit import Journey, Leg

log = logging.getLogger(__name__)

DEFAULT_URL = "https://www3.vvs.de/mngvvs"
TRIP_PATH = "/XML_TRIP_REQUEST2"
USER_AGENT = "PersonalDigitalAgent/1.0 (Reise-Assistent; Studienprojekt)"
ATTRIBUTION = "ÖPNV-Verbindungen und Preise im VVS: Verkehrs- und Tarifverbund Stuttgart"
TIMEZONE = ZoneInfo(transit.TIMEZONE_NAME)
COORD = "WGS84[dd.ddddd]"
NUM_TRIPS = 6
# VVS-Gebiet (Stuttgart und die Kreise Böblingen, Esslingen, Ludwigsburg, Rems-Murr, Göppingen), grob
AREA = (48.50, 8.70, 49.10, 9.95)   # Süd, West, Nord, Ost
FARE_PERSON, FARE_VALIDITY = "ADULT", "SINGLE"
URGENT = frozenset({"high", "veryHigh"})   # Hinweise mit dieser Priorität immer zeigen

# EFA-Produktklassen → Verkehrsmittel wie in transit.py (MOTIS-Namen)
MODES = {0: "REGIONAL_RAIL", 1: "SUBURBAN", 2: "SUBWAY", 3: "SUBWAY", 4: "TRAM", 5: "BUS", 6: "BUS", 7: "BUS",
         8: "FUNICULAR", 9: "FERRY", 10: "BUS", 11: "OTHER", 12: "AIRPLANE", 13: "REGIONAL_RAIL",
         14: "LONG_DISTANCE", 15: "LONG_DISTANCE", 16: "LONG_DISTANCE", 17: "BUS", 18: "RAIL", 19: "BUS",
         105: "ODM", 107: "BIKE"}
WALK_CLASSES = frozenset({97, 98, 99, 100})
BUS_MODES = frozenset({"BUS"})   # Linie ohne Buchstaben: "Bus 42" statt "42"


def covers(place: Place) -> bool:
    """Liegt der Ort im VVS-Gebiet?"""
    south, west, north, east = AREA
    return south <= place.lat <= north and west <= place.lon <= east


class Vvs:
    def __init__(self, http: Http, base_url: str = DEFAULT_URL):
        self.http = http
        self.base_url = base_url.rstrip("/")

    def covers(self, start: Place, end: Place) -> bool:
        return covers(start) and covers(end)

    def latest_journey(self, start: Place, end: Place, arrive_by: datetime.datetime, max_transfers: int = 2,
                       min_transfer_minutes: int = 5, max_walk_minutes: int = 15,
                       not_before: datetime.datetime | None = None) -> Journey | None:
        """Späteste Verbindung, die bis arrive_by an der Zieladresse ist und frühestens not_before losgeht."""
        return transit.latest(self._trips(start, end, arrive_by, True, max_transfers, min_transfer_minutes,
                                          max_walk_minutes), arrive_by, not_before)

    def earliest_journey(self, start: Place, end: Place, depart_after: datetime.datetime, max_transfers: int = 2,
                         min_transfer_minutes: int = 5, max_walk_minutes: int = 15) -> Journey | None:
        """Verbindung ab depart_after, die am frühesten ankommt."""
        return transit.earliest(self._trips(start, end, depart_after, False, max_transfers, min_transfer_minutes,
                                            max_walk_minutes), depart_after)

    def _trips(self, start: Place, end: Place, moment: datetime.datetime, arrive_by: bool, max_transfers: int,
               min_transfer_minutes: int, max_walk_minutes: int) -> list[Journey]:
        local = moment.astimezone(TIMEZONE)
        params = {
            "outputFormat": "rapidJSON", "coordOutputFormat": COORD, "language": "de",
            "type_origin": "coord", "name_origin": f"{start.lon:.5f}:{start.lat:.5f}:{COORD}",
            "type_destination": "coord", "name_destination": f"{end.lon:.5f}:{end.lat:.5f}:{COORD}",
            "itdDate": f"{local:%Y%m%d}", "itdTime": f"{local:%H%M}",
            "itdTripDateTimeDepArr": "arr" if arrive_by else "dep",
            "calcNumberOfTrips": NUM_TRIPS, "maxChanges": max_transfers, "routeType": "leasttime",
            "changeSpeed": "slow" if min_transfer_minutes >= 8 else "fast" if min_transfer_minutes <= 3 else "normal",
            "useRealtime": 1, "useProxFootSearch": 1, "trITMOTvalue100": max_walk_minutes,
            "locationServerActive": 1,
        }
        data = self.http.get_json(self.base_url + TRIP_PATH, params, headers={"User-Agent": USER_AGENT})
        if not isinstance(data, dict):
            raise IntegrationError("Ungültige Antwort der VVS-Auskunft")
        journeys = []
        for raw in data.get("journeys") or []:
            try:   # unvollständig oder eine Fahrt fällt aus
                journey = _journey(raw)
            except (KeyError, TypeError, ValueError, IndexError):
                log.debug("VVS: Verbindung übersprungen: %r", raw)
                continue
            shortest = journey.shortest_transfer_minutes()
            # auf ganze Minuten: Die Zeiten haben Sekunden, 4,9 Min. sind für den Fahrgast 5 Min.
            if journey.rides and (shortest is None or round(shortest) >= min_transfer_minutes):
                journeys.append(journey)
        return journeys


def _journey(raw: dict[str, Any]) -> Journey:
    legs: list[Leg] = []
    count = len(raw["legs"])
    for index, item in enumerate(raw["legs"]):
        legs.append(_leg(item, legs[-1] if legs else None, first=index == 0, last=index == count - 1))
    fare, name = _fare(raw.get("fare") or {})
    return Journey(tuple(legs), fare, name, ATTRIBUTION)


def _leg(raw: dict[str, Any], previous: Leg | None, first: bool, last: bool) -> Leg:
    origin, destination = raw["origin"], raw["destination"]
    transportation = raw.get("transportation") or {}
    product = transportation.get("product") or {}
    product_class = product.get("class")
    mode = "WALK" if product_class in WALK_CLASSES or product.get("name") == "footpath" \
        else MODES.get(product_class, "OTHER")
    walking = mode in transit.NON_TRANSIT
    status = raw.get("realtimeStatus") or []
    if not walking and any("CANCEL" in str(entry) for entry in status):
        raise ValueError("Fahrt fällt aus")
    departure = _time(origin.get("departureTimeEstimated") or origin.get("departureTimePlanned"))
    if departure is None:   # Fußwege haben nicht immer Zeiten
        departure = previous.arrival if previous else None
    arrival = _time(destination.get("arrivalTimeEstimated") or destination.get("arrivalTimePlanned"))
    if arrival is None:
        arrival = departure + datetime.timedelta(seconds=raw.get("duration") or 0)
    coords = raw.get("coords") or [origin["coord"], destination["coord"]]
    return Leg(
        mode=mode,
        line="" if walking else _line(transportation, mode),
        origin="Start" if first and origin.get("type") in ("address", "coord") else _name(origin),
        destination="Ziel" if last and destination.get("type") in ("address", "coord") else _name(destination),
        departure=departure,
        arrival=arrival,
        scheduled_departure=_time(origin.get("departureTimePlanned")),
        scheduled_arrival=_time(destination.get("arrivalTimePlanned")),
        platform="" if walking else _platform(origin),
        arrival_platform="" if walking else _platform(destination),
        headsign=((transportation.get("destination") or {}).get("name") or "") if not walking else "",
        realtime="MONITORED" in status,
        messages=() if walking else _messages(raw, origin, destination),
        geometry=tuple((point[1], point[0]) for point in coords),   # EFA: [Breite, Länge]
        stops=() if walking else tuple(
            (_name(stop), _time(stop.get("departureTimeEstimated") or stop.get("departureTimePlanned")
                                or stop.get("arrivalTimeEstimated") or stop.get("arrivalTimePlanned")))
            for stop in (raw.get("stopSequence") or [])[1:-1]),   # ohne Ein- und Ausstieg
    )


def _line(transportation: dict[str, Any], mode: str) -> str:
    line = transportation.get("disassembledName") or transportation.get("number") or transportation.get("name") or ""
    product = (transportation.get("product") or {}).get("name") or ""
    if mode in BUS_MODES and line and line[0].isdigit():
        return f"{product or 'Bus'} {line}"
    return line or product or mode.title()


def _name(place: dict[str, Any]) -> str:
    """Name der Haltestelle (bei einem Gleis der Name des Halts)."""
    if place.get("type") == "platform" and (place.get("parent") or {}).get("name"):
        return place["parent"]["name"]
    return place.get("name") or place.get("disassembledName") or ""


def _platform(place: dict[str, Any]) -> str:
    properties = place.get("properties") or {}
    return str(properties.get("platform") or properties.get("platformName") or "")


def _messages(raw: dict[str, Any], origin: dict[str, Any], destination: dict[str, Any]) -> tuple[str, ...]:
    """Hinweise zur Fahrt. Hinweise zur ganzen Linie (z. B. Bauarbeiten am anderen Ende) nur, wenn
    sie dringend sind oder einen Halt dieser Fahrt nennen."""
    stops = [origin, *(raw.get("stopSequence") or []), destination]
    words = {word.casefold() for stop in stops for word in _words(_name(stop))}
    texts = []
    for info in raw.get("infos") or []:
        for link in info.get("infoLinks") or []:
            text = link.get("urlText") or link.get("subtitle") or link.get("title") or ""
            urgent = info.get("priority") in URGENT
            if text and (urgent or info.get("type") != "lineInfo"
                         or words & {word.casefold() for word in _words(f"{text} {link.get('content') or ''}")}):
                texts.append(transit.short(text))
    return tuple(dict.fromkeys(texts))


def _words(text: str) -> list[str]:
    """Wörter ab 4 Buchstaben, z. B. "Rotebühlplatz", "Vaihingen" (für den Abgleich mit Haltestellen)."""
    return [word for word in re.split(r"[^\w]+", text) if len(word) >= 4 and not word.isdigit()]


def _fare(fare: dict[str, Any]) -> tuple[float | None, str]:
    """Günstigster Einzelfahrschein für Erwachsene (ohne Zuschläge); vom Automaten nur, wenn es
    nichts anderes gibt (dort teurer). (None, "") ohne Preisangabe."""
    singles = [ticket for ticket in fare.get("tickets") or []
               if ticket.get("person") == FARE_PERSON and ticket.get("timeValidity") == FARE_VALIDITY
               and "zuschlag" not in (ticket.get("name") or "").casefold()
               and isinstance(ticket.get("priceBrutto"), (int, float))]
    preferred = [ticket for ticket in singles if "automat" not in ticket["name"].casefold()] or singles
    if not preferred:
        return None, ""
    best = min(preferred, key=lambda ticket: ticket["priceBrutto"])
    return float(best["priceBrutto"]), best["name"]


def _time(text: str | None) -> datetime.datetime | None:
    if not text:
        return None
    return datetime.datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(TIMEZONE)
