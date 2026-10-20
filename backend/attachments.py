"""Dateien im Chat: Werkzeuge liefern sie als Attachment (backend/assistant/tools.py) mit,
z. B. Mail-Anhänge aus mcp_servers/inbox.py. Das Popup kann sie öffnen oder speichern.

Das Frontend bekommt nie einen Pfad, nur eine zufällige ID (register). Mit der ID ruft es
api.open_attachment bzw. api.save_attachment auf.

Sicherheit:
  - Angenommen werden nur Dateien in base_dir (config.ATTACHMENT_DIR). Ein anderer
    MCP-Server kann so nicht beliebige Dateien des Rechners zum Öffnen anbieten.
  - Ausführbare Dateien (.exe, .bat, .js …) lassen sich nur speichern, nicht direkt
    öffnen - ein Klick im Chat würde sonst fremden Code aus einer Mail starten.
"""
from __future__ import annotations

import logging
import os
import secrets
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import url2pathname

from backend.assistant.tools import Attachment

log = logging.getLogger(__name__)

BLOCKED_SUFFIXES = frozenset({
    ".exe", ".com", ".scr", ".pif", ".msi", ".msp", ".bat", ".cmd", ".ps1", ".psm1", ".vbs", ".vbe",
    ".js", ".jse", ".wsf", ".wsh", ".hta", ".cpl", ".jar", ".lnk", ".url", ".reg", ".inf", ".scf",
    ".dll", ".sys", ".appx", ".msix", ".application", ".gadget", ".iso", ".img", ".vhd", ".vhdx",
    ".docm", ".xlsm", ".pptm", ".dotm", ".xltm", ".xlam", ".ppam",   # Office mit Makros
})


class AttachmentError(ValueError):
    """Unbekannte ID, Datei nicht mehr vorhanden oder Öffnen nicht erlaubt."""


@dataclass(frozen=True)
class StoredAttachment:
    id: str
    path: Path
    name: str
    mime_type: str
    size: int

    @property
    def can_open(self) -> bool:
        return self.path.suffix.lower() not in BLOCKED_SUFFIXES

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "mime_type": self.mime_type,
                "size": self.size, "can_open": self.can_open}


def _open_with_default_app(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)   # noqa: S606  # öffnet mit dem Standardprogramm, wie ein Doppelklick
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])


class AttachmentStore:
    def __init__(self, base_dir: Path, download_dir: Path,
                 opener: Callable[[Path], None] = _open_with_default_app):
        self.base_dir = base_dir
        self.download_dir = download_dir
        self.opener = opener
        self._lock = threading.Lock()   # die Bridge ruft aus Hintergrund-Threads auf
        self._by_id: dict[str, StoredAttachment] = {}
        self._id_by_path: dict[Path, str] = {}

    def register(self, attachment: Attachment) -> dict[str, Any] | None:
        """Datei für den Chat freigeben: {"id", "name", "mime_type", "size", "can_open"};
        None, wenn sie nicht in base_dir liegt oder nicht existiert."""
        path = _file_path(attachment.uri)
        if path is None or not path.is_file() or not path.is_relative_to(self.base_dir.resolve()):
            log.warning("Anhang %r abgelehnt: %s liegt nicht in %s", attachment.name, attachment.uri, self.base_dir)
            return None
        with self._lock:
            known = self._id_by_path.get(path)
            stored = StoredAttachment(known or secrets.token_hex(8), path, attachment.name or path.name,
                                      attachment.mime_type, path.stat().st_size)
            self._by_id[stored.id] = stored
            self._id_by_path[path] = stored.id
        return stored.to_dict()

    def open(self, attachment_id: str) -> str:
        stored = self._get(attachment_id)
        if not stored.can_open:
            raise AttachmentError(f"{stored.name} ist eine ausführbare Datei und wird aus Sicherheitsgründen "
                                  "nicht direkt geöffnet. Du kannst sie speichern.")
        self.opener(stored.path)
        return stored.name

    def save(self, attachment_id: str) -> str:
        """Kopie in den Download-Ordner; vorhandene Dateien werden nicht überschrieben. Gibt den Pfad zurück."""
        stored = self._get(attachment_id)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        # Name der Datei auf der Platte, nicht der angezeigte: Der kommt vom Werkzeug und könnte
        # Zeichen enthalten, die Windows nicht erlaubt, oder einen Pfad wie "..\x".
        target = _free_path(self.download_dir / stored.path.name)
        shutil.copyfile(stored.path, target)
        return str(target)

    def _get(self, attachment_id: str) -> StoredAttachment:
        with self._lock:
            stored = self._by_id.get(str(attachment_id))
        if stored is None:
            raise AttachmentError("Unbekannter Anhang")
        if not stored.path.is_file():
            raise AttachmentError(f"{stored.name} ist nicht mehr vorhanden - lass die Mail bitte erneut öffnen")
        return stored


def _file_path(uri: str) -> Path | None:
    parsed = urlparse(uri)
    if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
        return None
    return Path(url2pathname(parsed.path)).resolve()   # url2pathname dekodiert %20 & Co. selbst


def _free_path(path: Path) -> Path:
    """plan.pdf, sonst plan (1).pdf, plan (2).pdf …"""
    candidate, number = path, 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} ({number}){path.suffix}")
        number += 1
    return candidate
