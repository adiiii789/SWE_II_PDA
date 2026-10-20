"""Bereitet Antworten des Assistenten für das Frontend auf:
{"text": str, "html": str | None, "attachments": [{"id", "name", "mime_type", "size", "can_open"}]}

Dasselbe Format für beide Wege:
  - Antwort auf eine Chat-Nachricht   (api.chat)
  - Nachricht, die das Backend von sich aus schickt  (push - z. B. Morning-Briefing)
"""
from __future__ import annotations

from functools import cache
from typing import Any

from backend import config
from backend.assistant import AssistantReply
from backend.attachments import AttachmentStore
from backend.events import ASSISTANT_MESSAGE, EventBus, events
from backend.rendering import ViewRenderer


@cache
def renderer() -> ViewRenderer:
    return ViewRenderer(config.TEMPLATE_DIR, config.FRONTEND_DIR)


@cache
def attachment_store() -> AttachmentStore:
    return AttachmentStore(config.ATTACHMENT_DIR, config.DOWNLOAD_DIR)


def present(reply: AssistantReply, store: AttachmentStore | None = None) -> dict[str, Any]:
    """"html" ist die fertige Ansicht fürs iframe; None = Ansicht beibehalten.
    "attachments" enthält nur Dateien, die der AttachmentStore angenommen hat."""
    html = renderer().render(reply.view) if reply.view else None
    store = store or attachment_store()
    attachments = [entry for entry in map(store.register, reply.attachments) if entry]
    return {"text": reply.text, "html": html, "attachments": attachments}


def push(reply: AssistantReply, event_bus: EventBus = events) -> None:
    """Nachricht des Assistenten ohne vorherige Nutzereingabe im Chat anzeigen."""
    event_bus.publish(ASSISTANT_MESSAGE, present(reply))
