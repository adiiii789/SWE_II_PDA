"""Proaktive Meldungen: Der PDA meldet sich von sich aus beim Nutzer.

Ablauf:
  Auslöser          heute: Makro Strg+Alt+P oder Tray-Menü (Vorführung, backend/desktop/)
                    später z. B.: 7 Uhr Briefing, Termin in 30 Minuten, neue Mail
    → api.proactive_message(name)
    → compose()     der Assistent formuliert die Meldung selbst (ProactiveAssistant.announce);
                    ohne Sprachmodell gilt der feste Ersatztext des Anlasses
    → announce()    Ereignis ASSISTANT_MESSAGE: Nachricht im Chat (mit "proactive": true)
                    Ereignis PROACTIVE_NOTICE: Windows-Benachrichtigung am Tray-Icon,
                    ein Klick darauf öffnet das Popup
    → vorlesen, wenn config.PROACTIVE_SPEAK und Sprachausgabe verfügbar

Neuer Anlass: ein Occasion-Objekt in OCCASIONS eintragen und den Auslöser
api.proactive_message("<name>") aufrufen lassen - aus beliebigem Thread.
"""
from __future__ import annotations

import datetime
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from backend.assistant import Assistant, AssistantReply, ProactiveAssistant
from backend.events import ASSISTANT_MESSAGE, PROACTIVE_NOTICE, EventBus
from backend.views import TemplateView

log = logging.getLogger(__name__)

NOTICE_MAX_CHARS = 200   # Windows kürzt längere Benachrichtigungen ohnehin


@dataclass(frozen=True)
class Occasion:
    """Anlass, zu dem sich der PDA meldet."""

    title: str         # Überschrift der Benachrichtigung und Ansicht
    instruction: str   # Auftrag ans Sprachmodell
    fallback: str      # Text, wenn kein Sprachmodell antworten kann
    trigger: str       # wodurch ausgelöst (steht in der Ansicht)


DEMO = "demo"

OCCASIONS: dict[str, Occasion] = {
    DEMO: Occasion(
        title="Dein PDA meldet sich",
        instruction=("Das ist eine Vorführung der proaktiven Meldung. Begrüße den Nutzer passend zur "
                     "Tageszeit, sag in einem Satz, wobei du dich künftig von selbst melden wirst "
                     "(z. B. Erinnerung an Termine, Morning-Briefing, wichtige neue Nachrichten), "
                     "und frag, ob du gerade helfen kannst. Höchstens drei kurze Sätze."),
        fallback=("Hallo, hier meldet sich dein PDA von sich aus. So kann ich dich künftig an Termine "
                  "erinnern, morgens ein Briefing geben oder auf wichtige Nachrichten hinweisen. "
                  "Kann ich dir gerade helfen?"),
        trigger="Makro (Test)",
    ),
}


def occasion(name: str) -> Occasion:
    try:
        return OCCASIONS[name]
    except KeyError:
        raise ValueError(f"Unbekannter Anlass: {name!r} (verfügbar: {sorted(OCCASIONS)})") from None


def compose(assistant: Assistant, occasion: Occasion,
            clock: Callable[[], datetime.datetime] = datetime.datetime.now) -> AssistantReply:
    """Meldung zum Anlass: vom Assistenten formuliert, sonst der Ersatztext. Wirft nie."""
    text = None
    if isinstance(assistant, ProactiveAssistant):
        try:
            text = assistant.announce(occasion.instruction)
        except Exception:  # noqa: BLE001  # die Meldung soll trotzdem ankommen
            log.exception("Assistent konnte die proaktive Meldung nicht formulieren")
    now = clock()
    view = TemplateView("default", {
        "title": occasion.title,
        "text": "Der PDA hat sich von sich aus gemeldet - ohne dass du etwas gefragt hast.",
        "columns": ["", ""],
        "rows": [["Ausgelöst", f"{now:%d.%m.%Y, %H:%M} Uhr"],
                 ["Auslöser", occasion.trigger],
                 ["Formuliert von", "Sprachmodell" if text else "festem Text (kein Sprachmodell)"]],
    })
    return AssistantReply(text or occasion.fallback, view)


def announce(message: dict[str, Any], occasion: Occasion, event_bus: EventBus) -> dict[str, Any]:
    """Fertige Nachricht (presenter.present) im Chat und als Benachrichtigung zeigen.
    Gibt die Chat-Nachricht zurück, wie sie ans Frontend ging."""
    message = {**message, "proactive": True, "title": occasion.title}
    event_bus.publish(ASSISTANT_MESSAGE, message)
    event_bus.publish(PROACTIVE_NOTICE, {"title": occasion.title, "text": notice_text(message["text"])})
    return message


def notice_text(text: str) -> str:
    """Kurzfassung für die Windows-Benachrichtigung: ohne Markdown-Zeichen, eine Zeile, gekürzt."""
    plain = " ".join(text.replace("**", "").replace("__", "").replace("`", "").replace("#", "").split())
    return plain if len(plain) <= NOTICE_MAX_CHARS else plain[:NOTICE_MAX_CHARS - 1].rstrip() + "…"
