"""Fähigkeit travel: Wie komme ich zum nächsten Termin?

  planner.py   Kosten der Verkehrsmittel (Preis + Zeit × Zeitwert), Einstellungen
  service.py   TravelService: Kalender, openrouteservice, DB Timetables, Tankerkönig
  view.py      Plan als Text und als Ansicht (frontend/templates/travel.html.j2)
  tools.py     Werkzeuge fürs Sprachmodell
  reminder.py  Erinnerung vor der Abfahrt (autonomer Auslöser)

Ohne Sprachmodell: fester Befehl "reise" (next_trip_reply).
"""
from __future__ import annotations

from collections.abc import Callable
from functools import cache

from backend import config
from backend.assistant.base import AssistantReply
from backend.assistant.skills.base import Skill
from backend.assistant.skills.travel.planner import HOME_ADDRESS
from backend.assistant.skills.travel.service import HomeAddressMissing, TravelService
from backend.assistant.skills.travel.tools import TravelTools
from backend.assistant.skills.travel.view import summary, trip_view
from backend.integrations.http import IntegrationError
from backend.views import TemplateView

INSTRUCTIONS = (
    "Reise: Fragt der Nutzer, wie er zu einem Termin kommt oder wann er losmuss, nutze "
    "plan_trip_to_next_appointment; für andere Ziele plan_trip. Nenne die Empfehlung mit "
    "Abfahrtszeit und kurz die beste Alternative - die Details zeigt die Ansicht. Fehlt die "
    "Heimatadresse, frag danach und speichere sie mit set_home_address. Bahnpreise sind Schätzungen."
)


@cache
def service() -> TravelService:
    # Erst hier importieren: Ohne Reise-Funktion braucht die App keinen dieser Clients.
    from backend.integrations.db_timetables import DbTimetables
    from backend.integrations.google_calendar import GoogleCalendar, oauth_token
    from backend.integrations.http import JsonHttp
    from backend.integrations.openrouteservice import OpenRouteService
    from backend.integrations.tankerkoenig import Tankerkoenig
    from backend.preferences import app_preferences

    http = JsonHttp(config.HTTP_TIMEOUT_S)
    return TravelService(
        OpenRouteService(http, config.ORS_KEY) if config.ORS_KEY else None,
        app_preferences(),
        GoogleCalendar(http, oauth_token(config.GOOGLE_DIR)),
        DbTimetables(http, config.DB_CLIENT_ID, config.DB_API_KEY) if config.DB_CLIENT_ID and config.DB_API_KEY else None,
        Tankerkoenig(http, config.TANKERKOENIG_KEY) if config.TANKERKOENIG_KEY else None,
    )


def next_trip_reply() -> AssistantReply:
    """Fester Befehl "reise"."""
    try:
        trip = service().next_trip()
    except HomeAddressMissing as error:
        return _message(f"{error} Sag dem Assistenten z. B. „Meine Heimatadresse ist …“ oder trag "
                        f"\"{HOME_ADDRESS}\" in {config.PREFERENCES_FILE} ein.")
    except IntegrationError as error:
        return _message(str(error))
    if trip is None:
        return _message("In den nächsten Tagen steht kein Termin mit Ort im Kalender.")
    return AssistantReply(summary(trip.plan, trip.event.title), trip_view(trip.plan, trip.event.title))


def _start() -> Callable[[], None] | None:
    from backend import presenter
    from backend.assistant.skills.travel.reminder import TravelReminder

    if not config.ORS_KEY:
        return None   # ohne Routen keine Abfahrtszeit
    reminder = TravelReminder(service(), presenter.push, config.TRAVEL_REMINDER_MINUTES, config.TRAVEL_CHECK_INTERVAL_S)
    return reminder.start()


def _message(text: str) -> AssistantReply:
    return AssistantReply(text, TemplateView("default", {"title": "Reise-Assistent", "text": text}))


SKILL = Skill("travel", INSTRUCTIONS, TravelTools(service), start=_start)
