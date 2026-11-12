"""Claude über die Claude-Code-Anmeldung dieses Rechners (Claude-Abo, kein API-Schlüssel).

Läuft über das Paket claude-agent-sdk (requirements-claude.txt), das Claude Code als Unterprozess
startet. Angemeldet wird einmal mit Claude Code selbst; im Projekt liegt weder Schlüssel noch Token.
Wer den Anbieter nutzt, braucht also ein eigenes Claude-Konto.

Claude Code läuft dabei abgeschottet:
  - keine eingebauten Werkzeuge (Bash, Dateien, Web), nur die Werkzeuge des Assistenten
  - keine Einstellungen, Hooks, CLAUDE.md oder MCP-Server des Nutzers, kein gespeicherter Verlauf
  - ANTHROPIC_API_KEY wird ausgeblendet, damit immer das Abo zahlt und nicht ein API-Konto
  - Texte gehen wörtlich durch (verbatim_prompts): "@pfad" in einer Mail liest keine lokale Datei

Anders als bei Gemini und Ollama steuert Claude Code die Werkzeugschleife selbst. Jeder Aufruf
geht über den Rückruf call_tool an den Assistenten, damit Zustimmung und Einstellungen gelten
(ClaudeCodeAssistant). Den Verlauf führt weiterhin der Assistent; er geht als Text mit.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from backend.assistant.llm import ChatMessage, LanguageModelError, ModelInfo, ModelResponse
from backend.assistant.tools import ToolResult, ToolSpec

MODELS = ("sonnet", "haiku", "opus")   # Aliasse von Claude Code, jeweils das aktuelle Modell der Reihe
SERVER = "eve"                         # Claude sieht die Werkzeuge als mcp__eve__<name>
INSTALL_HELP = ('Für Claude fehlt das Paket claude-agent-sdk. Installiere es mit '
                '"pip install -r requirements-claude.txt".')
LOGIN_HELP = ('Claude Code ist auf diesem Rechner nicht mit einem Claude-Konto angemeldet. '
              'Starte im Terminal "claude" und melde dich mit "/login" an.')

ToolRunner = Callable[[str, dict[str, Any]], ToolResult]


class ClaudeCodeError(LanguageModelError):
    """Claude Code konnte die Anfrage nicht beantworten."""


class ClaudeCodeModel:
    def __init__(self, name: str, work_dir: Path, timeout: float, effort: str = "medium"):
        self.name = ""
        self.default_name = name or MODELS[0]
        self.work_dir = work_dir   # leerer Ordner: kein Projekt-CLAUDE.md, keine Projektdateien
        self.timeout = timeout
        self.effort = effort

    def available_models(self) -> list[ModelInfo]:
        return [ModelInfo(name, supports_tools=True, cloud=True) for name in self.selectable()]

    def selectable(self) -> list[str]:
        return list(dict.fromkeys((self.default_name, *MODELS)))

    def chat(self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec] = ()) -> ModelResponse:
        """Antwort ohne Werkzeuge (proaktive Meldungen, Wächter). Mit Werkzeugen: run()."""
        if tools:
            raise ClaudeCodeError("Werkzeuge laufen bei Claude Code über run().")
        return ModelResponse(ChatMessage("assistant", self.run(messages)))

    def run(self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec] = (),
            call_tool: ToolRunner | None = None, max_rounds: int = 5) -> str:
        """Ganze Runde samt Werkzeugaufrufen; gibt den Antworttext zurück."""
        sdk = _sdk()
        if tools and call_tool is None:
            raise ClaudeCodeError("Werkzeuge brauchen einen Rückruf call_tool.")
        self.work_dir.mkdir(parents=True, exist_ok=True)
        server_tools = [sdk.SdkMcpTool(tool.name, tool.description,
                                       tool.input_schema or {"type": "object", "properties": {}},
                                       _handler(tool.name, call_tool))
                        for tool in tools]
        options = sdk.ClaudeAgentOptions(
            model=self.name or self.default_name,
            system_prompt="\n\n".join(message.content for message in messages if message.role == "system"),
            tools=[],                                   # keine eingebauten Werkzeuge
            mcp_servers={SERVER: sdk.create_sdk_mcp_server(SERVER, tools=server_tools)} if server_tools else {},
            strict_mcp_config=True,                     # keine MCP-Server oder Connectors des Nutzers
            allowed_tools=[f"mcp__{SERVER}__{tool.name}" for tool in tools],
            permission_mode="dontAsk",                  # alles andere ablehnen statt nachfragen
            setting_sources=[],
            skills=[],
            cwd=self.work_dir,
            max_turns=max_rounds + 1,
            effort=self.effort,
            verbatim_prompts=True,
            env={"ANTHROPIC_API_KEY": ""},
            extra_args={"no-session-persistence": None},
        )
        prompt = _transcript([message for message in messages if message.role != "system"])
        try:
            import anyio
            result = anyio.run(_ask, sdk, prompt, options, self.timeout)
        except TimeoutError:
            raise ClaudeCodeError("Claude hat nicht rechtzeitig geantwortet.") from None
        except sdk.CLINotFoundError:
            raise ClaudeCodeError("Claude Code ließ sich nicht starten. Installiere claude-agent-sdk neu.") from None
        except sdk.ClaudeSDKError as error:
            raise ClaudeCodeError(_failure(str(error))) from None
        return _answer(result)


def _sdk() -> Any:
    try:
        import claude_agent_sdk
    except ImportError:
        raise ClaudeCodeError(INSTALL_HELP) from None
    return claude_agent_sdk


def _handler(name: str, call_tool: ToolRunner | None):
    async def handle(arguments: dict[str, Any]) -> dict[str, Any]:
        import anyio
        # Werkzeuge blockieren (MCP-Server, Google); im Thread hält das Claude Code nicht auf.
        result = await anyio.to_thread.run_sync(call_tool, name, dict(arguments))
        return {"content": [{"type": "text", "text": result.content or "(kein Ergebnis)"}],
                "is_error": result.is_error}
    return handle


async def _ask(sdk: Any, prompt: str, options: Any, timeout: float) -> Any:
    import anyio
    result = None
    error = None
    with anyio.fail_after(timeout):
        async for message in sdk.query(prompt=prompt, options=options):
            if isinstance(message, sdk.AssistantMessage) and message.error:
                error = message.error
            elif isinstance(message, sdk.ResultMessage):
                result = message
    if error:
        raise ClaudeCodeError(_ERRORS.get(error, _ERRORS["unknown"]))
    return result


_ERRORS = {
    "authentication_failed": LOGIN_HELP,
    "billing_error": "Dein Claude-Konto hat dafür gerade kein Kontingent. Prüfe dein Abo.",
    "rate_limit": "Das Nutzungslimit deines Claude-Abos ist erreicht. Versuch es später noch einmal.",
    "invalid_request": "Claude hat die Anfrage abgelehnt. Prüfe das gewählte Modell.",
    "server_error": "Claude ist gerade nicht erreichbar.",
    "unknown": "Claude hat mit einem unbekannten Fehler geantwortet.",
}


def _answer(result: Any) -> str:
    if result is None:
        raise ClaudeCodeError("Claude Code hat keine Antwort geliefert.")
    if result.subtype == "error_max_turns":
        return "Ich habe zu viele Werkzeuge nacheinander aufgerufen und breche ab. Versuch es bitte genauer."
    if result.is_error:
        raise ClaudeCodeError(_failure(result.result or " ".join(result.errors or ())))
    text = (result.result or "").strip()
    if not text:
        raise ClaudeCodeError("Claude hat keine verwendbare Antwort geliefert.")
    return text


def _failure(detail: str) -> str:
    lowered = detail.lower()
    if "login" in lowered or "logged in" in lowered or "authenticat" in lowered:
        return LOGIN_HELP
    if "limit" in lowered:
        return _ERRORS["rate_limit"]
    return "Claude Code ist mit einem Fehler beendet worden."


def _transcript(messages: Sequence[ChatMessage]) -> str:
    """Bisherigen Verlauf und neue Nachricht als einen Text.

    Claude Code speichert hier keine Sitzung; der Assistent führt den Verlauf (gekürzt, mit "neu"
    leerbar) und gibt ihn bei jeder Anfrage mit. Werkzeugaufrufe stehen mit Argumenten darin, damit
    Claude einen bestätigten Aufruf genau so wiederholen kann.
    """
    if not messages:
        return ""
    *earlier, last = messages
    if not earlier and last.role == "user":
        return last.content
    lines = []
    for message in earlier:
        if message.role == "user":
            lines.append(f"Nutzer: {message.content}")
        elif message.role == "tool":
            lines.append(f"Ergebnis von {message.tool_name}: {message.content}")
        else:
            if message.content:
                lines.append(f"Assistent: {message.content}")
            lines.extend(f"Assistent ruft {call.name} auf mit "
                         f"{json.dumps(call.arguments, ensure_ascii=False, sort_keys=True)}"
                         for call in message.tool_calls)
    if last.role == "user":
        current = f"Neue Nachricht des Nutzers:\n{last.content}"
    else:
        lines.append(f"Assistent: {last.content}")
        current = "Antworte auf den Verlauf."
    return "Bisheriger Gesprächsverlauf:\n<verlauf>\n" + "\n".join(lines) + "\n</verlauf>\n\n" + current
