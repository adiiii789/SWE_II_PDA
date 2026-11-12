"""TravelTools: Werkzeuge des Reise-Assistenten fürs Sprachmodell (erfüllt ToolProvider)."""
from __future__ import annotations

import datetime
from collections.abc import Callable
from typing import Any

from backend.assistant.skills.travel.service import HomeAddressMissing, TravelService
from backend.assistant.skills.travel.view import summary, trip_view
from backend.assistant.tools import ToolResult, ToolSpec, UnknownToolError
from backend.integrations.http import IntegrationError

NEXT_TRIP, PLAN_TRIP, HOME_TRIP, SET_HOME = ("plan_trip_to_next_appointment", "plan_trip", "plan_trip_home",
                                             "set_home_address")
_TIME = "ISO-Format, z. B. 2026-10-21T14:00"

_SPECS = [
    ToolSpec(NEXT_TRIP,
             "Bester Weg zum nächsten Termin mit Ort aus dem Kalender: vergleicht Auto, Bahn (auch mit "
             "Umstiegen), Taxi, Fahrrad und zu Fuß, berücksichtigt das Wetter und sagt, wann man losmuss. "
             "Steht heute kein Termin mehr an: der Heimweg vom letzten Termin.",
             {"type": "object", "properties": {}}),
    ToolSpec(PLAN_TRIP,
             "Bester Weg zu einer beliebigen Adresse (Auto, Bahn, Taxi, Fahrrad, zu Fuß).",
             {"type": "object", "properties": {
                 "destination": {"type": "string", "description": "Zieladresse oder Ort"},
                 "origin": {"type": "string", "description": "Startadresse; leer = Heimatadresse"},
                 "arrive_by": {"type": "string", "description": f"Gewünschte Ankunft, {_TIME}"},
                 "depart_at": {"type": "string",
                               "description": f"Statt arrive_by: frühestens losfahren um, {_TIME}; "
                                              "beides leer = jetzt los"},
             }, "required": ["destination"]}),
    ToolSpec(HOME_TRIP,
             "Bester Weg nach Hause (zur gespeicherten Heimatadresse).",
             {"type": "object", "properties": {
                 "origin": {"type": "string",
                            "description": "Startadresse; leer = Ort des letzten Termins heute"},
                 "depart_at": {"type": "string",
                               "description": f"Losfahren um, {_TIME}; leer = Ende des letzten Termins bzw. jetzt"},
             }}),
    ToolSpec(SET_HOME,
             "Heimatadresse des Nutzers speichern (Start für den ersten Termin des Tages).",
             {"type": "object", "properties": {"address": {"type": "string"}}, "required": ["address"]}),
]


class TravelTools:
    def __init__(self, service: Callable[[], TravelService]):
        """service: liefert den TravelService erst beim ersten Aufruf (Erzeugen kostet dann nichts)."""
        self._service = service

    def list_tools(self) -> list[ToolSpec]:
        return list(_SPECS)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        handlers = {NEXT_TRIP: self._next_trip, PLAN_TRIP: self._plan_trip, HOME_TRIP: self._home_trip,
                    SET_HOME: self._set_home}
        if name not in handlers:
            raise UnknownToolError(f"Unbekanntes Werkzeug: {name!r}")
        try:
            return handlers[name](arguments)
        except HomeAddressMissing:
            return ToolResult("Die Heimatadresse ist unbekannt. Frag den Nutzer danach und speichere sie "
                              f"mit {SET_HOME}.", is_error=True)
        except (IntegrationError, ValueError) as error:
            return ToolResult(str(error), is_error=True)

    def _next_trip(self, arguments: dict[str, Any]) -> ToolResult:
        service = self._service()
        trip = service.next_trip()
        if trip is None:
            return ToolResult("In den nächsten Tagen steht kein Termin mit Ort im Kalender.")
        moment = trip.event.end if trip.home else trip.event.start
        title = f"{trip.event.title} ({moment:%d.%m. %H:%M})"
        return ToolResult(summary(trip.plan, title, trip.home),
                          view=trip_view(trip.plan, trip.event.title, trip.home, service.tiles))

    def _plan_trip(self, arguments: dict[str, Any]) -> ToolResult:
        service = self._service()
        origin = arguments.get("origin") or service.home_address()
        now = service.clock()
        if arguments.get("arrive_by"):
            plan = service.plan(origin, arguments["destination"], _parse_time(arguments["arrive_by"]))
        else:   # ohne Zeit: jetzt los
            depart = _parse_time(arguments["depart_at"]) if arguments.get("depart_at") else now
            plan = service.plan(origin, arguments["destination"], depart_after=depart)
        return ToolResult(summary(plan), view=trip_view(plan, tiles=service.tiles))

    def _home_trip(self, arguments: dict[str, Any]) -> ToolResult:
        service = self._service()
        home = service.home_address()
        now = service.clock()
        origin, title = arguments.get("origin"), ""
        depart = _parse_time(arguments["depart_at"]) if arguments.get("depart_at") else None
        if not origin:
            trip = service.next_trip()
            if trip is None or not trip.home:
                return ToolResult("Heute steht kein begonnener Termin mit Ort im Kalender - frag den Nutzer, "
                                  "von wo aus er heimwill, und gib es als origin an.", is_error=True)
            if depart is None:
                return ToolResult(summary(trip.plan, trip.event.title, True),
                                  view=trip_view(trip.plan, trip.event.title, True, service.tiles))
            origin, title = trip.event.location, trip.event.title
        plan = service.plan(origin, home, depart_after=max(depart or now, now))
        return ToolResult(summary(plan, title, True), view=trip_view(plan, title, True, service.tiles))

    def _set_home(self, arguments: dict[str, Any]) -> ToolResult:
        place = self._service().set_home_address(arguments["address"])
        return ToolResult(f"Heimatadresse gespeichert: {place.label}")


def _parse_time(text: str) -> datetime.datetime:
    try:
        moment = datetime.datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(f"Ungültige Zeit {text!r}, erwartet z. B. 2026-10-21T14:00") from None
    return moment if moment.tzinfo else moment.astimezone()   # ohne Zone: Ortszeit des PCs
