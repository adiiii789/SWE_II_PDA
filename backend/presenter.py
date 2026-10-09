"""Bereitet Antworten des Assistenten für das Frontend auf: {"text": str, "html": str | None}.

Dasselbe Format für beide Wege:
  - Antwort auf eine Chat-Nachricht   (api.chat)
  - Nachricht, die das Backend von sich aus schickt  (push - z. B. Morning-Briefing)
"""
from __future__ import annotations

from functools import cache
from typing import Any

from backend import config
from backend.assistant import AssistantReply
from backend.events import ASSISTANT_MESSAGE, EventBus, events
from backend.rendering import ViewRenderer


@cache
def renderer() -> ViewRenderer:
    return ViewRenderer(config.TEMPLATE_DIR, config.FRONTEND_DIR)


def present(reply: AssistantReply) -> dict[str, Any]:
    """"html" ist die fertige Ansicht fürs iframe; None = Ansicht beibehalten."""
    html = renderer().render(reply.view) if reply.view else None
    return {"text": reply.text, "html": html}


def push(reply: AssistantReply, event_bus: EventBus = events) -> None:
    """Nachricht des Assistenten ohne vorherige Nutzereingabe im Chat anzeigen."""
    event_bus.publish(ASSISTANT_MESSAGE, present(reply))
