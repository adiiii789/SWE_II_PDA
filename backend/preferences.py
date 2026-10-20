"""Kontextwissen und persönliche Präferenzen des Nutzers.

Beispiele: Wohnort (Wetter, Routen), bevorzugtes Verkehrsmittel, Aktien-Watchlist,
Lieblingsmusik, Uhrzeit des Morning-Briefings.

Aufbau:
  - Speicherung als JSON-Datei: JsonPreferenceStore (config.PREFERENCES_FILE).
    Heute steht dort z. B. das gewählte Ollama-Modell ("ollama_model").
  - Bearbeitung "vorab grafisch per UI": ein Template mit Formular im Frontend
    plus Funktionen in backend/api.py, die get/set aufrufen (noch offen)
  - Zugriff der Assistenten über einen PreferenceStore, der ihnen beim
    Erzeugen übergeben wird (backend/assistant/__init__.py, _BACKENDS)
Werte müssen JSON-tauglich sein.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

log = logging.getLogger(__name__)


@runtime_checkable
class PreferenceStore(Protocol):
    def get(self, key: str, default: Any = None) -> Any:
        """Wert einer Präferenz oder default, wenn sie nicht gesetzt ist."""
        ...

    def set(self, key: str, value: Any) -> None:
        """Präferenz setzen und dauerhaft speichern."""
        ...

    def all(self) -> Mapping[str, Any]:
        """Alle Präferenzen, z. B. als Kontext für das Sprachmodell oder für die Einstellungs-UI."""
        ...


class JsonPreferenceStore:
    """PreferenceStore in einer JSON-Datei. Eine kaputte oder fehlende Datei zählt als leer."""

    def __init__(self, path: Path):
        self.path = path
        try:
            self._values: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self._values = {}
        except (OSError, ValueError) as error:
            log.warning("Präferenzen %s nicht lesbar (%s), starte leer", path, error)
            self._values = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._values[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._values, ensure_ascii=False, indent=2), encoding="utf-8")

    def all(self) -> Mapping[str, Any]:
        return dict(self._values)
