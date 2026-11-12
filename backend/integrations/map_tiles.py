"""Kartenkacheln von OpenStreetMap für die Routenkarte (backend/assistant/skills/travel/view.py).

Das iframe ist abgeschottet und lädt nichts aus dem Netz. Deshalb holt das Backend die Kacheln
und bettet sie als data:-URI ins HTML ein. Nutzungsregeln der OSM-Kacheln
(https://operations.osmfoundation.org/policies/tiles/): eigener User-Agent, Zwischenspeicher
(CACHE_S, im App-Datenordner), keine Massenabrufe (eine Karte braucht höchstens etwa 12 Kacheln),
Namensnennung unter der Karte (ATTRIBUTION).

Ohne Netz zeigt die Ansicht die Route ohne Karte darunter: Nach einem Fehler wird OFFLINE_S lang
nichts mehr abgerufen, gespeicherte Kacheln gelten weiter.
"""
from __future__ import annotations

import base64
import logging
import math
import threading
import time
from collections.abc import Callable
from pathlib import Path

from backend.integrations.http import Http, IntegrationError

log = logging.getLogger(__name__)

TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
TILE_SIZE = 256
MAX_ZOOM = 17
CACHE_S = 14 * 24 * 3600      # OSM verlangt mindestens 7 Tage
OFFLINE_S = 300               # nach einem Fehler so lange ohne Karte
USER_AGENT = "PersonalDigitalAgent/1.0 (Reise-Assistent; Studienprojekt)"
ATTRIBUTION = "Karte © OpenStreetMap-Mitwirkende"
MAX_LATITUDE = 85.0511        # Grenze der Web-Mercator-Projektion


def pixel(lon: float, lat: float, zoom: int) -> tuple[float, float]:
    """Position in der Weltkarte der Zoomstufe (Web Mercator), in Pixeln."""
    size = TILE_SIZE * 2 ** zoom
    lat = math.radians(max(-MAX_LATITUDE, min(MAX_LATITUDE, lat)))
    x = (lon + 180.0) / 360.0 * size
    y = (1.0 - math.log(math.tan(lat) + 1.0 / math.cos(lat)) / math.pi) / 2.0 * size
    return x, y


class MapTiles:
    def __init__(self, http: Http, cache_dir: Path, clock: Callable[[], float] = time.time):
        self.http = http
        self.cache_dir = Path(cache_dir)
        self.clock = clock
        self._offline_until = 0.0
        self._lock = threading.Lock()

    def data_uri(self, zoom: int, x: int, y: int) -> str:
        """Kachel als data:-URI. IntegrationError, wenn sie weder gespeichert noch abrufbar ist."""
        return "data:image/png;base64," + base64.b64encode(self._tile(zoom, x, y)).decode("ascii")

    def _tile(self, zoom: int, x: int, y: int) -> bytes:
        path = self.cache_dir / str(zoom) / str(x) / f"{y}.png"
        cached = _read(path)
        now = self.clock()
        if cached is not None and now - path.stat().st_mtime < CACHE_S:
            return cached
        with self._lock:
            offline = now < self._offline_until
        if offline:
            if cached is not None:
                return cached
            raise IntegrationError("Kartenkacheln gerade nicht erreichbar")
        try:
            data = self.http.get_bytes(TILE_URL.format(z=zoom, x=x, y=y), headers={"User-Agent": USER_AGENT})
        except IntegrationError as error:
            with self._lock:
                self._offline_until = now + OFFLINE_S
            if cached is not None:
                return cached
            log.info("Keine Kartenkacheln: %s", error)
            raise
        if not data.startswith(b"\x89PNG"):
            raise IntegrationError("Keine Kartenkachel (PNG) erhalten")
        _write(path, data)
        return data


def _read(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def _write(path: Path, data: bytes) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f".{threading.get_ident()}.tmp")
        temporary.write_bytes(data)
        temporary.replace(path)
    except OSError as error:   # dann eben ohne Zwischenspeicher
        log.warning("Kartenkachel nicht gespeichert: %s", error)
