"""Proaktive Meldungen: EVE meldet sich von sich aus beim Nutzer.

Ablauf:
  Auslöser          Makro Strg+Alt+P oder Tray-Menü (Vorführung, backend/desktop/);
                    der Wächter (backend/watcher.py) bei Mails, Aufgaben und Terminen
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
from backend.config import APP_NAME
from backend.events import ASSISTANT_MESSAGE, PROACTIVE_NOTICE, EventBus
from backend.views import TemplateView

log = logging.getLogger(__name__)

NOTICE_MAX_CHARS = 200   # Windows kürzt längere Benachrichtigungen ohnehin


@dataclass(frozen=True)
class Occasion:
    """Anlass, zu dem sich EVE meldet."""

    title: str         # Überschrift der Benachrichtigung und Ansicht
    instruction: str   # Auftrag ans Sprachmodell
    fallback: str      # Text, wenn kein Sprachmodell antworten kann
    trigger: str       # wodurch ausgelöst (steht in der Ansicht)
    view: TemplateView | None = None
    chat_text: str | None = None  # kurze Nachricht, wenn die Details in der Ansicht stehen


DEMO = "demo"

OCCASIONS: dict[str, Occasion] = {
    DEMO: Occasion(
        title=f"{APP_NAME} meldet sich",
        instruction=("Das ist eine Vorführung der proaktiven Meldung. Begrüße den Nutzer passend zur "
                     "Tageszeit, sag in einem Satz, wobei du dich künftig von selbst melden wirst "
                     "(z. B. Erinnerung an Termine, Morning-Briefing, wichtige neue Nachrichten), "
                     "und frag, ob du gerade helfen kannst. Höchstens drei kurze Sätze."),
        fallback=(f"Hallo, hier meldet sich {APP_NAME} von sich aus. So kann ich dich künftig an Termine "
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
    if occasion.view is not None:
        return AssistantReply(occasion.chat_text or occasion.fallback, occasion.view, view_button="Briefing anzeigen")
    text = None
    if isinstance(assistant, ProactiveAssistant):
        try:
            text = assistant.announce(occasion.instruction)
        except Exception:  # noqa: BLE001  # die Meldung soll trotzdem ankommen
            log.exception("Assistent konnte die proaktive Meldung nicht formulieren")
    now = clock()
    view = TemplateView("default", {
        "title": occasion.title,
        "text": f"{APP_NAME} hat sich von sich aus gemeldet - ohne dass du etwas gefragt hast.",
        "columns": ["", ""],
        "rows": [["Ausgelöst", f"{now:%d.%m.%Y, %H:%M} Uhr"],
                 ["Auslöser", occasion.trigger],
                 ["Formuliert von", "Sprachmodell" if text else "festem Text (kein Sprachmodell)"]],
    })
    return AssistantReply(text or occasion.fallback, view)


def announce(message: dict[str, Any], occasion: Occasion, event_bus: EventBus,
             display: str | None = None) -> dict[str, Any]:
    """Fertige Nachricht (presenter.present) im Chat und als Benachrichtigung zeigen.

    display: "popup", "notice", "chat" (nur im Chat, kein Hinweis); None = Standard der App.
    Gibt die Chat-Nachricht zurück, wie sie ans Frontend ging."""
    message = {**message, "proactive": True, "title": occasion.title}
    event_bus.publish(ASSISTANT_MESSAGE, message)
    if display == "chat":
        return message
    notice_body = occasion.chat_text.partition("\n\n")[0] if occasion.chat_text is not None else message["text"]
    notice = {"title": occasion.title, "text": notice_text(notice_body)}
    event_bus.publish(PROACTIVE_NOTICE, notice if display is None else {**notice, "display": display})
    return message


def notice_text(text: str) -> str:
    """Kurzfassung für die Windows-Benachrichtigung: ohne Markdown-Zeichen, eine Zeile, gekürzt."""
    plain = " ".join(text.replace("**", "").replace("__", "").replace("`", "").replace("#", "").split())
    return plain if len(plain) <= NOTICE_MAX_CHARS else plain[:NOTICE_MAX_CHARS - 1].rstrip() + "…"
