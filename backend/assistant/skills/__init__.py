"""Fähigkeiten (Skills) des Assistenten - ein Assistent, drei Aufgabenbereiche.

Es gibt genau einen durchgehenden Assistenten: ein Gesprächsverlauf, ein Satz
Präferenzen, Rückfragen über alle Bereiche hinweg. Eine Fähigkeit bündelt, was
er für einen Aufgabenbereich braucht. Umgesetzt ist travel (skills/travel/). Geplant:

  Fähigkeit           Wofür                                  Integrationen (backend/integrations/)
  ------------------  -------------------------------------  -------------------------------------
  morning             kurzes Briefing über den Tag           Calendar, OpenWeather, Aktien-API, Musik
  travel              wie komme ich zum nächsten Termin?     Calendar, Google Maps, Tankerkönig, Flüge
  organization        Nachrichten verfassen, Tag planen      Calendar, Gmail, Google Keep
                      (im Projektplan: "Assistant²")

Konvention:
  - Ein Modul pro Fähigkeit, z. B. skills/morning.py. Es stellt bereit:
      * die Integrationen der Fähigkeit (ToolProvider, gebündelt per
        CompositeToolProvider aus backend/assistant/tools.py),
      * kurze Anweisungen für das Sprachmodell (wann und wie die Werkzeuge
        einzusetzen sind, Antwortstil),
      * optional einen autonomen Auslöser (Skill.start), z. B. Briefing um 7 Uhr;
        die Antwort geht dann mit backend.presenter.push(reply) in den Chat. Die App
        startet alle Auslöser beim Start (start_triggers).
  - Der Assistent (ein Assistant mit LanguageModel, backend/assistant/llm.py) sammelt
    die Werkzeuge und Anweisungen aller Fähigkeiten. Das Modell wählt per
    Tool-Calling selbst, welche Werkzeuge es braucht. Sind es für ein kleines
    lokales Modell zu viele, gibt der Assistent je Anfrage nur die Werkzeuge der
    passenden Fähigkeit mit - die Struktur bleibt dieselbe.
  - Kontextwissen kommt aus dem PreferenceStore (backend/preferences.py).
  - Jedes Modul liefert ein Skill-Objekt (skills/base.py); es wird in SKILLS
    eingetragen. Größere Fähigkeiten sind ein Paket, z. B. skills/travel/. Der
    OllamaAssistant (backend/assistant/ollama_assistant.py) gibt dem Modell die
    Werkzeuge und Anweisungen aller Fähigkeiten mit.

Beispiel skills/morning.py:

    SKILL = Skill(
        name="morning",
        instructions="Für ein Briefing: Termine, Wetter und Aktien abfragen, in 3 Sätzen zusammenfassen.",
        tools=CompositeToolProvider([CalendarTools(), WeatherTools()]),
    )
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from backend.assistant.skills import travel
from backend.assistant.skills.base import Skill

log = logging.getLogger(__name__)

# Hier die Fähigkeiten eintragen, z. B. [morning.SKILL, travel.SKILL, organization.SKILL]
SKILLS: list[Skill] = [travel.SKILL]


def start_triggers(skills: list[Skill] = SKILLS) -> Callable[[], None]:
    """Autonome Auslöser aller Fähigkeiten starten (backend/desktop/application.py).
    Gibt eine Funktion zurück, die alle wieder beendet. Ein defekter Auslöser stoppt die anderen nicht."""
    stops: list[Callable[[], None]] = []
    for skill in skills:
        if skill.start is None:
            continue
        try:
            stop = skill.start()
        except Exception:  # noqa: BLE001  # z. B. kaputte Zugangsdaten - App startet trotzdem
            log.exception("Auslöser der Fähigkeit %r nicht gestartet", skill.name)
            continue
        if stop is not None:
            stops.append(stop)

    def stop_all() -> None:
        for stop in stops:
            stop()

    return stop_all


__all__ = ["SKILLS", "Skill", "start_triggers"]
