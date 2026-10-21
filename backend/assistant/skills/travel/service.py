"""TravelService: holt Termine, Orte, Routen, Züge und Spritpreise und lässt planner.py bewerten.

Fällt ein Dienst aus oder fehlt sein Key, fehlt nur das betroffene Verkehrsmittel; der
Grund steht in TripPlan.notes. Nur ohne openrouteservice geht gar nichts (Adressen).
"""
from __future__ import annotations

import datetime
import logging
from collections.abc import Callable
from dataclasses import dataclass

from backend.assistant.skills.travel import planner
from backend.assistant.skills.travel.planner import HOME_ADDRESS, Option, TravelSettings, TripPlan
from backend.integrations import openrouteservice as ors
from backend.integrations.db_timetables import DbTimetables
from backend.integrations.geo import Place, distance_km
from backend.integrations.google_calendar import CalendarEvent, GoogleCalendar
from backend.integrations.http import IntegrationError
from backend.integrations.openrouteservice import OpenRouteService
from backend.integrations.tankerkoenig import Tankerkoenig
from backend.preferences import PreferenceStore

log = logging.getLogger(__name__)

LOOKAHEAD_DAYS = 7          # so weit im Voraus sucht der Assistent den nächsten Termin
RAIL_DETOUR_FACTOR = 1.2    # Gleisweg ≈ Luftlinie × Faktor (für die Preisschätzung)


class TravelSetupError(IntegrationError):
    """Etwas muss erst eingerichtet werden (Key, Heimatadresse, Kalender)."""


class HomeAddressMissing(TravelSetupError):
    def __init__(self):
        super().__init__("Ich kenne deine Heimatadresse noch nicht.")


@dataclass(frozen=True)
class Trip:
    """Weg zu einem Termin aus dem Kalender."""
    event: CalendarEvent
    origin_source: str          # "home" oder Titel des vorigen Termins
    plan: TripPlan


class TravelService:
    def __init__(self, ors_client: OpenRouteService | None, preferences: PreferenceStore,
                 calendar: GoogleCalendar | None = None, rail: DbTimetables | None = None,
                 fuel: Tankerkoenig | None = None,
                 clock: Callable[[], datetime.datetime] = lambda: datetime.datetime.now().astimezone()):
        self.ors = ors_client
        self.preferences = preferences
        self.calendar = calendar
        self.rail = rail
        self.fuel = fuel
        self.clock = clock
        self._trips: dict[tuple, Trip] = {}

    # --- Kalender ------------------------------------------------------------------------
    def next_trip(self, interactive: bool = True) -> Trip | None:
        """Weg zum nächsten Termin mit Ort. Start: Ort des vorigen Termins am selben Tag, sonst daheim.
        Der Plan wird je Termin, Startort und Bearbeitungsstand nur einmal berechnet
        (die Erinnerung fragt alle paar Minuten)."""
        self._ors()   # ohne Routen erst gar nicht den Kalender (und dessen Anmeldung) bemühen
        now = self.clock()
        events = self._events(now, interactive)
        target = next((event for event in events if event.location and event.start > now), None)
        if target is None:
            return None
        previous = [event for event in events if event.location and event.end <= target.start
                    and event.start.date() == target.start.date() and event.id != target.id]
        if previous:
            origin, source = previous[-1].location, previous[-1].title
        else:
            origin, source = self.home_address(), "home"
        key = (target.id, target.updated, target.start, target.location, origin)
        if key not in self._trips:
            self._trips = {key: Trip(target, source, self.plan(origin, target.location, target.start))}
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
    def plan(self, origin: str, destination: str, arrive_by: datetime.datetime) -> TripPlan:
        client = self._ors()
        settings = TravelSettings.from_preferences(self.preferences)
        start, end = client.geocode(origin), client.geocode(destination)
        options: list[Option] = []
        notes: list[str] = []
        air_km = distance_km(start, end)

        car = self._try(notes, "Auto/Taxi", lambda: client.route(ors.CAR, start, end))
        if car is not None:
            price, estimated = self._fuel_price(start, settings, notes)
            options += [planner.car_option(car, price, estimated, settings, arrive_by),
                        planner.taxi_option(car, settings, arrive_by)]
        if air_km <= settings.max_bike_km:
            bike = self._try(notes, "Fahrrad", lambda: client.route(ors.BIKE, start, end))
            if bike is not None:
                options.append(planner.bike_option(bike, settings, arrive_by))
        if air_km <= settings.max_walk_km:
            walk = self._try(notes, "Zu Fuß", lambda: client.route(ors.FOOT, start, end))
            if walk is not None:
                options.append(planner.walk_option(walk, settings, arrive_by))
        if self.rail is None:
            notes.append("Bahn: DB-API nicht eingerichtet (PDA_DB_CLIENT_ID, PDA_DB_API_KEY).")
        else:
            train = self._try(notes, "Bahn", lambda: self._train(client, start, end, arrive_by, settings, notes))
            if train is not None:
                options.append(train)
        return TripPlan(start, end, arrive_by, planner.rank(options, settings), settings, tuple(notes))

    def _train(self, client: OpenRouteService, start: Place, end: Place, arrive_by: datetime.datetime,
               settings: TravelSettings, notes: list[str]) -> Option | None:
        origin = self.rail.find_station(client.locality(start))
        destination = self.rail.find_station(client.locality(end))
        if origin.eva == destination.eva:
            notes.append(f"Bahn: Start und Ziel liegen am selben Bahnhof ({origin.name}).")
            return None
        origin_place = client.geocode(origin.name)
        destination_place = client.geocode(destination.name)
        access = self._leg(client, start, origin_place, settings)
        egress = self._leg(client, destination_place, end, settings)
        latest_arrival = arrive_by - datetime.timedelta(minutes=settings.buffer_minutes, seconds=egress.duration_s)
        connection = self.rail.latest_direct(origin, destination, latest_arrival)
        if connection is None:
            notes.append(f"Bahn: keine Direktverbindung {origin.name} → {destination.name} gefunden "
                         "(Umstiege sucht die DB-Timetables-API nicht).")
            return None
        rail_km = distance_km(origin_place, destination_place) * RAIL_DETOUR_FACTOR
        return planner.train_option(connection, access, egress, rail_km, settings)

    def _leg(self, client: OpenRouteService, start: Place, end: Place, settings: TravelSettings) -> planner.Leg:
        walk = client.route(ors.FOOT, start, end)
        car = client.route(ors.CAR, start, end) if walk.duration_s > settings.station_walk_minutes * 60 else None
        return planner.walk_or_transit_leg(walk, car, settings)

    def _fuel_price(self, place: Place, settings: TravelSettings, notes: list[str]) -> tuple[float, bool]:
        if self.fuel is not None:
            price = self._try(notes, "Spritpreis", lambda: self.fuel.price(place, settings.fuel))
            if price is not None:
                return price, False
        return settings.fuel_price, True

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
