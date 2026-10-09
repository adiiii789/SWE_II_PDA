"""Kontextwissen und persönliche Präferenzen des Nutzers.

Beispiele: Wohnort (Wetter, Routen), bevorzugtes Verkehrsmittel, Aktien-Watchlist,
Lieblingsmusik, Uhrzeit des Morning-Briefings.

Nur Schnittstelle - noch keine Implementierung. Vorgesehen:
  - Speicherung, z. B. als JSON-Datei (Implementierung von PreferenceStore)
  - Bearbeitung "vorab grafisch per UI": ein Template mit Formular im Frontend
    plus Funktionen in backend/api.py, die get/set aufrufen
  - Zugriff der Assistenten über einen PreferenceStore, der ihnen beim
    Erzeugen übergeben wird (backend/assistant/__init__.py, _BACKENDS)
Werte müssen JSON-tauglich sein.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable


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
