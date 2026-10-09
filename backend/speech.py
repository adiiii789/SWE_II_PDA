"""Sprachliche Ein- und Ausgabe.

Nur Schnittstelle - noch keine Implementierung. Sprache läuft in Python, nicht im
Browser: Qt WebEngine bringt keine Spracherkennung mit. Mögliche Umsetzungen sind
lokale Bibliotheken für Spracherkennung (Speech-to-Text) und Sprachausgabe
(Text-to-Speech).

Anbindung ans Frontend später über Funktionen in backend/api.py, z. B. ein
Mikrofon-Knopf im Chat, der listen() aufruft und den Text an den Assistenten
gibt. listen() und speak() dürfen blockieren - Bridge-Aufrufe laufen ohnehin in
einem Hintergrund-Thread.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SpeechInput(Protocol):
    def listen(self) -> str:
        """Spracheingabe aufnehmen und als Text zurückgeben (leer, wenn nichts erkannt wurde)."""
        ...


@runtime_checkable
class SpeechOutput(Protocol):
    def speak(self, text: str) -> None:
        """Text vorlesen."""
        ...
