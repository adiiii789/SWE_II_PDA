"""Deutsche Bahn, API Marketplace: Timetables (Soll-Fahrplan je Bahnhof und Stunde).

Kostenlos: https://developers.deutschebahn.com → Anwendung anlegen, "Timetables" abonnieren,
Client-ID und API-Key → PDA_DB_CLIENT_ID, PDA_DB_API_KEY.

Die API kennt keine Verbindungssuche von A nach B, nur Abfahrtstafeln. Daraus sucht
latest_direct() Direktverbindungen: Ein Halt am Zielbahnhof, dessen Ankunft vom
Startbahnhof kommt (ppth = die Halte davor), und derselbe Zug (gleiche Fahrt-ID) am
Startbahnhof. Umstiege findet sie nicht. Preise liefert die DB hier nicht.
Fahrplandaten gibt es nur für die nächsten Stunden (etwa bis morgen).
"""
from __future__ import annotations

import datetime
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from backend.integrations.http import Http, IntegrationError

BASE_URL = "https://apis.deutschebahn.com/db-api-marketplace/apis/timetables/v1"
TIMEZONE = ZoneInfo("Europe/Berlin")   # Zeiten im Fahrplan sind deutsche Ortszeit
SEARCH_HOURS = 4                       # so viele Stunden vor der Ankunft wird gesucht
MAX_CANDIDATES = 3                     # Ankünfte, für die der Startbahnhof geprüft wird
MAX_CACHED_PLANS = 200                 # Stundenpläne im Speicher (die App läuft tagelang)

# Züge, für die das Deutschlandticket nicht gilt
LONG_DISTANCE = frozenset({"ICE", "IC", "EC", "ECE", "EN", "NJ", "RJ", "RJX", "TGV", "FLX", "ES", "EST", "WB"})


@dataclass(frozen=True)
class Station:
    name: str        # z. B. "Mannheim Hbf" - so steht er auch in den Laufwegen (ppth)
    eva: str         # Bahnhofsnummer, z. B. "8000244"


@dataclass(frozen=True)
class _Stop:
    trip: str                            # Fahrt-ID, an allen Halten desselben Zugs gleich
    train: str                           # z. B. "ICE 597", "RE 4", "S 1"
    category: str                        # z. B. "ICE"
    arrival: datetime.datetime | None
    arrival_path: tuple[str, ...]        # Halte vor diesem
    departure: datetime.datetime | None
    platform: str


@dataclass(frozen=True)
class TrainConnection:
    train: str
    long_distance: bool
    origin: Station
    destination: Station
    departure: datetime.datetime
    arrival: datetime.datetime
    platform: str = ""


class DbTimetables:
    def __init__(self, http: Http, client_id: str, api_key: str):
        self.http = http
        self.headers = {"DB-Client-Id": client_id, "DB-Api-Key": api_key, "Accept": "application/xml"}
        self._plans: dict[tuple[str, str], list[_Stop]] = {}

    def find_station(self, name: str) -> Station:
        """Bahnhof zu einem Ortsnamen. Bevorzugt den Hauptbahnhof ("Mannheim" → "Mannheim Hbf")."""
        root = self._get(f"/station/{urllib.parse.quote(name)}")
        stations = [Station(s.get("name", ""), s.get("eva", "")) for s in root.iter("station") if s.get("eva")]
        if not stations:
            raise IntegrationError(f"Kein Bahnhof zu {name!r} gefunden")
        main = [s for s in stations if "Hbf" in s.name and s.name.startswith(name.split()[0])]
        return (main or stations)[0]

    def latest_direct(self, origin: Station, destination: Station,
                      arrive_by: datetime.datetime) -> TrainConnection | None:
        """Späteste Direktverbindung, die bis arrive_by am Ziel ist; None, wenn keine fährt."""
        arrive_by = arrive_by.astimezone(TIMEZONE)
        arrivals = sorted((stop for hour in _hours_back(arrive_by, SEARCH_HOURS)
                           for stop in self._plan(destination.eva, hour)
                           if stop.arrival and stop.arrival <= arrive_by and origin.name in stop.arrival_path),
                          key=lambda stop: stop.arrival, reverse=True)
        for arrival in arrivals[:MAX_CANDIDATES]:
            departure = self._departure(origin, arrival)
            if departure:
                return TrainConnection(arrival.train, arrival.category in LONG_DISTANCE, origin, destination,
                                       departure.departure, arrival.arrival, departure.platform)
        return None

    def _departure(self, origin: Station, arrival: _Stop) -> _Stop | None:
        for hour in _hours_back(arrival.arrival, SEARCH_HOURS):
            for stop in self._plan(origin.eva, hour):
                if stop.trip == arrival.trip and stop.departure and stop.departure < arrival.arrival:
                    return stop
        return None

    def _plan(self, eva: str, hour: datetime.datetime) -> list[_Stop]:
        key = (eva, f"{hour:%y%m%d/%H}")
        if key not in self._plans:   # jede Stunde nur einmal abfragen (Limit: 60 Abfragen pro Minute)
            if len(self._plans) >= MAX_CACHED_PLANS:
                self._plans.clear()
            self._plans[key] =[_stop(s) for s in self._get(f"/plan/{eva}/{key[1]}").iter("s")]
        return self._plans[key]

    def _get(self, path: str) -> ET.Element:
        text = self.http.get_text(BASE_URL + path, headers=self.headers)
        try:
            return ET.fromstring(text)
        except ET.ParseError:
            raise IntegrationError("Ungültige Antwort der DB-Timetables-API") from None


def _stop(element: ET.Element) -> _Stop:
    line = element.find("tl")
    line = line.attrib if line is not None else {}
    arrival, departure = element.find("ar"), element.find("dp")
    event = departure if departure is not None else arrival
    category = line.get("c", "")
    number = (event.get("l") if event is not None else None) or line.get("n", "")
    return _Stop(
        trip=element.get("id", "").rsplit("-", 1)[0],   # "<Fahrt>-<Datum>-<Halt-Nr.>" ohne Halt-Nr.
        train=f"{category} {number}".strip(),
        category=category,
        arrival=_time(arrival),
        arrival_path=tuple(arrival.get("ppth", "").split("|")) if arrival is not None else (),
        departure=_time(departure),
        platform=(event.get("pp", "") if event is not None else ""),
    )


def _time(event: ET.Element | None) -> datetime.datetime | None:
    if event is None or not event.get("pt"):
        return None
    return datetime.datetime.strptime(event.get("pt"), "%y%m%d%H%M").replace(tzinfo=TIMEZONE)


def _hours_back(moment: datetime.datetime, count: int) -> list[datetime.datetime]:
    start = moment.replace(minute=0, second=0, microsecond=0)
    return [start - datetime.timedelta(hours=h) for h in range(count)]
