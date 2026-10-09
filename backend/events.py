"""Ereignisse vom Backend an das Frontend (Push) - ohne dass das Frontend fragt.

Grundlage für autonomes Verhalten, z. B. ein Morning-Briefing zu einer festen
Uhrzeit oder eine Erinnerung vor dem nächsten Termin:

    from backend.events import ASSISTANT_MESSAGE, events
    events.publish(ASSISTANT_MESSAGE, {"text": "...", "html": "..."})

Die Bridge (backend/bridge/web_bridge.py) leitet jedes Ereignis ans JavaScript
weiter; dort kommt es bei  onPythonEvent(name, handler)  an. publish() darf aus
jedem Thread aufgerufen werden. Der Payload muss JSON-tauglich sein.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)

EventHandler = Callable[[str, Any], None]

# Nachricht des Assistenten im Chat, Payload wie die Antwort von api.chat: {"text", "html"}
ASSISTANT_MESSAGE = "assistant_message"


class EventBus:
    def __init__(self) -> None:
        self._handlers: list[EventHandler] = []
        self._lock = threading.Lock()

    def subscribe(self, handler: EventHandler) -> Callable[[], None]:
        """Handler anmelden; gibt eine Funktion zum Abmelden zurück."""
        with self._lock:
            self._handlers.append(handler)

        def unsubscribe() -> None:
            with self._lock:
                if handler in self._handlers:
                    self._handlers.remove(handler)

        return unsubscribe

    def publish(self, name: str, payload: Any = None) -> None:
        with self._lock:
            handlers = list(self._handlers)
        for handler in handlers:
            try:
                handler(name, payload)
            except Exception:  # noqa: BLE001  # ein defekter Handler darf die anderen nicht stoppen
                log.exception("Handler für Ereignis %r fehlgeschlagen", name)


events = EventBus()
