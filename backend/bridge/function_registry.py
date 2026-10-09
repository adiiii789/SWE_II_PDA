"""Sammelt die öffentlichen Funktionen eines Moduls und ruft sie per Name auf.

Bewusst ohne Qt-Abhängigkeit, damit die Logik einfach testbar bleibt.
"""
from __future__ import annotations

import inspect
from collections.abc import Callable
from types import ModuleType
from typing import Any


class UnknownFunctionError(LookupError):
    """Das Frontend hat eine Funktion aufgerufen, die es nicht gibt."""


class FunctionRegistry:
    def __init__(self, functions: dict[str, Callable[..., Any]]):
        self._functions = dict(functions)

    @classmethod
    def from_module(cls, module: ModuleType) -> FunctionRegistry:
        """Alle im Modul selbst definierten Funktionen ohne "_" am Anfang (keine Importe)."""
        return cls({
            name: obj for name, obj in vars(module).items()
            if inspect.isfunction(obj)
            and obj.__module__ == module.__name__
            and not name.startswith("_")
        })

    @property
    def names(self) -> list[str]:
        return sorted(self._functions)

    def call(self, name: str, args: list[Any]) -> Any:
        try:
            func = self._functions[name]
        except KeyError:
            raise UnknownFunctionError(f"Unbekannte Funktion: {name}") from None
        return func(*args)
