"""Schnittstelle zu Werkzeugen, die das Sprachmodell nutzen kann.

ToolSpec entspricht einem MCP-Tool (name, description, inputSchema) und lässt
sich direkt in das "tools"-Format von Ollama übersetzen.

Ein ToolProvider ist entweder eine eigene Integration in backend/integrations/
(z. B. Google Calendar, OpenWeather) oder ein MCP-Client, der die Tools eines
MCP-Servers bereitstellt. CompositeToolProvider bündelt mehrere davon, sodass
ein Assistent alle seine Werkzeuge über einen einzigen ToolProvider sieht.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)   # JSON-Schema der Argumente


@dataclass(frozen=True)
class Attachment:
    """Datei, die ein Werkzeug mitliefert (MCP "resource_link"), z. B. ein Mail-Anhang.
    Das Modell sieht nur den Namen; der Chat zeigt sie zum Öffnen und Speichern an."""
    name: str
    uri: str                  # file:///C:/...
    mime_type: str = ""
    size: int | None = None


@dataclass(frozen=True)
class ToolResult:
    content: str
    is_error: bool = False
    attachments: tuple[Attachment, ...] = ()


@runtime_checkable
class ToolProvider(Protocol):
    def list_tools(self) -> list[ToolSpec]:
        """Alle verfügbaren Werkzeuge dieses Providers."""
        ...

    def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """Werkzeug ausführen und sein Ergebnis zurückgeben."""
        ...


class UnknownToolError(LookupError):
    """Kein Provider bietet ein Werkzeug mit diesem Namen an."""


class DuplicateToolError(ValueError):
    """Zwei Provider bieten ein Werkzeug mit demselben Namen an."""


class CompositeToolProvider:
    """Bündelt mehrere ToolProvider zu einem, z. B. Calendar + Wetter + Aktien für die
    Fähigkeit "morning". Aufrufe gehen an den Provider, der das Werkzeug anbietet."""

    def __init__(self, providers: Iterable[ToolProvider]):
        self._providers = list(providers)

    def list_tools(self) -> list[ToolSpec]:
        return [spec for spec, _ in self._index().values()]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        try:
            _, provider = self._index()[name]
        except KeyError:
            raise UnknownToolError(f"Unbekanntes Werkzeug: {name!r}") from None
        return provider.call_tool(name, arguments)

    def _index(self) -> dict[str, tuple[ToolSpec, ToolProvider]]:
        # Jedes Mal neu: MCP-Server können ihre Werkzeuge zur Laufzeit ändern.
        index: dict[str, tuple[ToolSpec, ToolProvider]] = {}
        for provider in self._providers:
            for spec in provider.list_tools():
                if spec.name in index:
                    raise DuplicateToolError(f"Werkzeug {spec.name!r} wird mehrfach angeboten")
                index[spec.name] = (spec, provider)
        return index
