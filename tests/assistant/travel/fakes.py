"""Attrappen für den Reise-Assistenten: Dienste ohne Netzwerk, feste Uhrzeit."""
from __future__ import annotations

import datetime

from backend.assistant.skills.travel.service import TravelService
from backend.integrations import openrouteservice as ors
from backend.integrations.db_timetables import Station, TrainConnection
from backend.integrations.geo import Place
from backend.integrations.google_calendar import CalendarEvent
from backend.integrations.http import IntegrationError
from backend.integrations.openrouteservice import Route, Step
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


class FakeRail:
    def __init__(self, connection=True):
        self.connection = connection
        self.arrive_by = None

    def find_station(self, name):
        return Station(f"{name} Hbf", name)

    def latest_direct(self, origin, destination, arrive_by):
        self.arrive_by = arrive_by
        if self.connection is not True:
            return self.connection
        return TrainConnection("RE 10", False, origin, destination, arrive_by - datetime.timedelta(minutes=30),
                               arrive_by - datetime.timedelta(minutes=10), "3")


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


def make_service(ors_client=None, calendar=None, rail=None, fuel=None, home="Zuhause", **preferences):
    prefs = InMemoryPreferences()
    if home:
        prefs.set("travel_home_address", home)
    for key, value in preferences.items():
        prefs.set("travel_" + key, value)
    clock = {"now": NOW}
    service = TravelService(FakeOrs() if ors_client is None else ors_client, prefs, calendar, rail, fuel,
                            clock=lambda: clock["now"])
    service.test_clock = clock   # Tests können die Zeit vorstellen
    return service
