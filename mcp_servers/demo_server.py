"""MCP-Server (stdio) ohne SDK - zeigt das Protokoll und dient den Tests als Gegenpart.

Werkzeuge:
  get_current_time   aktuelles Datum und Uhrzeit
  calculate          rechnet einen arithmetischen Ausdruck aus

Der eigentliche Server des Projekts ist pda_server.py (offizielles MCP-SDK).
Dieser hier zeigt, wie wenig das Protokoll selbst verlangt: eine
JSON-RPC-Nachricht pro Zeile auf stdin/stdout. In mcp_servers.json ist er
abgeschaltet ("disabled": true), weil pda_server.py dieselben Werkzeuge anbietet.
"""
from __future__ import annotations

import json
import sys

import basic_tools

TOOLS = [
    {
        "name": "get_current_time",
        "description": "Returns the current local date, weekday and time.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "calculate",
        "description": "Evaluates an arithmetic expression with + - * / ** % and parentheses, e.g. '(3 + 4) * 2'.",
        "inputSchema": {
            "type": "object",
            "properties": {"expression": {"type": "string", "description": "The arithmetic expression"}},
            "required": ["expression"],
        },
    },
]

HANDLERS = {
    "get_current_time": lambda arguments: basic_tools.current_time(),
    "calculate": lambda arguments: basic_tools.calculate(str(arguments.get("expression", ""))),
}


def handle(request: dict) -> dict | None:
    """Antwort auf eine JSON-RPC-Nachricht; None bei Benachrichtigungen (ohne id)."""
    method, params = request.get("method"), request.get("params") or {}
    if "id" not in request:
        return None
    if method == "initialize":
        result = {"protocolVersion": params.get("protocolVersion", "2025-06-18"),
                  "capabilities": {"tools": {}},
                  "serverInfo": {"name": "pda-demo", "version": "1.0"}}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call" and params.get("name") in HANDLERS:
        try:
            text, is_error = HANDLERS[params["name"]](params.get("arguments") or {}), False
        except Exception as error:   # Fehler gehen als Ergebnis ans Modell, damit es reagieren kann
            text, is_error = f"Fehler: {error}", True
        result = {"content": [{"type": "text", "text": text}], "isError": is_error}
    else:
        return {"jsonrpc": "2.0", "id": request["id"],
                "error": {"code": -32601, "message": f"Unbekannt: {method} {params.get('name', '')}".strip()}}
    return {"jsonrpc": "2.0", "id": request["id"], "result": result}


def main() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        response = handle(json.loads(line))
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
