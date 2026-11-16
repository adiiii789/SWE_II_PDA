"""Skill: was eine Fähigkeit dem Assistenten mitgibt (Konvention in skills/__init__.py)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from backend.assistant.tools import CompositeToolProvider, ToolProvider


@dataclass(frozen=True)
class Skill:
    name: str
    instructions: str                                   # wird an die Systemanweisung angehängt
    tools: ToolProvider = field(default_factory=lambda: CompositeToolProvider([]))
    # Autonomer Auslöser, z. B. Erinnerung: startet beim App-Start und gibt eine Funktion
    # zum Beenden zurück (oder None). Antworten gehen mit backend.presenter.push in den Chat.
    start: Callable[[], Callable[[], None] | None] | None = None
