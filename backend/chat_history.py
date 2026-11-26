"""Gespeicherte Chats: Jedes Gespräch im Popup landet als JSON-Datei in config.CHATS_DIR und lässt sich
später wieder öffnen und fortsetzen (Chats-Knopf im Popup, frontend/chats.js; Funktionen in backend/api.py).

Gespeichert wird, was im Chat zu sehen war: Nachrichten des Nutzers, Antworten (Text; bei Antworten mit
"Anzeigen"-Knopf auch die Ansicht, z. B. Reiseplan oder Morning-Briefing) und proaktive Meldungen.
Werkzeugaufrufe und ihre Ergebnisse nicht - beim Fortsetzen bekommt das Sprachmodell das Gespräch als
reinen Text (ConversationMemory.restore_conversation, backend/assistant/base.py).

Ein Chat wird erst gespeichert, wenn der Nutzer darin etwas geschrieben hat; nur proaktive Meldungen
ergeben keinen eigenen Eintrag. Es bleiben höchstens max_chats Chats, die ältesten fallen weg.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import re
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from backend.assistant.commands import is_command

log = logging.getLogger(__name__)

TITLE_MAX_CHARS = 60
MAX_VIEW_CHARS = 2_000_000     # größere Ansichten (z. B. viele Kartenkacheln) werden nicht mitgespeichert
_CHAT_ID = re.compile(r"[0-9a-f]{32}")   # uuid4().hex - schützt auch vor Pfaden wie "../preferences"


@dataclass
class Chat:
    id: str
    created: str                  # ISO-Zeitpunkt, Ortszeit
    updated: str
    title: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)

    @property
    def has_user_message(self) -> bool:
        return any(message["role"] == "user" for message in self.messages)

    def summary(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title or "Neuer Chat", "updated": self.updated,
                "count": len(self.messages)}

    def dialogue(self) -> list[tuple[str, str]]:
        """Das Gespräch fürs Sprachmodell: (Rolle, Text) ohne feste Befehle ("hilfe", "modelle" …)
        und deren Antworten - die hat das Modell auch im laufenden Chat nie gesehen."""
        result: list[tuple[str, str]] = []
        skip_reply = False
        for message in self.messages:
            if message["role"] == "user":
                skip_reply = is_command(message["text"])
                if not skip_reply:
                    result.append(("user", message["text"]))
            elif message["role"] == "assistant":
                if skip_reply and not message.get("proactive"):
                    skip_reply = False
                    continue
                result.append(("assistant", message["text"]))
        return result


def chat_title(text: str) -> str:
    """Titel aus der ersten Nachricht des Nutzers: eine Zeile, höchstens TITLE_MAX_CHARS Zeichen."""
    title = " ".join(text.split())
    return title if len(title) <= TITLE_MAX_CHARS else title[:TITLE_MAX_CHARS - 1].rstrip() + "…"


def valid_chat_id(chat_id: Any) -> bool:
    return isinstance(chat_id, str) and bool(_CHAT_ID.fullmatch(chat_id))


class ChatStore:
    """Ein Chat pro Datei <id>.json im Ordner directory. Kaputte Dateien werden übersprungen."""

    def __init__(self, directory: Path, max_chats: int = 100):
        self.directory = directory
        self.max_chats = max_chats

    def _path(self, chat_id: str) -> Path:
        if not valid_chat_id(chat_id):
            raise ValueError(f"Ungültige Chat-ID: {chat_id!r}")
        return self.directory / f"{chat_id}.json"

    def load(self, chat_id: str) -> Chat:
        """Gespeicherter Chat; KeyError, wenn es ihn nicht (mehr) gibt."""
        path = self._path(chat_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Chat(id=chat_id, created=str(data["created"]), updated=str(data["updated"]),
                        title=str(data.get("title", "")), messages=_valid_messages(data.get("messages")))
        except FileNotFoundError:
            raise KeyError(chat_id) from None
        except (OSError, ValueError, KeyError, TypeError) as error:
            log.warning("Chat %s nicht lesbar: %s", path, error)
            raise KeyError(chat_id) from None

    def all(self) -> list[Chat]:
        """Alle lesbaren Chats, zuletzt geänderte zuerst."""
        chats = []
        for path in self.directory.glob("*.json"):
            if valid_chat_id(path.stem):
                try:
                    chats.append(self.load(path.stem))
                except KeyError:
                    continue
        return sorted(chats, key=lambda chat: chat.updated, reverse=True)

    def save(self, chat: Chat) -> None:
        """Atomar schreiben (erst eine Hilfsdatei, dann umbenennen) - ein Absturz hinterlässt keine halbe Datei."""
        path = self._path(chat.id)
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(chat), ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)
        self._prune(keep=chat.id)

    def delete(self, chat_id: str) -> bool:
        try:
            self._path(chat_id).unlink()
        except FileNotFoundError:
            return False
        return True

    def _prune(self, keep: str) -> None:
        for chat in self.all()[self.max_chats:]:
            if chat.id != keep:
                self.delete(chat.id)


def _valid_messages(messages: Any) -> list[dict[str, Any]]:
    if not isinstance(messages, list):
        raise ValueError("messages ist keine Liste")
    return [message for message in messages
            if isinstance(message, dict) and message.get("role") in ("user", "assistant")
            and isinstance(message.get("text"), str)]


class ChatHistory:
    """Der laufende Chat und das Archiv. Nicht thread-sicher: api.py ruft es unter einem Lock auf."""

    def __init__(self, store: ChatStore, clock: Callable[[], datetime.datetime] = datetime.datetime.now):
        self.store = store
        self.clock = clock
        self.current = self._fresh()

    def _now(self) -> str:
        return self.clock().isoformat(timespec="seconds")

    def _fresh(self) -> Chat:
        now = self._now()
        return Chat(id=uuid.uuid4().hex, created=now, updated=now)

    def start_new(self) -> Chat:
        """Neuer, leerer Chat; der bisherige ist schon gespeichert (sofern der Nutzer etwas geschrieben hat)."""
        self.current = self._fresh()
        return self.current

    def record_exchange(self, message: str, reply: dict[str, Any]) -> None:
        """Nachricht des Nutzers und die Antwort (wie presenter.present sie liefert) anhängen und speichern."""
        self._append(_entry("user", message, self._now()), save=False)
        self.record_reply(reply)

    def record_reply(self, reply: dict[str, Any]) -> None:
        """Antwort oder proaktive Meldung ({"text", "html"?, "view_button"?, "proactive"?, "title"?})."""
        entry = _entry("assistant", reply.get("text") or "", self._now())
        if reply.get("proactive"):
            entry["proactive"] = True
            entry["title"] = str(reply.get("title") or "Meldung")
        html = reply.get("html")
        if reply.get("view_button") and isinstance(html, str) and len(html) <= MAX_VIEW_CHARS:
            entry["html"] = html
            entry["view_button"] = str(reply["view_button"])
        self._append(entry)

    def _append(self, entry: dict[str, Any], save: bool = True) -> None:
        chat = self.current
        chat.messages.append(entry)
        chat.updated = entry["time"]
        if entry["role"] == "user" and not chat.title:
            chat.title = chat_title(entry["text"])
        if save and chat.has_user_message:
            try:
                self.store.save(chat)
            except OSError:   # z. B. Platte voll - der Chat läuft trotzdem weiter
                log.exception("Chat %s konnte nicht gespeichert werden", chat.id)

    def open(self, chat_id: str) -> Chat:
        """Gespeicherten Chat zum laufenden machen; KeyError, wenn es ihn nicht gibt."""
        if chat_id != self.current.id:
            self.current = self.store.load(chat_id)
        return self.current

    def delete(self, chat_id: str) -> bool:
        """Chat löschen. True, wenn es der laufende war - dann beginnt ein neuer."""
        self.store.delete(chat_id)
        if chat_id == self.current.id:
            self.start_new()
            return True
        return False

    def summaries(self) -> list[dict[str, Any]]:
        """Gespeicherte Chats fürs Popup, neueste zuerst; "current" markiert den laufenden."""
        return [{**chat.summary(), "current": chat.id == self.current.id} for chat in self.store.all()]


def _entry(role: str, text: str, time: str) -> dict[str, Any]:
    return {"role": role, "text": text, "time": time}
