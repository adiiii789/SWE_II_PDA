"""TravelReminder: meldet sich von selbst, kurz bevor man zum nächsten Termin - oder nach dem
letzten Termin des Tages nach Hause - losmuss.

Läuft in einem Hintergrund-Thread und schaut alle config.TRAVEL_CHECK_INTERVAL_S in den
Kalender. Den Plan rechnet TravelService nur neu, wenn sich der Termin ändert - und kurz bevor die
Erinnerung kommt noch einmal (FRESH_PLAN): Der erste Plan ist oft Stunden alt, jetzt zählen die
aktuellen Abfahrten mit Verspätungen. Fährt die Empfehlung dann später, wartet die Erinnerung. Ob, wie früh
und wie (Popup, Benachrichtigung, nur Chat, vorlesen) er sich meldet, steht in den
Einstellungen (⚙ → Reise) und wird bei jeder Prüfung neu gelesen. Öffnet nie den Browser zur
Anmeldung: Wer sich noch nicht beim Kalender angemeldet hat, bekommt keine Erinnerung.
"""
from __future__ import annotations

import datetime
import logging
import threading
from collections.abc import Callable

from backend.assistant.base import AssistantReply
from backend.assistant.skills.travel.planner import TravelSettings
from backend.assistant.skills.travel.service import TravelService, TravelSetupError
from backend.assistant.skills.travel.view import summary, trip_view
from backend.integrations.http import IntegrationError

log = logging.getLogger(__name__)

HOME_GRACE = datetime.timedelta(minutes=30)   # Heimweg: höchstens so lange nach Terminende erinnern
FRESH_PLAN = datetime.timedelta(minutes=5)    # vor der Erinnerung neu rechnen, wenn der Plan älter ist

# notify(reply, settings): Meldung zeigen - wie, steht in settings (reminder_display, reminder_speak)
Notify = Callable[[AssistantReply, TravelSettings], None]


class TravelReminder:
    def __init__(self, service: TravelService, notify: Notify, interval_s: float):
        self.service = service
        self.notify = notify
        self.interval_s = interval_s
        self._reminded: set[tuple[str, str, datetime.datetime]] = set()
        self._last_warning = ""   # dieselbe Warnung (z. B. Ort nicht gefunden) nicht alle paar Minuten

    def check(self) -> bool:
        """Einmal prüfen; True, wenn eine Erinnerung verschickt wurde."""
        settings = self.service.settings()
        if not settings.reminder:
            return False
        try:
            trip = self.service.next_trip(interactive=False)
        except TravelSetupError as error:   # z. B. noch nicht beim Kalender angemeldet
            log.debug("Reise-Erinnerung: %s", error)
            return False
        except IntegrationError as error:
            if str(error) != self._last_warning:
                log.warning("Reise-Erinnerung: %s", error)
            self._last_warning = str(error)
            return False
        self._last_warning = ""
        if not self._due(trip, settings):
            return False
        try:   # gleich ist es so weit: mit aktuellen Abfahrten (Verspätungen) neu rechnen
            trip = self.service.next_trip(interactive=False, fresh_after=FRESH_PLAN) or trip
        except IntegrationError as error:
            log.warning("Reise-Erinnerung: Plan nicht aktualisiert, nehme den alten: %s", error)
        if not self._due(trip, settings):
            return False   # fährt jetzt später - dann eben später erinnern
        best = trip.plan.recommended
        key = ("home" if trip.home else "to", trip.event.id, trip.event.start)
        now = self.service.clock()
        self._reminded.add(key)
        minutes = max(0, round((best.depart_at - now).total_seconds() / 60))
        when = f"In {minutes} Minuten" if minutes else "Jetzt"
        if trip.home:
            text = f"{when} geht es nach Hause (nach „{trip.event.title}“). "
        else:
            text = f"{when} solltest du los zu „{trip.event.title}“. "
        self.notify(AssistantReply(text + summary(trip.plan, trip.event.title, trip.home),
                                   trip_view(trip.plan, trip.event.title, trip.home, self.service.tiles)), settings)
        return True

    def _due(self, trip, settings: TravelSettings) -> bool:
        """Ist es Zeit für die Erinnerung (Abfahrt minus Vorlauf erreicht, Termin noch nicht begonnen)
        und war sie für diesen Termin noch nicht da?"""
        best = trip.plan.recommended if trip else None
        if best is None or best.depart_at is None or trip.plan.same_place:   # z. B. nächste Vorlesung im selben Haus
            return False
        key = ("home" if trip.home else "to", trip.event.id, trip.event.start)
        now = self.service.clock()
        until = trip.event.end + HOME_GRACE if trip.home else trip.event.start
        lead = datetime.timedelta(minutes=settings.reminder_minutes)
        return key not in self._reminded and best.depart_at - lead <= now < until

    def start(self) -> Callable[[], None]:
        """Im Hintergrund prüfen, bis die zurückgegebene Funktion aufgerufen wird."""
        stop = threading.Event()

        def run() -> None:
            while not stop.is_set():
                try:
                    self.check()
                except Exception:   # noqa: BLE001  # der Thread darf nie sterben
                    log.exception("Reise-Erinnerung fehlgeschlagen")
                stop.wait(self.interval_s)

        threading.Thread(target=run, name="travel-reminder", daemon=True).start()
        return stop.set
