"""Attrappen für den Reise-Assistenten: Dienste ohne Netzwerk, feste Uhrzeit."""
from __future__ import annotations

import datetime

from backend.assistant.skills.travel.service import TravelService
from backend.integrations import openrouteservice as ors
from backend.integrations.db_timetables import Journey, Station, TrainConnection
from backend.integrations.geo import Place
from backend.integrations.google_calendar import CalendarEvent
from backend.integrations.http import IntegrationError
from backend.integrations import transit
from backend.integrations.openrouteservice import Route, Step
from backend.integrations.weather import Weather
from tests.test_interfaces import InMemoryPreferences

TZ = datetime.timezone(datetime.timedelta(hours=2))
NOW = datetime.datetime(2026, 10, 21, 8, 0, tzinfo=TZ)
HOME = Place("Zuhause, Mannheim", 49.48, 8.46)
UNI = Place("Universität, Heidelberg", 49.41, 8.67)
PLACES = {"Zuhause": HOME, "Universität": UNI, "Mannheim Hbf": Place("Mannheim Hbf, Mannheim", 49.479, 8.469),
          "Heidelberg Hbf": Place("Heidelberg Hbf, Heidelberg", 49.404, 8.676)}

# Mannheim → Heidelberg: Auto 25 Min., Rad 70 Min.; zum/vom Bahnhof je 10 Min. zu Fuß
ROUTES = {
    ors.CAR: Route(21000, 1500, (Step("Losfahren", 100, 10), Step("", 0, 0)), ((8.46, 49.48), (8.67, 49.41))),
    ors.BIKE: Route(20000, 4200),
    ors.FOOT: Route(800, 600),
}


def event(id_="t1", title="Vorlesung", start=NOW + datetime.timedelta(hours=2), minutes=90, location="Universität"):
    return CalendarEvent(id_, title, start, start + datetime.timedelta(minutes=minutes), location, "v1")


class FakeOrs:
    def __init__(self, routes=None):
        self.routes = dict(ROUTES if routes is None else routes)
        self.calls = []

    def geocode(self, text):
        self.calls.append(("geocode", text))
        if text not in PLACES:
            raise IntegrationError(f"Adresse nicht gefunden: {text!r}")
        return PLACES[text]

    def locality(self, place):
        return place.label.split(", ")[-1]

    def route(self, profile, start, end):
        self.calls.append(("route", profile))
        route = self.routes.get(profile)
        if isinstance(route, Exception):
            raise route
        if route is None:
            raise IntegrationError(f"Keine Route ({profile})")
        return route


def transit_journey(departure, bus=True):
    """Fußweg 5 Min. → Bus 33 (10 Min.) → 6 Min. Umstieg → S3 (16 Min.) → Fußweg 4 Min.
    bus=False: nur die S3."""
    minutes = datetime.timedelta(minutes=1)
    walk_to = transit.Leg("WALK", "", "Start", "Paradeplatz", departure, departure + 5 * minutes,
                             geometry=((8.46, 49.48), (8.462, 49.481)))
    ride = transit.Leg("BUS", "Bus 33", "Paradeplatz", "Mannheim, Hauptbahnhof", departure + 5 * minutes,
                          departure + 15 * minutes, platform="B", headsign="Hauptbahnhof", realtime=True,
                          geometry=((8.462, 49.481), (8.469, 49.479)))
    train = transit.Leg("SUBURBAN", "S3", "Mannheim, Hauptbahnhof", "Heidelberg, Hauptbahnhof",
                           departure + 21 * minutes, departure + 37 * minutes, platform="9",
                           scheduled_departure=departure + 19 * minutes, headsign="Karlsruhe",
                           messages=("Bauarbeiten",), geometry=((8.469, 49.479), (8.675, 49.404)))
    walk_from = transit.Leg("WALK", "", "Heidelberg, Hauptbahnhof", "Ziel", departure + 37 * minutes,
                               departure + 41 * minutes, geometry=((8.675, 49.404), (8.67, 49.41)))
    return transit.Journey((walk_to, ride, train, walk_from) if bus else (walk_to, train, walk_from))


def vvs_journey(departure=None):
    """Wie transit_journey, mit VVS-Preis."""
    journey = transit_journey(departure or NOW)
    return transit.Journey(journey.legs, 3.45, "EinzelTicket Erwachsene", "VVS")


class FakeTransit:
    """Transitous-Attrappe: Verbindung 50 Min. vor arrive_by bzw. ab depart_after; journey=None: keine,
    Exception: Transitous nicht erreichbar."""

    def __init__(self, journey=True, area=True):
        self.journey = journey
        self.area = area   # nur VVS: liegt der Weg im Verbundgebiet?
        self.calls = []

    def covers(self, start, end):
        return self.area

    def latest_journey(self, start, end, arrive_by, max_transfers=2, min_transfer_minutes=5, max_walk_minutes=15,
                       not_before=None):
        self.calls.append(("latest", arrive_by, max_transfers, min_transfer_minutes, max_walk_minutes, not_before))
        return self._answer(arrive_by - datetime.timedelta(minutes=50))

    def earliest_journey(self, start, end, depart_after, max_transfers=2, min_transfer_minutes=5, max_walk_minutes=15):
        self.calls.append(("earliest", depart_after, max_transfers, min_transfer_minutes, max_walk_minutes))
        return self._answer(depart_after)

    def _answer(self, departure):
        if isinstance(self.journey, Exception):
            raise self.journey
        if callable(self.journey):
            return self.journey(departure)
        return transit_journey(departure) if self.journey is True else self.journey


class FakeRail:
    """Liefert einen Zug 30 Min. vor arrive_by bzw. 5 Min. nach depart_after (20 Min. Fahrt)."""

    def __init__(self, connection=True):
        self.connection = connection
        self.arrive_by = None
        self.depart_after = None
        self.search = None
        self.not_before = None

    def find_station(self, name):
        return Station(f"{name} Hbf", name)

    def latest_journey(self, origin, destination, arrive_by, max_transfers=1, min_transfer_minutes=5, not_before=None):
        self.arrive_by, self.search, self.not_before = arrive_by, (max_transfers, min_transfer_minutes), not_before
        return self._journey(origin, destination, arrive_by - datetime.timedelta(minutes=30))

    def earliest_journey(self, origin, destination, depart_after, max_transfers=1, min_transfer_minutes=5):
        self.depart_after, self.search = depart_after, (max_transfers, min_transfer_minutes)
        return self._journey(origin, destination, depart_after + datetime.timedelta(minutes=5))

    def _journey(self, origin, destination, departure):
        if self.connection is not True:
            return self.connection
        return Journey((TrainConnection("RE 10", False, origin, destination, departure,
                                        departure + datetime.timedelta(minutes=20), "3", realtime=True),))


class FakeWeather:
    def __init__(self, weather=None):
        self.weather = weather if weather is not None else Weather(NOW, 15.0, 0.0, 0, 10.0)
        self.calls = []

    def at(self, place, moment):
        self.calls.append((place, moment))
        if isinstance(self.weather, Exception):
            raise self.weather
        return self.weather


RAIN = Weather(NOW, 8.0, 2.5, 90, 20.0, 63)


class FakeCalendar:
    def __init__(self, *events):
        self.events_ = list(events)
        self.calls = []

    def events(self, start, end, limit=50, interactive=True):
        self.calls.append(interactive)
        return list(self.events_)


class FakeFuel:
    def __init__(self, price=1.50):
        self.price_ = price

    def price(self, place, fuel):
        if isinstance(self.price_, Exception):
            raise self.price_
        return self.price_


class FakeStations:
    """Bahnhof mit Koordinaten zu jedem Ort; mit Exception: StaDa nicht verfügbar."""

    def __init__(self, error=None):
        self.error = error
        self.calls = []
        self.known = {}   # EVA → (Länge, Breite) der gelieferten Bahnhöfe

    def nearest(self, place, max_category=None):
        """Ohne max_category ein kleiner Halt "<Ort> Süd", sonst "<Ort> Hbf"."""
        self.calls.append((place, max_category))
        if self.error is not None:
            raise self.error
        city = place.label.split(", ")[-1]
        name = f"{city} Hbf" if max_category else f"{city} Süd"
        station = Station(name, f"eva-{name}", place.lat + 0.01, place.lon)
        self.known[station.eva] = (station.lon, station.lat)
        return station

    def coordinates(self, eva):
        return None if self.error is not None else self.known.get(eva)


def make_service(ors_client=None, calendar=None, rail=None, fuel=None, home="Zuhause", weather=None, stations=None,
                 transit=None, vvs=None, **preferences):
    prefs = InMemoryPreferences()
    if home:
        prefs.set("travel_home_address", home)
    for key, value in preferences.items():
        prefs.set("travel_" + key, value)
    clock = {"now": NOW}
    service = TravelService(FakeOrs() if ors_client is None else ors_client, prefs, calendar, rail, fuel, weather,
                            clock=lambda: clock["now"], stations=stations, transit=transit, vvs=vvs)
    service.test_clock = clock   # Tests können die Zeit vorstellen
    return service
