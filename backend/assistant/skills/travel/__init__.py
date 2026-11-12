"""Fähigkeit travel: Wie komme ich zum nächsten Termin?

  planner.py   Kosten der Verkehrsmittel (Preis + Zeit × Zeitwert × Wetter), TravelSettings
  service.py   TravelService: Kalender, openrouteservice, VVS und Transitous (Bahn/ÖPNV), DB OpenBoards/Timetables
               (Ersatz), Open-Meteo, Tankerkönig
  view.py      Plan als Text und als Ansicht (frontend/templates/travel.html.j2)
  tools.py     Werkzeuge fürs Sprachmodell
  reminder.py  Erinnerung vor der Abfahrt, auch für den Heimweg (autonomer Auslöser)
  settings.py  Formular im Popup (⚙ Einstellungen → Reise)

Ohne Sprachmodell: fester Befehl "reise" (next_trip_reply).
"""
from __future__ import annotations

from collections.abc import Callable
from functools import cache

from backend import config
from backend.assistant.base import AssistantReply
from backend.assistant.skills.base import Skill
from backend.assistant.skills.travel.planner import HOME_ADDRESS, TravelSettings
from backend.assistant.skills.travel.service import HomeAddressMissing, TravelService
from backend.assistant.skills.travel.tools import TravelTools
from backend.assistant.skills.travel.view import summary, trip_view
from backend.integrations.http import IntegrationError
from backend.views import TemplateView

INSTRUCTIONS = (
    "Reise: Fragt der Nutzer, wie er zu einem Termin kommt oder wann er losmuss, nutze "
    "plan_trip_to_next_appointment; für andere Ziele plan_trip, für den Weg nach Hause plan_trip_home. "
    "Nenne die Empfehlung mit Abfahrtszeit (bei Bahn/ÖPNV auch Linie und Umstiege) und kurz die beste "
    "Alternative - die Details zeigt die Ansicht. Hat das Wetter die Wahl beeinflusst, sag das kurz. "
    "Fehlt die Heimatadresse, frag danach und speichere sie mit set_home_address. Bahnpreise sind Schätzungen."
)


@cache
def service() -> TravelService:
    # Erst hier importieren: Ohne Reise-Funktion braucht die App keinen dieser Clients.
    from backend.integrations.db_stations import DbStations
    from backend.integrations.db_timetables import DbTimetables
    from backend.integrations.google_calendar import GoogleCalendar, oauth_token
    from backend.integrations.http import JsonHttp
    from backend.integrations.map_tiles import MapTiles
    from backend.integrations.openrouteservice import OpenRouteService
    from backend.integrations.tankerkoenig import Tankerkoenig
    from backend.integrations.transitous import Transitous
    from backend.integrations.vvs import Vvs
    from backend.integrations.weather import OpenMeteo
    from backend.preferences import default_store

    http = JsonHttp(config.HTTP_TIMEOUT_S)
    rail_keys = (config.DB_CLIENT_ID, config.DB_API_KEY) if config.DB_CLIENT_ID and config.DB_API_KEY else None
    stations = (DbStations(JsonHttp(config.STATIONS_TIMEOUT_S), *rail_keys, config.DB_STATIONS_FILE)
                if rail_keys else None)
    return TravelService(
        OpenRouteService(http, config.ORS_KEY) if config.ORS_KEY else None,
        default_store(),
        GoogleCalendar(http, oauth_token(config.GOOGLE_DIR)),
        DbTimetables(http, *rail_keys, locate=stations.lookup) if rail_keys else None,
        Tankerkoenig(http, config.TANKERKOENIG_KEY) if config.TANKERKOENIG_KEY else None,
        OpenMeteo(http),
        stations=stations,
        tiles=MapTiles(JsonHttp(config.TILE_TIMEOUT_S), config.TILE_DIR),
        transit=Transitous(http, config.TRANSITOUS_URL) if config.TRANSITOUS_URL else None,
        vvs=Vvs(http, config.VVS_URL) if config.VVS_URL else None,
    )


def next_trip_reply() -> AssistantReply:
    """Fester Befehl "reise"."""
    try:
        travel = service()
        trip = travel.next_trip()
    except HomeAddressMissing as error:
        return _message(f"{error} Sag dem Assistenten z. B. „Meine Heimatadresse ist …“ oder trag "
                        f"\"{HOME_ADDRESS}\" in {config.PREFERENCES_FILE} ein.")
    except IntegrationError as error:
        return _message(str(error))
    if trip is None:
        return _message("In den nächsten Tagen steht kein Termin mit Ort im Kalender.")
    return AssistantReply(summary(trip.plan, trip.event.title, trip.home),
                          trip_view(trip.plan, trip.event.title, trip.home, travel.tiles))


def _start() -> Callable[[], None] | None:
    from backend.assistant.skills.travel.reminder import TravelReminder

    if not config.ORS_KEY:
        return None   # ohne Routen keine Abfahrtszeit
    return TravelReminder(service(), _notify, config.TRAVEL_CHECK_INTERVAL_S).start()


def _notify(reply: AssistantReply, settings: TravelSettings) -> None:
    """Erinnerung wie eine proaktive Meldung zeigen (Popup, Benachrichtigung oder nur Chat)."""
    from backend import api   # erst hier: api braucht selbst den Assistenten samt Fähigkeiten

    api._announce_reply(reply, "Zeit loszufahren", "Reise-Assistent", settings.reminder_display,
                        settings.reminder_speak)


def _message(text: str) -> AssistantReply:
    return AssistantReply(text, TemplateView("default", {"title": "Reise-Assistent", "text": text}))


SKILL = Skill("travel", INSTRUCTIONS, TravelTools(service), start=_start)
