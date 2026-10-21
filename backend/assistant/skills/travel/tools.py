"""TravelTools: Werkzeuge des Reise-Assistenten fürs Sprachmodell (erfüllt ToolProvider)."""
from __future__ import annotations

import datetime
from collections.abc import Callable
from typing import Any

from backend.assistant.skills.travel.service import HomeAddressMissing, TravelService
from backend.assistant.skills.travel.view import summary, trip_view
from backend.assistant.tools import ToolResult, ToolSpec, UnknownToolError
from backend.integrations.http import IntegrationError

NEXT_TRIP, PLAN_TRIP, SET_HOME = "plan_trip_to_next_appointment", "plan_trip", "set_home_address"
DEFAULT_LEAD = datetime.timedelta(hours=1)   # plan_trip ohne Ankunftszeit: Ankunft in einer Stunde

_SPECS = [
    ToolSpec(NEXT_TRIP,
             "Bester Weg zum nächsten Termin mit Ort aus dem Kalender: vergleicht Auto, Bahn, Taxi, "
             "Fahrrad und zu Fuß und sagt, wann man losmuss.",
             {"type": "object", "properties": {}}),
    ToolSpec(PLAN_TRIP,
             "Bester Weg zu einer beliebigen Adresse (Auto, Bahn, Taxi, Fahrrad, zu Fuß).",
             {"type": "object", "properties": {
                 "destination": {"type": "string", "description": "Zieladresse oder Ort"},
                 "origin": {"type": "string", "description": "Startadresse; leer = Heimatadresse"},
                 "arrive_by": {"type": "string",
                               "description": "Gewünschte Ankunft, ISO-Format, z. B. 2026-10-21T14:00"},
             }, "required": ["destination"]}),
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
        handlers = {NEXT_TRIP: self._next_trip, PLAN_TRIP: self._plan_trip, SET_HOME: self._set_home}
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
        trip = self._service().next_trip()
        if trip is None:
            return ToolResult("In den nächsten Tagen steht kein Termin mit Ort im Kalender.")
        title = f"{trip.event.title} ({trip.event.start:%d.%m. %H:%M})"
        return ToolResult(summary(trip.plan, title), view=trip_view(trip.plan, trip.event.title))

    def _plan_trip(self, arguments: dict[str, Any]) -> ToolResult:
        service = self._service()
        origin = arguments.get("origin") or service.home_address()
        arrive_by = _parse_time(arguments.get("arrive_by"), service.clock())
        plan = service.plan(origin, arguments["destination"], arrive_by)
        return ToolResult(summary(plan), view=trip_view(plan))

    def _set_home(self, arguments: dict[str, Any]) -> ToolResult:
        place = self._service().set_home_address(arguments["address"])
        return ToolResult(f"Heimatadresse gespeichert: {place.label}")


def _parse_time(text: str | None, now: datetime.datetime) -> datetime.datetime:
    if not text:
        return now + DEFAULT_LEAD
    try:
        moment = datetime.datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(f"Ungültige Zeit {text!r}, erwartet z. B. 2026-10-21T14:00") from None
    return moment if moment.tzinfo else moment.astimezone()   # ohne Zone: Ortszeit des PCs
