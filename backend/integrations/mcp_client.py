"""MCPToolProvider: stellt die Werkzeuge eines MCP-Servers als ToolProvider bereit.

MCP (Model Context Protocol) über stdio: Der Server ist ein eigenes Programm,
das wir als Unterprozess starten. Beide Seiten schicken sich JSON-RPC-Nachrichten,
eine pro Zeile, über stdin/stdout:

  wir  → initialize                 Server ← Protokollversion, Fähigkeiten
  wir  → notifications/initialized
  wir  → tools/list                 Server ← [{name, description, inputSchema}]
  wir  → tools/call {name, args}    Server ← {content: [...], isError}

Welche Server laufen, steht in mcp_servers.json (siehe load_mcp_servers).
Bewusst ohne MCP-SDK: Das SDK ist asynchron, die Bridge ruft aber synchron aus
einem Hintergrund-Thread auf - dafür reicht dieser kleine Client.
"""
from __future__ import annotations

import atexit
import json
import logging
import os
import queue
import shutil
import subprocess
import sys
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from backend.assistant.tools import Attachment, ToolResult, ToolSpec

log = logging.getLogger(__name__)

PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "personal-digital-agent", "version": "1.0"}


class MCPError(RuntimeError):
    """Server nicht startbar, abgestürzt, zu langsam oder mit Fehler geantwortet."""


class MCPToolProvider:
    """Erfüllt ToolProvider. Der Server wird beim ersten Zugriff gestartet und bei
    einem Absturz beim nächsten Zugriff neu gestartet."""

    def __init__(self, name: str, command: str, args: list[str] | None = None,
                 env: Mapping[str, str] | None = None, cwd: Path | None = None, timeout: float = 60):
        self.name = name
        self.command = command
        self.args = list(args or [])
        self.env = dict(env or {})
        self.cwd = cwd
        self.timeout = timeout
        self._process: subprocess.Popen | None = None
        self._responses: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._next_id = 0
        self._tools: list[ToolSpec] | None = None
        self._lock = threading.RLock()
        atexit.register(self.close)   # Server beim Beenden der App mit beenden

    # --- ToolProvider ------------------------------------------------------------
    def list_tools(self) -> list[ToolSpec]:
        """Werkzeuge des Servers. Ist er nicht erreichbar, gibt es keine Werkzeuge
        (ein defekter Server soll nicht den ganzen Assistenten lahmlegen)."""
        with self._lock:
            if self._tools is None:
                try:
                    self._tools = self._fetch_tools()
                except MCPError as error:
                    log.warning("MCP-Server %r: %s", self.name, error)
                    return []
            return list(self._tools)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        with self._lock:
            try:
                result = self._request("tools/call", {"name": name, "arguments": arguments})
            except MCPError as error:
                return ToolResult(str(error), is_error=True)
            return ToolResult(_content_to_text(result), bool(result.get("isError")), _attachments(result))

    def close(self) -> None:
        with self._lock:
            process, self._process = self._process, None
            self._tools = None
            if process is None:
                return
            try:
                process.stdin.close()
                process.wait(timeout=2)
            except Exception:
                process.kill()

    # --- Protokoll -----------------------------------------------------------------
    def _fetch_tools(self) -> list[ToolSpec]:
        tools: list[ToolSpec] = []
        cursor = None
        while True:
            result = self._request("tools/list", {"cursor": cursor} if cursor else {})
            for tool in result.get("tools", []):
                tools.append(ToolSpec(tool["name"], tool.get("description") or "",
                                      tool.get("inputSchema") or {"type": "object", "properties": {}}))
            cursor = result.get("nextCursor")
            if not cursor:
                return tools

    def _ensure_started(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return
        if self._process is not None:
            log.warning("MCP-Server %r ist beendet, starte neu", self.name)
            self._process = None
            self._tools = None
        self._start()
        try:
            self._exchange("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                          "clientInfo": CLIENT_INFO})
            self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        except MCPError:
            self.close()   # halb initialisierten Server nicht weiterverwenden
            raise

    def _start(self) -> None:
        command = sys.executable if self.command == "python" else (shutil.which(self.command) or self.command)
        try:
            self._process = subprocess.Popen(
                [command, *self.args], cwd=self.cwd, env={**os.environ, **self.env},
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                encoding="utf-8", errors="replace", bufsize=1,
                # Tray-App ohne Konsole: kein schwarzes Fenster für den Server öffnen.
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as error:
            self._process = None
            raise MCPError(f"Start von {self.command!r} fehlgeschlagen: {error}") from None
        self._responses = queue.Queue()
        threading.Thread(target=self._read_stdout, args=(self._process, self._responses),
                         name=f"mcp-{self.name}-out", daemon=True).start()
        threading.Thread(target=self._read_stderr, args=(self._process,),
                         name=f"mcp-{self.name}-err", daemon=True).start()

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._ensure_started()
        return self._exchange(method, params)

    def _exchange(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._next_id += 1
        request_id = self._next_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        while True:
            try:
                message = self._responses.get(timeout=self.timeout)
            except queue.Empty:
                raise MCPError(f"keine Antwort auf {method} nach {self.timeout:g} s") from None
            if message is None:
                raise MCPError(f"Server wurde beendet (während {method})")
            if "method" in message:
                self._handle_server_message(message)
            elif message.get("id") == request_id:
                if "error" in message:
                    raise MCPError(f"{method}: {message['error'].get('message', message['error'])}")
                return message.get("result") or {}

    def _handle_server_message(self, message: dict[str, Any]) -> None:
        if message["method"] == "notifications/tools/list_changed":
            self._tools = None
        if "id" not in message:
            return   # sonstige Benachrichtigung (z. B. Logging)
        if message["method"] == "ping":
            self._send({"jsonrpc": "2.0", "id": message["id"], "result": {}})
        else:   # Anfragen des Servers an uns (sampling, roots …) unterstützen wir nicht
            self._send({"jsonrpc": "2.0", "id": message["id"],
                        "error": {"code": -32601, "message": f"Nicht unterstützt: {message['method']}"}})

    def _send(self, message: dict[str, Any]) -> None:
        try:
            self._process.stdin.write(json.dumps(message) + "\n")
            self._process.stdin.flush()
        except (OSError, ValueError) as error:
            raise MCPError(f"Senden fehlgeschlagen: {error}") from None

    # --- Lese-Threads ----------------------------------------------------------------
    def _read_stdout(self, process: subprocess.Popen, responses: queue.Queue) -> None:
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                responses.put(json.loads(line))
            except json.JSONDecodeError:
                log.debug("MCP-Server %r (keine JSON-Zeile): %s", self.name, line)
        responses.put(None)   # Server beendet

    def _read_stderr(self, process: subprocess.Popen) -> None:
        for line in process.stderr:
            log.debug("MCP-Server %r: %s", self.name, line.rstrip())


def _content_to_text(result: dict[str, Any]) -> str:
    """MCP-Ergebnis (Liste von Inhaltsblöcken) als Text für das Sprachmodell."""
    parts = []
    for block in result.get("content", []):
        if block.get("type") == "text":
            parts.append(block.get("text", ""))
        elif block.get("type") == "resource" and "text" in block.get("resource", {}):
            parts.append(block["resource"]["text"])
        elif block.get("type") == "resource_link":
            parts.append(f"[Datei im Chat angehängt: {block.get('name', '')}]")
        else:
            parts.append(f"[{block.get('type', 'unbekannt')}-Inhalt nicht darstellbar]")
    if not parts and "structuredContent" in result:
        parts.append(json.dumps(result["structuredContent"], ensure_ascii=False))
    return "\n".join(parts)


def _attachments(result: dict[str, Any]) -> tuple[Attachment, ...]:
    """Mitgelieferte Dateien ("resource_link"-Blöcke, z. B. Mail-Anhänge) für den Chat."""
    return tuple(Attachment(block.get("name", ""), block["uri"], block.get("mimeType", ""), block.get("size"))
                 for block in result.get("content", [])
                 if block.get("type") == "resource_link" and isinstance(block.get("uri"), str))


def load_mcp_servers(path: Path, base_dir: Path) -> list[MCPToolProvider]:
    """MCP-Server aus einer JSON-Datei, im selben Format wie bei Claude Desktop & Co.:

    {"mcpServers": {"name": {"command": "...", "args": [...], "env": {...}}}}

    Zusätzlich optional: "cwd" (relativ zu base_dir) und "disabled": true.
    Relative Pfade in args beziehen sich auf base_dir (Arbeitsordner des Servers).
    """
    if not path.exists():
        return []
    servers = json.loads(path.read_text(encoding="utf-8")).get("mcpServers", {})
    return [
        MCPToolProvider(name, entry["command"], entry.get("args"), entry.get("env"),
                        base_dir / entry.get("cwd", "."))
        for name, entry in servers.items() if not entry.get("disabled")
    ]
