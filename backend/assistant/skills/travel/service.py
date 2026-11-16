"""TravelService: holt Termine, Orte, Routen, Züge, Wetter und Spritpreise und lässt planner.py bewerten.

Bahn/ÖPNV, von Tür zu Tür mit Bus und Tram - der Reihe nach, bis eine Auskunft eine Verbindung hat:
  1. VVS (vvs.py), wenn Start und Ziel im VVS-Gebiet liegen: mit Echtzeit und echtem Preis
  2. Transitous (transitous.py), deutschlandweit
  3. DB-Tafeln (db_timetables.py): nur Züge, ab den nächsten Bahnhöfen
Fällt eine Auskunft aus, steht das in den Hinweisen.

Fällt ein Dienst aus oder fehlt sein Key, fehlt nur das betroffene Verkehrsmittel (bzw. das
Wetter); der Grund steht in TripPlan.notes. Nur ohne openrouteservice geht gar nichts (Adressen).
"""
from __future__ import annotations

import datetime
import logging
from collections.abc import Callable
from dataclasses import dataclass, replace

from backend.assistant.skills.travel import planner
from backend.assistant.settings import TRAVEL_KEY
from backend.assistant.skills.travel.planner import HOME_ADDRESS, Option, TravelSettings, TripPlan
from backend.integrations import openrouteservice as ors
from backend.integrations.db_stations import DbStations
from backend.integrations.db_timetables import MAX_TRANSFERS, DbTimetables, Journey, Station
from backend.integrations.geo import Place, distance_km
from backend.integrations.google_calendar import CalendarEvent, GoogleCalendar
from backend.integrations.http import IntegrationError
from backend.integrations.map_tiles import MapTiles
from backend.integrations.openrouteservice import OpenRouteService
from backend.integrations.tankerkoenig import Tankerkoenig
from backend.integrations.transitous import Transitous
from backend.integrations.vvs import Vvs
from backend.integrations.weather import OpenMeteo, Weather
from backend.preferences import PreferenceStore

log = logging.getLogger(__name__)

LOOKAHEAD_DAYS = 7          # so weit im Voraus sucht der Assistent den nächsten Termin
RAIL_DETOUR_FACTOR = 1.2    # Gleisweg ≈ Luftlinie × Faktor (für die Preisschätzung)
WEATHER_BEFORE = datetime.timedelta(minutes=30)   # Wetter für Ankunft minus so viel (≈ unterwegs)
MAJOR_STATION_CATEGORY = 2  # zweiter Versuch ab Bahnhöfen der StaDa-Kategorie 1-2 (z. B. Heidelberg Hbf)
HOME_ROUNDING_S = 15 * 60   # Heimweg nach Terminende: Abfahrt "jetzt" auf 15 Min. gerundet (Cache)
TRANSIT_MIN_WALK_MINUTES = 15   # Transitous: so lange darf der Fußweg zur ersten Haltestelle mindestens sein
_TRANSFER_TEXT = {0: "Direktverbindung", 1: "Verbindung mit höchstens einem Umstieg",
                  2: "Verbindung mit höchstens zwei Umstiegen", 3: "Verbindung mit höchstens drei Umstiegen"}


class TravelSetupError(IntegrationError):
    """Etwas muss erst eingerichtet werden (Key, Heimatadresse, Kalender)."""


class PlaceNotFound(IntegrationError):
    """Ein Ort (oft eine Raumangabe aus dem Kalender) lässt sich keiner Adresse zuordnen."""

    def __init__(self, place: str):
        super().__init__(f"Ort nicht gefunden: {place!r} - eine Adresse dafür lässt sich als Ortskürzel "
                         "speichern (⚙ Einstellungen → Reise → Allgemein)")
        self.place = place


class HomeAddressMissing(TravelSetupError):
    def __init__(self):
        super().__init__("Ich kenne deine Heimatadresse noch nicht.")


@dataclass(frozen=True)
class Trip:
    """Weg zu einem Termin aus dem Kalender - oder nach dem letzten Termin nach Hause."""
    event: CalendarEvent        # Ziel; beim Heimweg der letzte Termin des Tages
    origin_source: str          # "home" oder Titel des vorigen Termins
    plan: TripPlan
    home: bool = False          # Heimweg
    planned_at: datetime.datetime | None = None   # wann der Plan gerechnet wurde (Erinnerung: aktuell genug?)

    @property
    def title(self) -> str:
        return f"Heimweg von „{self.event.title}“" if self.home else f"Weg zu „{self.event.title}“"


class TravelService:
    def __init__(self, ors_client: OpenRouteService | None, preferences: PreferenceStore,
                 calendar: GoogleCalendar | None = None, rail: DbTimetables | None = None,
                 fuel: Tankerkoenig | None = None, weather: OpenMeteo | None = None,
                 clock: Callable[[], datetime.datetime] = lambda: datetime.datetime.now().astimezone(),
                 stations: DbStations | None = None, tiles: MapTiles | None = None,
                 transit: Transitous | None = None, vvs: Vvs | None = None):
        self.ors = ors_client
        self.preferences = preferences
        self.calendar = calendar
        self.rail = rail
        self.fuel = fuel
        self.weather = weather
        self.clock = clock
        self.stations = stations       # Bahnhof zur Adresse; ohne: Suche nach dem Ortsnamen (Timetables)
        self.tiles = tiles             # Kartenkacheln für die Ansicht (view.trip_view)
        self.transit = transit         # Verbindungssuche Bahn/ÖPNV; ohne: nur die DB-Tafeln
        self.vvs = vvs                 # Verbindungssuche im VVS-Gebiet (vor Transitous)
        self._trips: dict[tuple, Trip] = {}

    def settings(self) -> TravelSettings:
        return TravelSettings.from_preferences(self.preferences)

    # --- Kalender ------------------------------------------------------------------------
    def next_trip(self, interactive: bool = True, fresh_after: datetime.timedelta | None = None) -> Trip | None:
        """Weg zum nächsten Termin mit Ort. Start: Ort des vorigen Termins am selben Tag, sonst daheim.
        Steht heute kein Termin mit Ort mehr an, aber einer hat schon begonnen: der Heimweg von dort
        (bis home_trip_hours nach dessen Ende). Der Plan wird je Termin, Startort und Bearbeitungs-
        stand nur einmal berechnet (die Erinnerung fragt alle paar Minuten) - mit fresh_after neu, wenn
        der Plan älter ist (die Erinnerung kurz vor der Abfahrt: aktuelle Verspätungen)."""
        self._ors()   # ohne Routen erst gar nicht den Kalender (und dessen Anmeldung) bemühen
        now = self.clock()
        settings = self.settings()
        events = [event for event in self._events(now, interactive) if event.location]
        target = next((event for event in events if event.start > now), None)
        if settings.home_trip and (target is None or target.start.date() != now.date()):
            started = [event for event in events if event.start <= now and event.start.date() == now.date()]
            last = max(started, key=lambda event: event.end, default=None)
            if last is not None and now < last.end + datetime.timedelta(hours=settings.home_trip_hours):
                return self._home_trip(last, now, fresh_after)
        if target is None:
            return None
        previous = [event for event in events if event.end <= target.start
                    and event.start.date() == target.start.date() and event.id != target.id]
        if previous:
            origin, source = previous[-1].location, previous[-1].title
        else:
            origin, source = self.home_address(), "home"
        key = (target.id, target.updated, target.start, target.location, origin)
        if self._stale(key, now, fresh_after):
            self._trips = {key: Trip(target, source, self.plan(origin, target.location, target.start), planned_at=now)}
        return self._trips[key]

    def _stale(self, key: tuple, now: datetime.datetime, fresh_after: datetime.timedelta | None) -> bool:
        """Neu rechnen: noch nicht gerechnet - oder (fresh_after) älter als das."""
        trip = self._trips.get(key)
        return trip is None or (fresh_after is not None and (trip.planned_at is None or now - trip.planned_at > fresh_after))

    def _home_trip(self, last: CalendarEvent, now: datetime.datetime,
                   fresh_after: datetime.timedelta | None = None) -> Trip | None:
        home = self.home_address()
        if last.location.strip().casefold() == home.strip().casefold():
            return None   # der letzte Termin ist zu Hause
        depart = last.end if now <= last.end else _rounded(now)
        key = ("home", last.id, last.updated, depart, last.location, home)
        if self._stale(key, now, fresh_after):
            self._trips = {key: Trip(last, last.title, self.plan(last.location, home, depart_after=depart), home=True,
                                     planned_at=now)}
        return self._trips[key]

    def _events(self, now: datetime.datetime, interactive: bool = True) -> list[CalendarEvent]:
        if self.calendar is None:
            raise TravelSetupError("Google Calendar ist nicht eingerichtet (siehe README).")
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return self.calendar.events(day_start, now + datetime.timedelta(days=LOOKAHEAD_DAYS), interactive=interactive)

    def home_address(self) -> str:
        address = self.preferences.get(HOME_ADDRESS)
        if not address:
            raise HomeAddressMissing()
        return address

    def set_home_address(self, address: str) -> Place:
        """Adresse prüfen (muss sich finden lassen) und speichern."""
        place = self._ors().geocode(address)
        self.preferences.set(HOME_ADDRESS, address)
        return place

    # --- Planung -------------------------------------------------------------------------
    def plan(self, origin: str, destination: str, arrive_by: datetime.datetime | None = None,
             depart_after: datetime.datetime | None = None) -> TripPlan:
        """Bis arrive_by ankommen - oder (Heimweg) ab depart_after losfahren. Genau eins von beiden."""
        if (arrive_by is None) == (depart_after is None):
            raise ValueError("Entweder Ankunfts- oder Abfahrtszeit angeben")
        client = self._ors()
        settings = self.settings()
        start, end = self._place(client, origin, settings), self._place(client, destination, settings)
        options: list[Option] = []
        notes: list[str] = []
        air_km = distance_km(start, end)
        when = {"arrive_by": arrive_by, "depart_after": depart_after}

        modes = set(settings.modes) & set(planner.LABELS) or set(planner.LABELS)   # nichts gewählt: alle
        car = None
        if modes & {planner.CAR, planner.TAXI}:
            car = self._try(notes, "Auto/Taxi", lambda: client.route(ors.CAR, start, end))
        if car is not None:
            if planner.CAR in modes:
                price, estimated = self._fuel_price(start, settings, notes)
                options.append(planner.car_option(car, price, estimated, settings, **when))
            if planner.TAXI in modes:
                options.append(planner.taxi_option(car, settings, **when))
        if planner.BIKE in modes and air_km <= settings.max_bike_km:
            bike = self._try(notes, "Fahrrad", lambda: client.route(ors.BIKE, start, end))
            if bike is not None:
                options.append(planner.bike_option(bike, settings, **when))
        if planner.FOOT in modes and air_km <= settings.max_walk_km:
            walk = self._try(notes, "Zu Fuß", lambda: client.route(ors.FOOT, start, end))
            if walk is not None:
                options.append(planner.walk_option(walk, settings, **when))
        if planner.TRAIN in modes:
            train = self._public_transport(client, start, end, arrive_by, depart_after, settings, notes)
            if train is not None:
                options.append(train)
        moment = depart_after or arrive_by - WEATHER_BEFORE
        weather = self._weather(start, moment, settings, notes)
        options = planner.apply_weather(options, weather, settings)
        return TripPlan(start, end, arrive_by, planner.rank(options, settings, arrive_by), settings, tuple(notes),
                        weather, depart_after)

    def _public_transport(self, client: OpenRouteService, start: Place, end: Place,
                          arrive_by: datetime.datetime | None, depart_after: datetime.datetime | None,
                          settings: TravelSettings, notes: list[str]) -> Option | None:
        """VVS (im VVS-Gebiet), dann Transitous, dann die DB-Tafeln (siehe Modulbeschreibung)."""
        sources = [("VVS", self.vvs)] if self.vvs is not None and self.vvs.covers(start, end) else []
        sources += [("Transitous", self.transit)] if self.transit is not None else []
        for name, source in sources:
            journey = self._try(notes, f"ÖPNV ({name})",
                                lambda: self._transit_journey(source, start, end, arrive_by, depart_after, settings))
            if journey is not None:
                return planner.transit_option(journey, settings)
            log.info("%s ohne Verbindung, frage die nächste Auskunft", name)
        if self.rail is None:
            if not sources:
                notes.append("Bahn: DB-API nicht eingerichtet (PDA_DB_CLIENT_ID, PDA_DB_API_KEY).")
            else:
                kind = _TRANSFER_TEXT[max(0, min(settings.train_transfers, MAX_TRANSFERS))]
                notes.append(f"ÖPNV: keine {kind} in den nächsten Stunden gefunden.")
            return None
        return self._try(notes, "Bahn", lambda: self._train(client, start, end, arrive_by, depart_after,
                                                            settings, notes))

    def _transit_journey(self, source: Transitous | Vvs, start: Place, end: Place,
                         arrive_by: datetime.datetime | None, depart_after: datetime.datetime | None,
                         settings: TravelSettings):
        search = {"max_transfers": max(0, settings.train_transfers),
                  "min_transfer_minutes": settings.transfer_minutes,
                  "max_walk_minutes": max(TRANSIT_MIN_WALK_MINUTES, settings.station_walk_minutes)}
        if depart_after is not None:
            return source.earliest_journey(start, end, depart_after, **search)
        latest_arrival = arrive_by - datetime.timedelta(minutes=settings.buffer_minutes)
        journey = source.latest_journey(start, end, latest_arrival, **search, not_before=self.clock())
        if journey is None:   # rechtzeitig fährt nichts mehr: die nächste ab jetzt (die Ansicht sagt "zu spät")
            journey = source.earliest_journey(start, end, self.clock(), **search)
        return journey

    def _train(self, client: OpenRouteService, start: Place, end: Place, arrive_by: datetime.datetime | None,
               depart_after: datetime.datetime | None, settings: TravelSettings, notes: list[str]) -> Option | None:
        """Erst ab den nächsten Bahnhöfen; findet die Suche dort nichts (an kleinen Bahnhöfen fahren
        wenige Züge, die Suche kennt nur die Laufwege), noch einmal ab den nächsten großen."""
        origins, destinations = self._stations_near(client, start), self._stations_near(client, end)
        pairs = list(dict.fromkeys([(origins[0], destinations[0]), (origins[-1], destinations[-1])]))
        searched = []
        for origin, destination in pairs:
            if origin.eva == destination.eva:
                continue
            option = self._train_between(client, start, end, origin, destination, arrive_by, depart_after,
                                         settings, notes)
            if option is not None:
                return option
            searched.append(f"{origin.name} → {destination.name}")
        if not searched:
            notes.append(f"Bahn: Start und Ziel liegen am selben Bahnhof ({origins[0].name}).")
        else:
            kind = _TRANSFER_TEXT[max(0, min(settings.train_transfers, MAX_TRANSFERS))]
            notes.append(f"Bahn: keine {kind} {' oder '.join(searched)} in den nächsten Stunden gefunden.")
        return None

    def _train_between(self, client: OpenRouteService, start: Place, end: Place, origin: Station, destination: Station,
                       arrive_by: datetime.datetime | None, depart_after: datetime.datetime | None,
                       settings: TravelSettings, notes: list[str]) -> Option | None:
        origin_place, destination_place = self._station_place(client, origin), self._station_place(client, destination)
        access = self._leg(client, start, origin_place, settings)
        egress = self._leg(client, destination_place, end, settings)
        search = {"max_transfers": settings.train_transfers, "min_transfer_minutes": settings.transfer_minutes}
        if depart_after is not None:
            at_station = depart_after + datetime.timedelta(seconds=access.duration_s)
            connection: Journey | None = self.rail.earliest_journey(origin, destination, at_station, **search)
        else:
            latest_arrival = arrive_by - datetime.timedelta(minutes=settings.buffer_minutes, seconds=egress.duration_s)
            not_before = self.clock() + datetime.timedelta(seconds=access.duration_s)   # nicht in der Vergangenheit
            connection = self.rail.latest_journey(origin, destination, latest_arrival, **search, not_before=not_before)
        if connection is None:
            return None
        if not connection.realtime:
            notes.append("Bahn: ohne Echtzeit (DB OpenBoards nicht erreichbar oder nicht abonniert) - "
                         "Zeiten aus dem Soll-Fahrplan, Verspätungen fehlen.")
        rail_km = distance_km(origin_place, destination_place) * RAIL_DETOUR_FACTOR
        option = planner.train_option(connection, access, egress, rail_km, settings)
        segments = self._train_segments(start, end, connection, access, egress)
        if not segments:
            return option
        line = [point for segment in segments for point in segment.points]
        line = tuple(point for i, point in enumerate(line) if i == 0 or point != line[i - 1])
        return replace(option, geometry=line, segments=segments)

    def _train_segments(self, start: Place, end: Place, connection: Journey, access: planner.Leg,
                        egress: planner.Leg) -> tuple[planner.Segment, ...]:
        """Für die Karte: Weg zum Bahnhof, jeder Zug über seine Zwischenhalte, Weg zum Ziel - als
        (Länge, Breite). () ohne Koordinaten der Bahnhöfe (dann zeigt die Karte die Luftlinie)."""
        if self.stations is None:
            return ()
        trains = []
        for leg in connection.legs:
            points = []
            for eva in (leg.origin.eva, *leg.via, leg.destination.eva):
                point = self.stations.coordinates(eva)
                if point is None and eva in (leg.origin.eva, leg.destination.eva):
                    return ()   # ohne Umstiegs- oder Endbahnhof wäre die Linie falsch
                if point is not None:
                    points.append(point)
            trains.append(planner.Segment(planner.RAIL, tuple(points),
                                          f"{leg.train}: {leg.origin.name} → {leg.destination.name}",
                                          leg.destination.name))
        first, last = trains[0].points[0], trains[-1].points[-1]
        to_station = planner.Segment(access.kind, access.geometry or ((start.lon, start.lat), first),
                                     f"{access.description} zu {connection.origin.name}", connection.origin.name)
        to_end = planner.Segment(egress.kind, egress.geometry or (last, (end.lon, end.lat)),
                                 f"{egress.description} zum Ziel")
        return (to_station, *trains, to_end)

    def _stations_near(self, client: OpenRouteService, place: Place) -> list[Station]:
        """[nächster Bahnhof, nächster großer Bahnhof] aus der StaDa-Liste (beide mit Koordinaten,
        oft derselbe) - ohne StaDa der Bahnhof zum Ortsnamen."""
        if self.stations is not None:
            try:
                nearest = self.stations.nearest(place)
                try:
                    major = self.stations.nearest(place, max_category=MAJOR_STATION_CATEGORY)
                except IntegrationError:   # kein großer Bahnhof in der Nähe
                    major = nearest
                return list(dict.fromkeys([nearest, major]))
            except IntegrationError as error:
                log.warning("Bahnhof über StaDa nicht gefunden, suche über den Ortsnamen: %s", error)
        return [self.rail.find_station(client.locality(place))]

    @staticmethod
    def _station_place(client: OpenRouteService, station: Station) -> Place:
        if station.lat is not None and station.lon is not None:
            return Place(station.name, station.lat, station.lon)
        return client.geocode(station.name)

    def _leg(self, client: OpenRouteService, start: Place, end: Place, settings: TravelSettings) -> planner.Leg:
        walk = client.route(ors.FOOT, start, end)
        car = client.route(ors.CAR, start, end) if walk.duration_s > settings.station_walk_minutes * 60 else None
        return planner.walk_or_transit_leg(walk, car, settings)

    def _weather(self, place: Place, moment: datetime.datetime, settings: TravelSettings,
                 notes: list[str]) -> Weather | None:
        if not settings.weather or self.weather is None:
            return None
        return self._try(notes, "Wetter", lambda: self.weather.at(place, moment))

    def _fuel_price(self, place: Place, settings: TravelSettings, notes: list[str]) -> tuple[float, bool]:
        if self.fuel is not None:
            price = self._try(notes, "Spritpreis", lambda: self.fuel.price(place, settings.fuel))
            if price is not None:
                return price, False
        return settings.fuel_price, True

    def _place(self, client: OpenRouteService, text: str, settings: TravelSettings) -> Place:
        """Adresse (oder Ort aus dem Kalender mit Ortskürzel) → Koordinaten."""
        address = planner.resolve_place(text, settings)
        try:
            return client.geocode(address)
        except IntegrationError as error:
            if "nicht gefunden" not in str(error):
                raise
            raise PlaceNotFound(text) from None

    def set_place_alias(self, key: str, address: str) -> Place:
        """Ortskürzel speichern (Adresse muss sich finden lassen), z. B. "LE1" → "Lerchenstraße 1, Stuttgart"."""
        place = self._ors().geocode(address)
        stored = self.preferences.get(TRAVEL_KEY)
        stored = dict(stored) if isinstance(stored, dict) else {}
        stored["places"] = planner.with_place_alias(self.settings().places, key.strip(), address.strip())
        self.preferences.set(TRAVEL_KEY, stored)
        return place

    def _ors(self) -> OpenRouteService:
        if self.ors is None:
            raise TravelSetupError("openrouteservice ist nicht eingerichtet: Key fehlt (PDA_ORS_KEY, siehe README).")
        return self.ors

    @staticmethod
    def _try(notes: list[str], what: str, action: Callable):
        try:
            return action()
        except IntegrationError as error:
            log.warning("%s: %s", what, error)
            notes.append(f"{what}: {error}")
            return None


def _rounded(moment: datetime.datetime) -> datetime.datetime:
    """Auf die nächsten HOME_ROUNDING_S aufgerundet - so bleibt der Heimweg-Plan eine Weile gültig."""
    seconds = -moment.timestamp() % HOME_ROUNDING_S
    return (moment + datetime.timedelta(seconds=seconds)).replace(microsecond=0)
