"""Claude über das eigene Claude-Abo (backend/assistant/claude_code.py).

Claude Code führt die Werkzeugschleife selbst. Jeder Aufruf läuft trotzdem über _call_tool:
Abgeschaltete und interne Werkzeuge bleiben gesperrt, riskante brauchen die Zustimmung des Nutzers.
Die Aufrufe landen wie bei den anderen Anbietern im Verlauf, in der Anzeige oben und bei den Anhängen.
"""
from __future__ import annotations

from backend.assistant.claude_code import MODELS, ClaudeCodeModel
from backend.assistant.llm import ChatMessage, ToolCall
from backend.assistant.model_assistant import MAX_TOOL_RESULT_CHARS, ModelAssistant
from backend.assistant.tools import ToolResult

MODEL_PREFERENCE = "claude_model"


class ClaudeCodeAssistant(ModelAssistant):
    model: ClaudeCodeModel
    provider = "Claude"
    model_preference = MODEL_PREFERENCE
    model_commands = {
        "modelle": "Zeigt die Claude-Modelle",
        "modell <name>": f"Wechselt das Sprachmodell, z. B. modell {MODELS[0]}",
    }
    model_hint = ("Claude läuft über die Claude-Code-Anmeldung dieses Rechners und zählt auf dein Claude-Abo. "
                  "Chatverlauf und verwendete Werkzeugergebnisse gehen an Anthropic.")
    no_model_hint = "Wähle ein Claude-Modell aus."
    unknown_model_message = "Claude-Modell {name!r} steht nicht zur Auswahl"

    def _run(self, tool_log: list[tuple[ToolCall, ToolResult]]) -> str:
        tools = self._offered_tools()
        system = self._system_message([tool.name for tool in tools])
        messages = [system, *self.history]

        def call_tool(name: str, arguments: dict) -> ToolResult:
            call = ToolCall(name, arguments, f"call_{len(tool_log) + 1}")
            result = self._call_tool(call)
            tool_log.append((call, result))
            content = ("Fehler: " if result.is_error else "") + result.content[:MAX_TOOL_RESULT_CHARS]
            self.history.append(ChatMessage("assistant", "", (call,)))
            self.history.append(ChatMessage("tool", content, tool_name=name, tool_call_id=call.id))
            return ToolResult(content, result.is_error)

        text = self.model.run(messages, tools, call_tool, self.max_tool_rounds)
        self.history.append(ChatMessage("assistant", text))
        return text

    def _ensure_model(self) -> bool:
        if not self.model.name:
            saved = self.preferences.get(self.model_preference)
            self.model.name = (saved if isinstance(saved, str) and saved in self.model.selectable()
                               else self.model.default_name)
        return True
