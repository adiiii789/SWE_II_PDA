"""Hochfahren im Hintergrund: Was vor der ersten Nachricht fertig sein soll (Ladebildschirm).

Die Popup-Seite ruft beim Laden api.loading_status() auf - das startet die Schritte einmalig in einem
eigenen Thread (Bridge-Aufrufe laufen nacheinander und würden sonst so lange warten) und liefert den
aktuellen Stand. Jeder Fortschritt kommt als Ereignis STARTUP_PROGRESS bei frontend/loading_screen.js an.

Ein fehlgeschlagener Schritt hält den Start nicht auf: Läuft z. B. Ollama nicht, meldet der Chat das
bei der ersten Nachricht.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from backend.events import STARTUP_PROGRESS, EventBus

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Step:
    label: str                 # steht auf dem Ladebildschirm
    run: Callable[[], Any]
    skippable: bool = False    # darf der Nutzer weitermachen, während das noch läuft?


class Startup:
    def __init__(self, steps: Sequence[Step], event_bus: EventBus):
        self._steps = tuple(steps)
        self._events = event_bus
        self._lock = threading.Lock()
        self._started = False
        self._finished_steps = 0
        self._done = False

    def status(self) -> dict[str, Any]:
        """{"done", "index" (fertige Schritte), "total", "labels", "label" (aktueller Schritt), "skippable"}"""
        with self._lock:
            index, done = self._finished_steps, self._done
        current = None if done else self._steps[index]
        return {"done": done, "index": index, "total": len(self._steps),
                "labels": [step.label for step in self._steps],
                "label": current.label if current else "",
                "skippable": bool(current and current.skippable)}

    def start(self) -> dict[str, Any]:
        """Beim ersten Aufruf im Hintergrund loslegen; gibt immer den aktuellen Stand zurück."""
        with self._lock:
            first = not self._started
            self._started = True
        if first:
            threading.Thread(target=self._run, name="startup", daemon=True).start()
        return self.status()

    def _run(self) -> None:
        for index, step in enumerate(self._steps):
            self._report(index)
            try:
                step.run()
            except Exception:  # noqa: BLE001  # der Rest soll trotzdem fertig werden
                log.exception("Startschritt %r fehlgeschlagen", step.label)
        self._report(len(self._steps), done=True)

    def _report(self, finished_steps: int, done: bool = False) -> None:
        with self._lock:
            self._finished_steps, self._done = finished_steps, done
        self._events.publish(STARTUP_PROGRESS, self.status())
