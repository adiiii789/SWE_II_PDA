"""Einfache Werkzeuge ohne Abhängigkeiten - genutzt von pda_server.py und demo_server.py."""
from __future__ import annotations

import ast
import datetime
import operator

_WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")


def current_time() -> str:
    now = datetime.datetime.now()
    return f"{_WEEKDAYS[now.weekday()]}, {now:%d.%m.%Y}, {now:%H:%M} Uhr"


_OPERATORS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Pow: operator.pow, ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def _evaluate(node: ast.AST) -> float:
    # Nur Zahlen und Rechenzeichen - kein eval(), damit das Modell keinen Code ausführen kann.
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_evaluate(node.left), _evaluate(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_evaluate(node.operand))
    raise ValueError("nur Zahlen und + - * / ** % erlaubt")


def calculate(expression: str) -> str:
    return f"{expression} = {_evaluate(ast.parse(expression, mode='eval'))}"
