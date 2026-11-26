"""Deutsche Bahn, API Marketplace: Bahnverbindungen aus OpenBoards (Echtzeit) und Timetables.

Kostenlos: https://developers.deutschebahn.com → Anwendung anlegen, "OpenBoards" und "Timetables"
abonnieren, Client-ID und API-Key → PDA_DB_CLIENT_ID, PDA_DB_API_KEY.

  OpenBoards   Abfahrts- und Ankunftstafeln mit Prognosezeiten, Gleis, Ausfällen und Störungstexten
               (POST /departures, /arrivals). Löst laut DB die Timetables-API ab.
  Timetables   Ersatz: Ist OpenBoards nicht abonniert oder gestört, sucht der Assistent im
               Soll-Fahrplan (/plan) - dann ohne Verspätungen. Und die Bahnhofssuche nach Namen
               (/station, find_station), wenn die StaDa-Liste fehlt (db_stations.py).

Keine der APIs kennt eine Verbindungssuche von A nach B, nur Tafeln. Jeder Halt nennt aber den
Laufweg: bei der Ankunft die Halte davor, bei der Abfahrt die Halte danach. Daraus sucht _find()
in Runden (bis max_transfers, höchstens MAX_TRANSFERS):
  Bahnhöfe       Abgefragt werden die Tafeln von Start (Abfahrten), Ziel (Ankünfte) und einigen
                 Umstiegsbahnhöfen (beides). Jede Runde nimmt neue Umstiegsbahnhöfe dazu
                 (STATIONS_PER_ROUND): zuerst solche, die im Laufweg eines Zugs liegen, der vom Start
                 (bzw. einem schon abgefragten Bahnhof auf der Startseite) kommt, und eines Zugs, der
                 zum Ziel fährt - gezählt wie oft, meist die großen Knoten. Gibt es keinen solchen und
                 sind noch Runden übrig, die größten Bahnhöfe auf einer Seite (mit StaDa-Kategorie und
                 Koordinaten, sonst die häufigsten); deren Tafeln verbinden dann in der nächsten Runde.
  Verbindungen   _connect() fährt von jeder Abfahrt am Start aus mit den Zügen zu den abgefragten
                 Bahnhöfen weiter (RAPTOR-artig: eine Runde je Zug, je Bahnhof die früheste Ankunft,
                 Anschluss frühestens nach min_transfer_minutes). Die Fahrt-ID verbindet die Halte
                 desselben Zugs auf den verschiedenen Tafeln.
Die erste Runde (ein Umstieg) läuft immer; weitere Umstiege sucht die Suche nur, wenn es mit weniger
keine Verbindung gibt - jeder Bahnhof kostet etwa 10 Abfragen. Preise liefert die DB hier nicht.
Mit OpenBoards zählen die Prognosezeiten: Ein verspäteter Zug kann zu spät ankommen, ein
Anschluss platzen; ausgefallene Halte fehlen ganz.
"""
from __future__ import annotations

import bisect
import datetime
import logging
import math
import time
import urllib.parse
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, replace
from typing import Any
from zoneinfo import ZoneInfo

from backend.integrations.geo import Place, distance_km
from backend.integrations.http import Http, IntegrationError

log = logging.getLogger(__name__)

BASE_URL = "https://apis.deutschebahn.com/db-api-marketplace/apis/timetables/v1"
BOARDS_URL = "https://apis.deutschebahn.com/db-api-marketplace/apis/open-boards/v1"
TIMEZONE = ZoneInfo("Europe/Berlin")   # Zeiten im Fahrplan sind deutsche Ortszeit
SEARCH_HOURS = 4                       # so weit vor der Ankunft bzw. nach der Abfahrt wird gesucht
MAX_TRANSFERS = 3                      # mehr Umstiege sucht der Assistent nicht
STATIONS_PER_ROUND = (3, 2, 2)         # neue Umstiegsbahnhöfe je Suchrunde (1., 2., 3. Umstieg)
MAX_DETOUR = 1.5                       # Umstiegsbahnhof höchstens so viel Umweg (Luftlinie) …
DETOUR_SLACK_KM = 20.0                 # … plus so viel (bei kurzen Wegen liegen Knoten oft daneben)
UNKNOWN_CATEGORY = 7                   # Bahnhof ohne StaDa-Kategorie zählt wie ein kleiner Halt
MAX_LOOKUPS_PER_STATION = 3            # Kandidaten je gesuchtem Umstiegsbahnhof, die nachgeschlagen werden
TRANSFER_PENALTY = datetime.timedelta(minutes=10)   # ein Umstieg zählt beim Vergleich wie 10 Min. später
MAX_CACHED_PLANS = 200                 # Stundenpläne/-tafeln im Speicher (die App läuft tagelang)
BOARD_CACHE_S = 60                     # Echtzeit-Tafeln so lange wiederverwenden

# OpenBoards: eine Abfrage je Bahnhof, Stunde und Tafel (höchstens 50 Züge je Produktklasse)
TRANSPORT_TYPES = ("HIGH_SPEED_TRAIN", "INTERCITY_TRAIN", "INTER_REGIONAL_TRAIN", "REGIONAL_TRAIN", "CITY_TRAIN")
MAX_ENTRIES = 50
MAX_VIA_STOPS = 99                     # ganzer Laufweg statt der 3 wichtigsten Halte (Umstiegssuche)
MAX_MESSAGE_CHARS = 160                # lange Hinweise (z. B. Aufzüge) werden gekürzt
DEPARTURES, ARRIVALS = "departures", "arrivals"
SKIPPED_CAUSE_CODES = {"00"}           # "keine Verspätungsbegründung"

# Züge, für die das Deutschlandticket nicht gilt
LONG_DISTANCE = frozenset({"ICE", "IC", "EC", "ECE", "EN", "NJ", "RJ", "RJX", "TGV", "FLX", "ES", "EST", "WB"})
LONG_DISTANCE_TYPES = frozenset({"HIGH_SPEED_TRAIN", "INTERCITY_TRAIN"})


@dataclass(frozen=True)
class Station:
    name: str        # z. B. "Mannheim Hbf" - so steht er auch in den Laufwegen (ppth)
    eva: str         # Bahnhofsnummer, z. B. "8000244"
    lat: float | None = field(default=None, compare=False)   # aus StaDa (db_stations.py), sonst None
    lon: float | None = field(default=None, compare=False)
    category: int | None = field(default=None, compare=False)   # StaDa: 1 = großer Knoten … 7 = kleiner Halt


@dataclass(frozen=True)
class _Stop:
    """Halt eines Zugs an einem Bahnhof. Zeiten: Prognose (OpenBoards) bzw. Soll (Timetables)."""
    trip: str                            # Fahrt-ID, an allen Halten desselben Zugs gleich
    train: str                           # z. B. "ICE 597", "RE 4", "S 1"
    long_distance: bool
    arrival: datetime.datetime | None
    arrival_path: tuple[str, ...]        # Halte vor diesem (Namen bzw. EVA-Nummern)
    departure: datetime.datetime | None
    departure_path: tuple[str, ...]      # Halte nach diesem
    platform: str                        # Abfahrtsgleis, sonst Ankunftsgleis
    arrival_platform: str
    arrival_scheduled: datetime.datetime | None = None    # Soll; None = wie arrival
    departure_scheduled: datetime.datetime | None = None
    messages: tuple[str, ...] = ()       # Störungen, Verspätungsgründe, Hinweise
    realtime: bool = False
    place_eva: str = ""                  # tatsächlicher Halt im Umsteigebereich (OpenBoards)


@dataclass(frozen=True)
class _Event:
    """Eine Abfahrt oder Ankunft aus OpenBoards."""
    trip: str
    eva: str                             # Halt, an dem der Zug hält (kann im Umsteigebereich abweichen)
    train: str
    long_distance: bool
    time: datetime.datetime              # beste bekannte Zeit (Prognose)
    scheduled: datetime.datetime
    platform: str
    path: tuple[str, ...]                # EVA-Nummern danach (Abfahrt) bzw. davor (Ankunft)
    messages: tuple[str, ...]


@dataclass(frozen=True)
class TrainConnection:
    """Eine Fahrt mit einem Zug."""
    train: str
    long_distance: bool
    origin: Station
    destination: Station
    departure: datetime.datetime         # mit Echtzeit: Prognose
    arrival: datetime.datetime
    platform: str = ""                   # Abfahrtsgleis
    arrival_platform: str = ""
    scheduled_departure: datetime.datetime | None = None   # Soll; None = wie departure
    scheduled_arrival: datetime.datetime | None = None
    messages: tuple[str, ...] = ()       # z. B. "Reparatur am Zug", "Bauarbeiten"
    realtime: bool = False               # Zeiten aus OpenBoards (sonst Soll-Fahrplan)
    via: tuple[str, ...] = ()            # EVA-Nummern der Halte dazwischen, in Fahrtrichtung (nur OpenBoards)

    @property
    def legs(self) -> tuple[TrainConnection, ...]:
        return (self,)

    @property
    def transfers(self) -> int:
        return 0

    @property
    def departure_delay(self) -> int:
        """Minuten später als geplant (0 = pünktlich oder unbekannt)."""
        return _delay(self.scheduled_departure, self.departure)

    @property
    def arrival_delay(self) -> int:
        return _delay(self.scheduled_arrival, self.arrival)


@dataclass(frozen=True)
class Journey:
    """Verbindung aus einem oder mehreren Zügen (mit Umstieg)."""
    legs: tuple[TrainConnection, ...]

    @property
    def train(self) -> str:
        return " → ".join(leg.train for leg in self.legs)

    @property
    def long_distance(self) -> bool:
        return any(leg.long_distance for leg in self.legs)

    @property
    def origin(self) -> Station:
        return self.legs[0].origin

    @property
    def destination(self) -> Station:
        return self.legs[-1].destination

    @property
    def departure(self) -> datetime.datetime:
        return self.legs[0].departure

    @property
    def arrival(self) -> datetime.datetime:
        return self.legs[-1].arrival

    @property
    def platform(self) -> str:
        return self.legs[0].platform

    @property
    def transfers(self) -> int:
        return len(self.legs) - 1

    @property
    def realtime(self) -> bool:
        return all(leg.realtime for leg in self.legs)

    @property
    def messages(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(message for leg in self.legs for message in leg.messages))


Stops = Callable[[str, datetime.datetime, datetime.datetime, tuple[str, ...]], list[_Stop]]
# Ein Stück einer Verbindung in der Suche: (Halt beim Einsteigen, dessen Bahnhof, Halt beim Aussteigen, dessen Bahnhof)
_Ride = tuple[_Stop, str, _Stop, str]


class DbTimetables:
    def __init__(self, http: Http, client_id: str, api_key: str, open_boards: bool = True,
                 clock: Callable[[], float] = time.monotonic,
                 locate: Callable[[str], Station | None] | None = None):
        """locate: Bahnhof mit Koordinaten und Kategorie zu EVA-Nummer oder Namen, ohne Netzwerk
        (DbStations.lookup) - damit wählt die Suche Umstiegsbahnhöfe nach Größe und Lage."""
        self.http = http
        self.locate = locate
        keys = {"DB-Client-Id": client_id, "DB-Api-Key": api_key}
        self.headers = {**keys, "Accept": "application/xml"}
        self.board_headers = {**keys, "Accept": "application/vnd.de.db.ris+json, application/json"}
        self.open_boards = open_boards
        self.clock = clock
        self._plans: dict[tuple[str, str], list[_Stop]] = {}
        self._boards: dict[tuple[str, str, str], tuple[float, list[_Event]]] = {}
        self._stations: dict[str, Station | None] = {}
        self._names: dict[str, str] = {}           # EVA → Name (aus den OpenBoards-Antworten)
        self._areas: dict[str, set[str]] = {}      # EVA → Haltestellen im selben Umsteigebereich

    def find_station(self, name: str) -> Station:
        """Bahnhof zu einem Ortsnamen. Bevorzugt den Hauptbahnhof ("Mannheim" → "Mannheim Hbf").
        Die Timetables-Suche liefert meist nur einen Treffer, und zu "Mannheim" ist das
        "Mannheim ARENA/Maimarkt" - deshalb erst "<Ort> Hbf", dann der Ort selbst."""
        first_word = name.split()[0]
        candidates: list[Station] = []
        for pattern in (f"{name} Hbf", name):
            candidates += [s for s in self._search(pattern) if _is_rail_station(s)]
            main = [s for s in candidates if "Hbf" in s.name and s.name.startswith(first_word)]
            if main:
                return main[0]
        if not candidates:
            raise IntegrationError(f"Kein Bahnhof zu {name!r} gefunden")
        return candidates[0]

    def latest_journey(self, origin: Station, destination: Station, arrive_by: datetime.datetime,
                       max_transfers: int = 1, min_transfer_minutes: int = 5,
                       not_before: datetime.datetime | None = None) -> Journey | None:
        """Späteste Verbindung, die bis arrive_by am Ziel ist und frühestens not_before abfährt
        (z. B. jetzt + Weg zum Bahnhof); None, wenn keine fährt.
        Ein Umstieg zählt dabei wie TRANSFER_PENALTY spätere Abfahrt weniger."""
        arrive_by = arrive_by.astimezone(TIMEZONE)
        start = arrive_by - datetime.timedelta(hours=SEARCH_HOURS)
        if not_before is not None:
            start = max(start, not_before.astimezone(TIMEZONE))
        if start >= arrive_by:
            return None
        journeys = self._journeys(origin, destination, start, arrive_by, max_transfers, min_transfer_minutes)
        return max(journeys, key=lambda j: (j.departure - j.transfers * TRANSFER_PENALTY, -j.arrival.timestamp()),
                   default=None)

    def earliest_journey(self, origin: Station, destination: Station, depart_after: datetime.datetime,
                         max_transfers: int = 1, min_transfer_minutes: int = 5) -> Journey | None:
        """Verbindung ab depart_after, die am frühesten ankommt; None, wenn keine fährt."""
        depart_after = depart_after.astimezone(TIMEZONE)
        journeys = self._journeys(origin, destination, depart_after,
                                  depart_after + datetime.timedelta(hours=SEARCH_HOURS),
                                  max_transfers, min_transfer_minutes)
        return min(journeys, key=lambda j: (j.arrival + j.transfers * TRANSFER_PENALTY, -j.departure.timestamp()),
                   default=None)

    # --- Suche ---------------------------------------------------------------------------
    def _journeys(self, origin: Station, destination: Station, start: datetime.datetime, end: datetime.datetime,
                  max_transfers: int, min_transfer_minutes: int) -> list[Journey]:
        """Erst mit Echtzeit (OpenBoards), sonst im Soll-Fahrplan. Nie gemischt: Die Fahrt-IDs der
        beiden APIs passen nicht zueinander."""
        if self.open_boards:
            try:
                return self._find(self._board_stops, origin, destination, start, end, max_transfers,
                                  min_transfer_minutes)
            except IntegrationError as error:
                log.warning("OpenBoards nicht nutzbar, suche im Soll-Fahrplan: %s", error)
        return self._find(self._plan_stops, origin, destination, start, end, max_transfers, min_transfer_minutes)

    def _find(self, stops: Stops, origin: Station, destination: Station, start: datetime.datetime,
              end: datetime.datetime, max_transfers: int, min_transfer_minutes: int) -> list[Journey]:
        """Gefundene Verbindungen, die frühestens um start abfahren und spätestens um end ankommen:
        je Abfahrt am Start und Zahl der Umstiege die früheste (siehe Modulbeschreibung)."""
        boards = {origin.eva: stops(origin.eva, start, end, (DEPARTURES,)),
                  destination.eva: stops(destination.eva, start, end, (ARRIVALS,))}
        stations = {origin.eva: origin, destination.eva: destination}
        transfer = datetime.timedelta(minutes=min_transfer_minutes)
        journeys = self._connect(boards, stations, origin, destination, start, end, 0, transfer)
        rounds = min(max_transfers, MAX_TRANSFERS)
        for index in range(rounds):
            if index and journeys:
                break   # mehr Umstiege nur, wenn es mit weniger keine Verbindung gibt
            # Bahnhöfe nur auf einer Seite lohnen sich erst für den nächsten Umstieg
            found = self._transfer_stations(origin, destination, boards, stations, STATIONS_PER_ROUND[index],
                                            linked_only=index == rounds - 1 or bool(journeys))
            for station in found:
                stations[station.eva] = station
                boards[station.eva] = stops(station.eva, start, end, (ARRIVALS, DEPARTURES))
            journeys = self._connect(boards, stations, origin, destination, start, end, index + 1, transfer)
        return journeys

    def _connect(self, boards: dict[str, list[_Stop]], stations: dict[str, Station], origin: Station,
                 destination: Station, start: datetime.datetime, end: datetime.datetime, max_transfers: int,
                 transfer: datetime.timedelta) -> list[Journey]:
        """Von jeder Abfahrt am Start: Runde 1 fährt mit diesem Zug zu allen abgefragten Bahnhöfen,
        jede weitere steigt dort in die Anschlüsse um. Je Bahnhof zählt nur die früheste Ankunft;
        das Ziel ergibt eine Verbindung, wenn es früher erreicht ist als mit weniger Umstiegen."""
        visits: dict[str, list[tuple[str, _Stop]]] = {}       # Fahrt → ihre Halte an den abgefragten Bahnhöfen
        for eva, board in boards.items():
            for stop in board:
                visits.setdefault(stop.trip, []).append((eva, stop))
        leaving = {eva: sorted((s for s in board if s.departure and s.departure <= end), key=lambda s: s.departure)
                   for eva, board in boards.items() if eva != destination.eva}
        times = {eva: [stop.departure for stop in board] for eva, board in leaving.items()}
        journeys = []
        for first in leaving.get(origin.eva, []):
            if first.departure < start:
                continue
            best: dict[str, datetime.datetime] = {}
            reached = _ride(first, origin.eva, (), visits, best, origin.eva, end)
            for transfers in range(max_transfers + 1):
                if destination.eva in reached:
                    journeys.append(Journey(tuple(self._connection(on, arrival, stations[at], stations[to])
                                                  for on, at, arrival, to in reached[destination.eva])))
                if transfers == max_transfers:
                    break
                onward: dict[str, tuple[_Ride, ...]] = {}
                for eva, rides in reached.items():
                    if eva == destination.eva:
                        continue
                    ready = rides[-1][2].arrival + transfer
                    used = {ride[0].trip for ride in rides}
                    for stop in leaving.get(eva, [])[bisect.bisect_left(times.get(eva, []), ready):]:
                        if stop.trip not in used:
                            onward.update(_ride(stop, eva, rides, visits, best, origin.eva, end))
                reached = onward
                if not reached:
                    break
        return journeys

    def _connection(self, departure: _Stop, arrival: _Stop, origin: Station, destination: Station) -> TrainConnection:
        return TrainConnection(arrival.train, arrival.long_distance, self._place(departure, origin),
                               self._place(arrival, destination), departure.departure, arrival.arrival,
                               departure.platform, arrival.arrival_platform,
                               departure.departure_scheduled, arrival.arrival_scheduled,
                               tuple(dict.fromkeys(departure.messages + arrival.messages)),
                               departure.realtime and arrival.realtime, _via(departure, arrival, destination))

    def _place(self, stop: _Stop, station: Station) -> Station:
        """Der Halt, an dem der Zug wirklich hält: Die Tafel von "Frankfurt Hbf (tief)" enthält auch
        die Züge oben im "Frankfurt(Main)Hbf" (gleicher Umsteigebereich)."""
        if stop.place_eva and stop.place_eva != station.eva and stop.place_eva in self._names:
            return Station(self._names[stop.place_eva], stop.place_eva)
        return station

    def _transfer_stations(self, origin: Station, destination: Station, boards: dict[str, list[_Stop]],
                           stations: dict[str, Station], count: int, linked_only: bool) -> list[Station]:
        """Bis zu count neue Umstiegsbahnhöfe (siehe Modulbeschreibung). Schlüssel sind EVA-Nummern
        (OpenBoards) bzw. Namen (Timetables), so wie sie im Laufweg stehen."""
        origin, destination = self._located(origin), self._located(destination)
        ends = {origin.eva, destination.eva}
        forward = self._reach(origin, boards, stations, DEPARTURES, ends)
        backward = self._reach(destination, boards, stations, ARRIVALS, ends)
        own = {"", *(key for station in stations.values() for key in (station.name, station.eva)),
               *(area for eva in stations for area in self._areas.get(eva, ()))}

        def near_route(key: str) -> bool:
            return _on_the_way(self.locate(key) if self.locate else None, origin, destination)

        def links(key: str) -> int:   # Paare aus einem Zug von der Start- und einem zur Zielseite
            return len(forward[key]) * len(backward[key]) - len(forward[key] & backward[key])

        linked = [key for key in forward if key in backward and key not in own and links(key) > 0 and near_route(key)]
        keys = sorted(linked, key=links, reverse=True)
        if not linked_only:   # sonst große Bahnhöfe auf einer Seite: Deren Tafeln verbinden in der nächsten Runde
            sides = [self._hubs({k: trips for k, trips in reach.items()
                                 if k not in other and k not in own and near_route(k)}, target)
                     for reach, other, target in ((forward, backward, destination), (backward, forward, origin))]
            keys += [key for pair in zip(*sides) for key in pair] + sides[0][len(sides[1]):] + sides[1][len(sides[0]):]
        found: list[Station] = []
        for key in keys[:count * MAX_LOOKUPS_PER_STATION]:   # Timetables: jeder unbekannte Name kostet eine Abfrage
            station = self._resolve(key)
            if station is not None and station.eva not in stations and station not in found:
                found.append(station)
            if len(found) >= count:
                break
        return found

    @staticmethod
    def _reach(end: Station, boards: dict[str, list[_Stop]], stations: dict[str, Station], kind: str,
               ends: set[str]) -> dict[str, set[str]]:
        """Bahnhof → Fahrten, die ihn von end aus erreichen (DEPARTURES: Laufweg nach der Abfahrt)
        bzw. von ihm nach end fahren (ARRIVALS: Laufweg vor der Ankunft) - auch über die schon
        abgefragten Umstiegsbahnhöfe, die so auf dieser Seite liegen."""
        reach: dict[str, set[str]] = {}
        transfers = {eva: station for eva, station in stations.items() if eva not in ends}
        todo = [end.eva]
        while todo:
            for stop in boards.get(todo.pop(0), ()):
                moment, path = ((stop.departure, stop.departure_path) if kind == DEPARTURES
                                else (stop.arrival, stop.arrival_path))
                if moment is not None:
                    for key in path:
                        reach.setdefault(key, set()).add(stop.trip)
            for eva, station in list(transfers.items()):
                if station.eva in reach or station.name in reach:
                    del transfers[eva]
                    todo.append(eva)   # liegt auf dieser Seite: auch seine Züge zählen
        return reach

    def _hubs(self, reach: dict[str, set[str]], target: Station) -> list[str]:
        """Bahnhöfe einer Seite, die größten zuerst und davon die näher am anderen Ende; ohne StaDa
        die, durch die die meisten Züge fahren."""
        def rank(key: str) -> tuple[int, float, int]:
            located = self.locate(key) if self.locate else None
            if located is None or located.lat is None:
                return UNKNOWN_CATEGORY + 1, math.inf, -len(reach[key])
            distance = _km(located, target) if target.lat is not None else math.inf
            return located.category or UNKNOWN_CATEGORY, distance, -len(reach[key])
        return sorted(reach, key=rank)

    def _located(self, station: Station) -> Station:
        """Mit Koordinaten aus StaDa, wenn die Suche sie noch nicht hat."""
        if station.lat is not None or self.locate is None:
            return station
        located = self.locate(station.eva)
        return replace(station, lat=located.lat, lon=located.lon, category=located.category) if located else station

    def _resolve(self, key: str) -> Station | None:
        """Bahnhof zu einem Schlüssel aus dem Laufweg; Name wie in den Tafeln, Lage aus StaDa."""
        located = self.locate(key) if self.locate else None
        if key in self._names:
            station = Station(self._names[key], key)
        elif located is not None:
            return located
        else:
            station = self._station_named(key)
            if station is None:
                return None
        return self._located(station) if located is None else replace(
            station, lat=located.lat, lon=located.lon, category=located.category)

    def _station_named(self, name: str) -> Station | None:
        """Bahnhof mit genau diesem Namen (wie im Laufweg); None, wenn die DB ihn nicht kennt."""
        if name not in self._stations:
            try:
                stations = self._search(name)
            except IntegrationError:
                stations = []
            exact = [s for s in stations if s.name == name]
            self._stations[name] = (exact or stations or [None])[0]
        return self._stations[name]

    # --- Timetables: Bahnhofssuche und Soll-Fahrplan ----------------------------------------
    def _search(self, name: str) -> list[Station]:
        root = self._get(f"/station/{urllib.parse.quote(name)}")
        return [Station(s.get("name", ""), s.get("eva", "")) for s in root.iter("station") if s.get("eva")]

    def _plan_stops(self, eva: str, start: datetime.datetime, end: datetime.datetime,
                    kinds: tuple[str, ...] = ()) -> list[_Stop]:
        """Alle Halte der Stundenpläne von start bis end (ein Plan enthält Ankünfte und Abfahrten)."""
        return [stop for hour in _hours(start, end) for stop in self._plan(eva, hour)]

    def _plan(self, eva: str, hour: datetime.datetime) -> list[_Stop]:
        key = (eva, f"{hour:%y%m%d/%H}")
        if key not in self._plans:   # jede Stunde nur einmal abfragen (Limit: 60 Abfragen pro Minute)
            if len(self._plans) >= MAX_CACHED_PLANS:
                self._plans.clear()
            self._plans[key] = [_stop(s) for s in self._get(f"/plan/{eva}/{key[1]}").iter("s")]
        return self._plans[key]

    def _get(self, path: str) -> ET.Element:
        text = self.http.get_text(BASE_URL + path, headers=self.headers)
        try:
            return ET.fromstring(text)
        except ET.ParseError:
            raise IntegrationError("Ungültige Antwort der DB-Timetables-API") from None

    # --- OpenBoards: Tafeln mit Echtzeit ---------------------------------------------------
    def _board_stops(self, eva: str, start: datetime.datetime, end: datetime.datetime,
                     kinds: tuple[str, ...]) -> list[_Stop]:
        """Halte aus den Tafeln von start bis end; Ankunft und Abfahrt desselben Zugs werden ein Halt."""
        events: dict[str, dict[str, _Event]] = {}
        for hour in _hours(start, end):
            for kind in kinds:
                for event in self._board(kind, eva, hour):
                    events.setdefault(event.trip, {})[kind] = event
        return [_board_stop(trip, by_kind.get(ARRIVALS), by_kind.get(DEPARTURES))
                for trip, by_kind in events.items()]

    def _board(self, kind: str, eva: str, hour: datetime.datetime) -> list[_Event]:
        key = (kind, eva, hour.isoformat())
        cached = self._boards.get(key)
        if cached is not None and self.clock() - cached[0] < BOARD_CACHE_S:
            return cached[1]
        if len(self._boards) >= MAX_CACHED_PLANS:
            self._boards.clear()
        body = {"stopPlaceOrStation": {"evaNumbers": [eva]},
                "timeWindow": {"timeStart": hour.isoformat(),
                               "timeEnd": (hour + datetime.timedelta(hours=1)).isoformat()},
                "transportTypes": list(TRANSPORT_TYPES), "maxViaStops": MAX_VIA_STOPS,
                "maxEntriesPerTransportType": MAX_ENTRIES, "noCancellations": True, "languages": ["deu"]}
        try:
            response = self.http.post_json(f"{BOARDS_URL}/{kind}", body, headers=self.board_headers)
        except IntegrationError as error:
            if " 404" not in str(error):   # 404: keine Halte in diesem Zeitfenster
                raise
            response = {}
        if not isinstance(response, dict):
            raise IntegrationError("Ungültige Antwort der DB-OpenBoards-API")
        events = self._parse_board(eva, kind, response)
        self._boards[key] = (self.clock(), events)
        return events

    def _parse_board(self, eva: str, kind: str, response: dict[str, Any]) -> list[_Event]:
        for place in response.get("stopPlaces") or []:
            name = _localized(place.get("localizedNames"), "name")
            if place.get("evaNumber") and name:
                self._names[place["evaNumber"]] = name
        considered = (response.get("meta") or {}).get("consideredStopPlaces") or []
        self._areas.setdefault(eva, set()).update(considered)
        truncated = (response.get("meta") or {}).get("truncatedTransportTypes")
        if truncated:
            log.debug("OpenBoards %s %s: nicht alle Züge geliefert (%s)", kind, eva, ", ".join(truncated))
        texts = _message_texts(response.get("messages") or {})
        events = []
        for item in response.get(kind) or []:
            try:
                event = _event(item, kind, texts)
            except (KeyError, TypeError, ValueError):
                log.debug("OpenBoards: Eintrag übersprungen: %r", item)
                continue
            if event is not None:
                events.append(event)
        return events


def _ride(boarding: _Stop, at: str, rides: tuple[_Ride, ...], visits: dict[str, list[tuple[str, _Stop]]],
          best: dict[str, datetime.datetime], origin: str, end: datetime.datetime) -> dict[str, tuple[_Ride, ...]]:
    """Mit dem Zug ab boarding (Bahnhof at) zu den abgefragten Bahnhöfen danach: die, an denen er
    früher ankommt als alles bisher (best wird aktualisiert), mit dem Weg dorthin."""
    improved = {}
    for eva, stop in visits[boarding.trip]:
        if eva in (at, origin) or stop.arrival is None:
            continue
        if boarding.departure < stop.arrival <= end and (eva not in best or stop.arrival < best[eva]):
            best[eva] = stop.arrival
            improved[eva] = rides + ((boarding, at, stop, eva),)
    return improved


def _on_the_way(station: Station | None, origin: Station, destination: Station) -> bool:
    """Liegt der Bahnhof ungefähr zwischen Start und Ziel? Ohne Koordinaten: ja."""
    if station is None or None in (station.lat, origin.lat, destination.lat):
        return True
    return (_km(origin, station) + _km(station, destination)
            <= MAX_DETOUR * _km(origin, destination) + DETOUR_SLACK_KM)


def _km(a: Station, b: Station) -> float:
    return distance_km(Place(a.name, a.lat, a.lon), Place(b.name, b.lat, b.lon))


def _via(departure: _Stop, arrival: _Stop, destination: Station) -> tuple[str, ...]:
    """Halte zwischen Abfahrt und Ankunft: der Laufweg nach der Abfahrt bis zum Ziel. Nur mit
    OpenBoards (EVA-Nummern in Fahrtrichtung); () wenn das Ziel nicht im Laufweg steht."""
    if not (departure.realtime and arrival.realtime):
        return ()
    path = departure.departure_path
    for target in (arrival.place_eva, destination.eva):
        if target and target in path:
            return path[:path.index(target)]
    return ()


def _is_rail_station(station: Station) -> bool:
    """Bahnhöfe in Deutschland haben EVA-Nummern 80xxxxx; die Suche findet auch Bushaltestellen."""
    return len(station.eva) == 7 and station.eva.startswith("80")


def _hours(start: datetime.datetime, end: datetime.datetime) -> Iterator[datetime.datetime]:
    hour = start.astimezone(TIMEZONE).replace(minute=0, second=0, microsecond=0)
    while hour <= end:
        yield hour
        hour += datetime.timedelta(hours=1)


def _delay(scheduled: datetime.datetime | None, actual: datetime.datetime) -> int:
    if scheduled is None:
        return 0
    return max(0, round((actual - scheduled).total_seconds() / 60))


# --- Timetables-XML ------------------------------------------------------------------------
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
        long_distance=category in LONG_DISTANCE,
        arrival=_time(arrival),
        arrival_path=_path(arrival),
        departure=_time(departure),
        departure_path=_path(departure),
        platform=(event.get("pp", "") if event is not None else ""),
        arrival_platform=(arrival.get("pp", "") if arrival is not None else ""),
    )


def _path(event: ET.Element | None) -> tuple[str, ...]:
    if event is None or not event.get("ppth"):
        return ()
    return tuple(event.get("ppth").split("|"))


def _time(event: ET.Element | None) -> datetime.datetime | None:
    if event is None or not event.get("pt"):
        return None
    return datetime.datetime.strptime(event.get("pt"), "%y%m%d%H%M").replace(tzinfo=TIMEZONE)


# --- OpenBoards-JSON -----------------------------------------------------------------------
def _event(item: dict[str, Any], kind: str, texts: dict[int, str]) -> _Event | None:
    """None für ausgefallene Halte und Fahrten."""
    info = item.get("journeyInfo") or {}
    if item.get("cancelled") or info.get("journeyCancelled"):
        return None
    transport = item["transport"]
    via = tuple(stop["evaNumber"] for stop in transport.get("via") or []
                if stop.get("evaNumber") and not stop.get("cancelled"))
    # Laufweg wie bei Timetables: Abfahrt → Halte danach bis zum Ziel, Ankunft → Halte ab dem Start
    end = info.get("destination" if kind == DEPARTURES else "origin") or {}
    end_eva = () if end.get("cancelled") or not end.get("evaNumber") else (end["evaNumber"],)
    path = via + end_eva if kind == DEPARTURES else end_eva + via
    category = transport.get("category", "")
    return _Event(
        trip=item["journeyId"],
        eva=item.get("evaNumber") or "",
        train=_train(transport),
        long_distance=transport.get("type") in LONG_DISTANCE_TYPES or category in LONG_DISTANCE,
        time=_iso(item["time"]),
        scheduled=_iso(item.get("timeSchedule") or item["time"]),
        platform=((item.get("platform") or item.get("platformSchedule") or {}).get("name") or ""),
        path=path,
        messages=tuple(text for i, text in texts.items() if i in set(item.get("messages") or [])),
    )


def _board_stop(trip: str, arrival: _Event | None, departure: _Event | None) -> _Stop:
    event = departure or arrival
    return _Stop(
        trip=trip,
        train=event.train,
        long_distance=event.long_distance,
        arrival=arrival.time if arrival else None,
        arrival_path=arrival.path if arrival else (),
        departure=departure.time if departure else None,
        departure_path=departure.path if departure else (),
        platform=event.platform,
        arrival_platform=arrival.platform if arrival else "",
        arrival_scheduled=arrival.scheduled if arrival else None,
        departure_scheduled=departure.scheduled if departure else None,
        messages=tuple(dict.fromkeys((arrival.messages if arrival else ())
                                     + (departure.messages if departure else ()))),
        realtime=True,
        place_eva=event.eva,
    )


def _train(transport: dict[str, Any]) -> str:
    """Bezeichnung für Reisende ("S9", "RE 10", "ICE 74"), sonst Linie bzw. Zugnummer."""
    if (transport.get("journeyDescription") or "").strip():
        return transport["journeyDescription"].strip()
    category = transport.get("category", "")
    line = ((transport.get("line") or {}).get("name") or "").strip()
    if line:
        return line if not category or line.startswith(category) else f"{category} {line}"
    return f"{category} {transport.get('journeyNumber', '')}".strip()


def _iso(text: str) -> datetime.datetime:
    moment = datetime.datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=TIMEZONE)
    return moment.astimezone(TIMEZONE)


def _message_texts(messages: dict[str, Any]) -> dict[int, str]:
    """messageID → deutscher Text, wichtigste zuerst: Störungen, Verspätungsgründe, Hinweise.
    Fahrtmerkmale ("attributes", z. B. Fahrradmitnahme) bleiben weg."""
    texts = {}
    for group in ("disruptions", "risCauseCodes", "notes"):
        for message in messages.get(group) or []:
            if message.get("code") in SKIPPED_CAUSE_CODES and group == "risCauseCodes":
                continue
            text = _localized(message.get("descriptions"), "textShort") or _localized(message.get("descriptions"), "text")
            if message.get("messageID") is not None and text:
                text = " ".join(text.split())
                texts[message["messageID"]] = (text if len(text) <= MAX_MESSAGE_CHARS
                                               else text[:MAX_MESSAGE_CHARS - 1].rsplit(" ", 1)[0] + " …")
    return texts


def _localized(entries: list[dict[str, Any]] | None, field: str) -> str:
    """Deutscher Eintrag, sonst der erste."""
    entries = entries or []
    for entry in sorted(entries, key=lambda e: e.get("language") != "deu"):
        if entry.get(field):
            return entry[field]
    return ""
