"""DB StaDa (Station Data): alle Bahnhöfe mit EVA-Nummer, Koordinaten und Größe - daraus der
Bahnhof zu einer Adresse.

Kostenlos: https://developers.deutschebahn.com → "StaDa - Station Data" abonnieren (dieselbe
Anwendung und dieselben Keys wie OpenBoards). Laut Nutzungsbedingungen höchstens einmal am Tag
abrufen: Die Liste (≈ 5400 Bahnhöfe, Download ≈ 9 MB) wird in config.DB_STATIONS_FILE gespeichert
und nur alle REFRESH_S erneuert. Ist StaDa nicht erreichbar, gilt die gespeicherte Liste weiter;
ohne Liste sucht der Reise-Assistent den Bahnhof wie früher über den Ortsnamen (Timetables).

Welcher Bahnhof: der mit der kleinsten "gefühlten" Entfernung = Luftlinie + Aufschlag je nach
Kategorie (1 = großer Hauptbahnhof … 7 = kleiner Halt, CATEGORY_PENALTY_KM). Ein Hauptbahnhof 2 km
entfernt gewinnt so gegen einen S-Bahn-Halt in 500 m: Dort halten mehr Züge, und die Suche braucht
seltener einen Umstieg.

lookup() liefert der Verbindungssuche (db_timetables.py) Lage und Kategorie möglicher Umstiegsbahnhöfe.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.integrations.db_timetables import Station
from backend.integrations.geo import Place, distance_km
from backend.integrations.http import Http, IntegrationError

log = logging.getLogger(__name__)

URL = "https://apis.deutschebahn.com/db-api-marketplace/apis/station-data/v2/stations"
PAGE_SIZE = 10000                       # Höchstwert der API; heute reicht eine Seite
REFRESH_S = 7 * 24 * 3600               # Bahnhöfe ändern sich selten (erlaubt: einmal am Tag)
RETRY_S = 3600                          # nach einem Fehler frühestens wieder
MAX_DISTANCE_KM = 25                    # weiter weg: kein Bahnhof "in der Nähe"
CATEGORY_PENALTY_KM = {1: 0.0, 2: 0.5, 3: 1.0, 4: 2.0, 5: 2.5, 6: 3.5, 7: 4.0}
UNKNOWN_CATEGORY = 7


@dataclass(frozen=True)
class _Entry:
    eva: str
    name: str
    lat: float
    lon: float
    category: int


class DbStations:
    def __init__(self, http: Http, client_id: str, api_key: str, cache_file: Path,
                 clock: Callable[[], float] = time.time):
        self.http = http
        self.headers = {"DB-Client-Id": client_id, "DB-Api-Key": api_key, "Accept": "application/json"}
        self.cache_file = Path(cache_file)
        self.clock = clock
        self._entries: list[_Entry] | None = None
        self._by_eva: dict[str, _Entry] = {}
        self._by_name: dict[str, _Entry] = {}
        self._fetched_at = 0.0
        self._last_attempt: float | None = None
        self._lock = threading.Lock()    # Erinnerung (Hintergrund) und Chat können gleichzeitig planen

    def nearest(self, place: Place, max_category: int | None = None) -> Station:
        """Bahnhof für eine Adresse (siehe Modulbeschreibung), mit max_category nur so große
        (2: Kategorie 1 und 2). IntegrationError ohne Liste oder ohne Bahnhof im Umkreis von MAX_DISTANCE_KM."""
        scored = []
        for entry in self._list():
            if max_category is not None and entry.category > max_category:
                continue
            km = distance_km(place, Place(entry.name, entry.lat, entry.lon))
            if km <= MAX_DISTANCE_KM:
                scored.append((km + CATEGORY_PENALTY_KM.get(entry.category, CATEGORY_PENALTY_KM[UNKNOWN_CATEGORY]),
                               km, entry))
        if not scored:
            raise IntegrationError(f"Kein Bahnhof im Umkreis von {MAX_DISTANCE_KM} km um {place.label!r}")
        return _station(min(scored, key=lambda item: (item[0], item[1]))[2])

    def lookup(self, key: str) -> Station | None:
        """Bahnhof zu EVA-Nummer oder genauem Namen, mit Koordinaten und Kategorie; None, wenn
        unbekannt (wie coordinates)."""
        try:
            self._list()
        except IntegrationError:
            return None
        entry = self._by_eva.get(key) or self._by_name.get(key)
        return _station(entry) if entry else None

    def coordinates(self, eva: str) -> tuple[float, float] | None:
        """(Länge, Breite) eines Bahnhofs, z. B. für die Zwischenhalte auf der Karte; None, wenn unbekannt."""
        try:
            self._list()
        except IntegrationError:
            return None
        entry = self._by_eva.get(eva)
        return (entry.lon, entry.lat) if entry else None

    # --- Liste: Datei, sonst Download ------------------------------------------------------
    def _list(self) -> list[_Entry]:
        with self._lock:
            if self._entries is None:
                self._entries, self._fetched_at = self._read_cache()
            now = self.clock()
            stale = not self._entries or now - self._fetched_at > REFRESH_S
            may_try = self._last_attempt is None or now - self._last_attempt > RETRY_S
            if stale and may_try:
                self._last_attempt = now
                try:
                    self._entries, self._fetched_at = self._download(), now
                    self._write_cache()
                except IntegrationError as error:
                    if not self._entries:
                        raise
                    log.warning("StaDa nicht erreichbar, nehme die gespeicherte Bahnhofsliste: %s", error)
            if not self._entries:
                raise IntegrationError("Bahnhofsliste (DB StaDa) nicht verfügbar")
            if len(self._by_eva) != len(self._entries):
                self._by_eva = {entry.eva: entry for entry in self._entries}
                self._by_name = {entry.name: entry for entry in self._entries}
            return self._entries

    def _download(self) -> list[_Entry]:
        stations: list[dict[str, Any]] = []
        while True:
            data = self.http.get_json(URL, {"offset": len(stations), "limit": PAGE_SIZE}, headers=self.headers)
            page = data.get("result") if isinstance(data, dict) else None
            if not isinstance(page, list):
                raise IntegrationError("Ungültige Antwort der DB-StaDa-API")
            stations += page
            if not page or len(stations) >= int(data.get("total") or 0):
                break
        entries = [entry for entry in map(_entry, stations) if entry is not None]
        if not entries:
            raise IntegrationError("DB StaDa liefert keine Bahnhöfe")
        log.info("StaDa: %d Bahnhöfe geladen", len(entries))
        return entries

    def _read_cache(self) -> tuple[list[_Entry] | None, float]:
        try:
            data = json.loads(self.cache_file.read_text(encoding="utf-8"))
            return [_Entry(*row) for row in data["stations"]], float(data["fetched_at"])
        except FileNotFoundError:
            return None, 0.0
        except (OSError, ValueError, KeyError, TypeError) as error:
            log.warning("Bahnhofsliste %s unlesbar, lade neu: %s", self.cache_file, error)
            return None, 0.0

    def _write_cache(self) -> None:
        rows = [[e.eva, e.name, e.lat, e.lon, e.category] for e in self._entries]
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.cache_file.with_suffix(".tmp")
            temporary.write_text(json.dumps({"fetched_at": self._fetched_at, "stations": rows}, ensure_ascii=False),
                                 encoding="utf-8")
            temporary.replace(self.cache_file)
        except OSError as error:   # dann eben nur im Speicher
            log.warning("Bahnhofsliste nicht gespeichert: %s", error)


def _station(entry: _Entry) -> Station:
    return Station(entry.name, entry.eva, entry.lat, entry.lon, entry.category)


def _entry(station: dict[str, Any]) -> _Entry | None:
    """Haupt-EVA-Nummer mit Koordinaten; None, wenn sie fehlt."""
    numbers = [n for n in station.get("evaNumbers") or [] if (n.get("geographicCoordinates") or {}).get("coordinates")]
    if not numbers or not station.get("name"):
        return None
    main = next((n for n in numbers if n.get("isMain")), numbers[0])
    lon, lat = main["geographicCoordinates"]["coordinates"][:2]
    category = station.get("category")
    return _Entry(str(main["number"]), station["name"], float(lat), float(lon),
                  category if isinstance(category, int) else UNKNOWN_CATEGORY)
