"""TravelReminder: meldet sich von selbst im Chat, kurz bevor man zum nächsten Termin losmuss.

Läuft in einem Hintergrund-Thread und schaut alle config.TRAVEL_CHECK_INTERVAL_S in den
Kalender. Den Plan rechnet TravelService nur neu, wenn sich der Termin ändert. Öffnet nie
den Browser zur Anmeldung: Wer sich noch nicht beim Kalender angemeldet hat, bekommt
keine Erinnerung, bis er "reise" einmal benutzt hat.
"""
from __future__ import annotations

import datetime
import logging
import threading
from collections.abc import Callable

from backend.assistant.base import AssistantReply
from backend.assistant.skills.travel.service import TravelService, TravelSetupError
from backend.assistant.skills.travel.view import summary, trip_view
from backend.integrations.http import IntegrationError

log = logging.getLogger(__name__)


class TravelReminder:
    def __init__(self, service: TravelService, push: Callable[[AssistantReply], None],
                 lead_minutes: int, interval_s: float):
        self.service = service
        self.push = push
        self.lead = datetime.timedelta(minutes=lead_minutes)
        self.interval_s = interval_s
        self._reminded: set[tuple[str, datetime.datetime]] = set()

    def check(self) -> bool:
        """Einmal prüfen; True, wenn eine Erinnerung verschickt wurde."""
        try:
            trip = self.service.next_trip(interactive=False)
        except TravelSetupError as error:   # z. B. noch nicht beim Kalender angemeldet
            log.debug("Reise-Erinnerung: %s", error)
            return False
        except IntegrationError as error:
            log.warning("Reise-Erinnerung: %s", error)
            return False
        best = trip.plan.recommended if trip else None
        if best is None or best.depart_at is None:
            return False
        key = (trip.event.id, trip.event.start)
        now = self.service.clock()
        if key in self._reminded or not best.depart_at - self.lead <= now < trip.event.start:
            return False
        self._reminded.add(key)
        minutes = max(0, round((best.depart_at - now).total_seconds() / 60))
        lead = f"In {minutes} Minuten" if minutes else "Jetzt"
        self.push(AssistantReply(f"{lead} solltest du los zu „{trip.event.title}“. " + summary(trip.plan),
                                 trip_view(trip.plan, trip.event.title)))
        return True

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
