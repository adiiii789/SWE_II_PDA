"""Claude über das Claude-Abo: Abschottung, Werkzeuge über den Assistenten, Verlauf, Fehler.

Ohne Claude Code: Ein nachgebautes Modul ersetzt claude_agent_sdk.
"""
import sys
import types
from dataclasses import dataclass, field
from typing import Any

import anyio
import pytest

from backend.assistant.claude_code import INSTALL_HELP, LOGIN_HELP, MODELS, ClaudeCodeModel, _transcript
from backend.assistant.claude_code_assistant import ClaudeCodeAssistant
from backend.assistant.llm import ChatMessage, ToolCall
from backend.assistant.model_picker import ModelPicker
from backend.assistant.tools import ToolResult, ToolSpec


class ClaudeSDKError(Exception):
    pass


class CLINotFoundError(ClaudeSDKError):
    pass


@dataclass
class AssistantMessage:
    content: list = field(default_factory=list)
    model: str = "claude"
    error: str | None = None


@dataclass
class ResultMessage:
    subtype: str = "success"
    is_error: bool = False
    result: str | None = None
    errors: list | None = None


@dataclass
class SdkMcpTool:
    name: str
    description: str
    input_schema: dict
    handler: Any


class FakeSdk(types.ModuleType):
    """Spielt eine Sitzung ab: ruft die geplanten Werkzeuge auf und liefert dann die Nachrichten."""

    def __init__(self, *messages, tool_calls=()):
        super().__init__("claude_agent_sdk")
        self.messages = list(messages) or [ResultMessage(result="Antwort.")]
        self.tool_calls = list(tool_calls)
        self.options = []
        self.prompts = []
        self.tool_results = []
        self.ClaudeSDKError, self.CLINotFoundError = ClaudeSDKError, CLINotFoundError
        self.AssistantMessage, self.ResultMessage, self.SdkMcpTool = AssistantMessage, ResultMessage, SdkMcpTool

    def ClaudeAgentOptions(self, **options):   # noqa: N802 - Name wie im SDK
        self.options.append(options)
        return options

    def create_sdk_mcp_server(self, name, tools):
        return {"name": name, "tools": {tool.name: tool for tool in tools}}

    async def query(self, prompt, options):
        self.prompts.append(prompt)
        for name, arguments in self.tool_calls:
            tool = options["mcp_servers"]["eve"]["tools"][name]
            self.tool_results.append(await tool.handler(arguments))
        for message in self.messages:
            if isinstance(message, Exception):
                raise message
            yield message


@pytest.fixture
def install(monkeypatch):
    def install_sdk(*messages, tool_calls=()):
        sdk = FakeSdk(*messages, tool_calls=tool_calls)
        monkeypatch.setitem(sys.modules, "claude_agent_sdk", sdk)
        return sdk
    return install_sdk


class Tools:
    def __init__(self):
        self.calls = []

    def list_tools(self):
        return [ToolSpec("echo", "Gibt den Text zurück", {"type": "object"}),
                ToolSpec("delete_task", "Löscht eine Aufgabe", {"type": "object"}),
                ToolSpec("watch_inbox", "Intern")]

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return ToolResult(f"{name}: {arguments}", data={"kind": "test"} if name == "echo" else None)


class Preferences:
    def __init__(self, **values):
        self.values = dict(values)

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value

    def all(self):
        return dict(self.values)


def assistant(tmp_path, preferences=None):
    model = ClaudeCodeModel("", tmp_path / "claude", timeout=5)
    return ClaudeCodeAssistant(model, Tools(), preferences or Preferences())


def test_session_is_isolated_and_uses_the_subscription(tmp_path, install):
    sdk = install()
    eve = assistant(tmp_path)

    assert eve.reply("Hallo").text == "Antwort."
    options = sdk.options[0]
    assert options["model"] == MODELS[0]
    assert options["tools"] == []
    assert options["strict_mcp_config"] and options["setting_sources"] == [] and options["skills"] == []
    assert options["permission_mode"] == "dontAsk"
    assert options["verbatim_prompts"] is True
    assert options["env"] == {"ANTHROPIC_API_KEY": ""}
    assert "no-session-persistence" in options["extra_args"]
    assert options["cwd"] == tmp_path / "claude" and (tmp_path / "claude").is_dir()
    # Interne Werkzeuge sieht Claude nicht; erlaubt sind genau die angebotenen.
    assert options["allowed_tools"] == ["mcp__eve__echo", "mcp__eve__delete_task"]
    assert "EVE" in options["system_prompt"]
    assert sdk.prompts == ["Hallo"]


def test_tool_calls_run_through_the_assistant(tmp_path, install):
    sdk = install(ResultMessage(result="Erledigt."), tool_calls=[("echo", {"text": "hi"})])
    eve = assistant(tmp_path)

    reply = eve.reply("Sag hi")

    assert reply.text == "Erledigt."
    assert eve.tools.calls == [("echo", {"text": "hi"})]
    assert sdk.tool_results == [{"content": [{"type": "text", "text": "echo: {'text': 'hi'}"}], "is_error": False}]
    roles = [(message.role, message.tool_calls) for message in eve.history]
    assert roles == [("user", ()), ("assistant", (ToolCall("echo", {"text": "hi"}, "call_1"),)),
                     ("tool", ()), ("assistant", ())]


def test_risky_tool_waits_for_agreement(tmp_path, install):
    first = install(ResultMessage(result="Soll ich Aufgabe 1 löschen?"), tool_calls=[("delete_task", {"id": "1"})])
    eve = assistant(tmp_path)

    assert eve.reply("Lösch Aufgabe 1").text == "Soll ich Aufgabe 1 löschen?"
    assert eve.tools.calls == []
    assert "Noch NICHT ausgeführt" in first.tool_results[0]["content"][0]["text"]

    second = install(ResultMessage(result="Gelöscht."), tool_calls=[("delete_task", {"id": "1"})])
    assert eve.reply("ja").text == "Gelöscht."
    assert eve.tools.calls == [("delete_task", {"id": "1"})]
    # Der vorgemerkte Aufruf steht mit Argumenten im Verlauf, den Claude mitbekommt.
    assert 'Assistent ruft delete_task auf mit {"id": "1"}' in second.prompts[0]
    assert second.prompts[0].endswith("Neue Nachricht des Nutzers:\nja")


def test_errors_become_chat_replies_and_leave_no_history(tmp_path, install):
    install(AssistantMessage(error="rate_limit"), ResultMessage(result=""))
    eve = assistant(tmp_path)
    assert "Nutzungslimit" in eve.reply("Hallo").text
    assert eve.history == []

    install(ResultMessage(subtype="error_during_execution", is_error=True, result="Not logged in · Please run /login"))
    assert LOGIN_HELP in eve.reply("Hallo").text

    install(ClaudeSDKError("Command failed: authentication required"))
    assert LOGIN_HELP in eve.reply("Hallo").text

    install(ResultMessage(subtype="error_max_turns", is_error=True))
    assert "zu viele Werkzeuge" in eve.reply("Hallo").text


def test_missing_package_explains_installation(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", None)
    assert INSTALL_HELP in assistant(tmp_path).reply("Hallo").text


def test_timeout_is_reported(tmp_path, monkeypatch):
    class Slow(FakeSdk):
        async def query(self, prompt, options):
            await anyio.sleep(1)
            yield ResultMessage(result="zu spät")

    monkeypatch.setitem(sys.modules, "claude_agent_sdk", Slow())
    model = ClaudeCodeModel("", tmp_path, timeout=0.05)
    eve = ClaudeCodeAssistant(model, Tools(), Preferences())
    assert "nicht rechtzeitig" in eve.reply("Hallo").text


def test_announce_and_consult_without_tools(tmp_path, install):
    sdk = install(ResultMessage(result="Gleich ist dein Termin."))
    eve = assistant(tmp_path)

    assert eve.announce("Erinnere an den Termin") == "Gleich ist dein Termin."
    assert sdk.options[0]["allowed_tools"] == [] and sdk.options[0]["mcp_servers"] == {}
    assert eve.consult("Ist das wichtig?") == "Gleich ist dein Termin."
    assert sdk.prompts[1] == "Ist das wichtig?"


def test_model_choice_is_saved(tmp_path, install):
    install()
    preferences = Preferences()
    eve = assistant(tmp_path, preferences)

    eve.select_model("opus")
    assert preferences.values["claude_model"] == "opus"
    assert assistant(tmp_path, preferences).current_model() == "opus"
    with pytest.raises(ValueError):
        eve.select_model("gpt")
    assert [model["name"] for model in eve.available_models()] == list(MODELS)


def test_transcript_with_history():
    messages = [ChatMessage("user", "Wie spät?"), ChatMessage("assistant", "", (ToolCall("get_time", {}),)),
                ChatMessage("tool", "12:00", tool_name="get_time"), ChatMessage("assistant", "12 Uhr."),
                ChatMessage("user", "Danke")]
    assert _transcript(messages) == (
        "Bisheriger Gesprächsverlauf:\n<verlauf>\nNutzer: Wie spät?\nAssistent ruft get_time auf mit {}\n"
        "Ergebnis von get_time: 12:00\nAssistent: 12 Uhr.\n</verlauf>\n\nNeue Nachricht des Nutzers:\nDanke")
    assert _transcript([ChatMessage("assistant", "Hallo")]).endswith("Antworte auf den Verlauf.")
    assert _transcript([]) == ""


def test_chat_refuses_tools_and_run_needs_callback(tmp_path, install):
    install()
    model = ClaudeCodeModel("haiku", tmp_path, timeout=5)
    with pytest.raises(Exception, match="run"):
        model.chat([ChatMessage("user", "x")], [ToolSpec("echo", "")])
    with pytest.raises(Exception, match="Rückruf"):
        model.run([ChatMessage("user", "x")], [ToolSpec("echo", "")])
    assert model.chat([ChatMessage("user", "x")]).message.content == "Antwort."


def test_picker_switches_to_claude(tmp_path, install):
    from tests.assistant.test_model_picker import _picker

    sdk = install(ResultMessage(result="Claude hier."))
    picker, _ = _picker(tmp_path / "preferences.json")
    preferences = picker._preferences
    claude = assistant(tmp_path, preferences)
    picker = ModelPicker(picker._assistants["gemini"], picker._assistants["ollama"], preferences, claude)

    assert {f"claude/{name}" for name in MODELS} <= {model["id"] for model in picker.available_models()}
    assert picker.reply("modell claude/haiku").text == "Ich nutze jetzt claude/haiku."
    assert picker.reply("Hallo").text == "Claude hier."
    assert sdk.options[-1]["model"] == "haiku"
    assert ModelPicker(picker._assistants["gemini"], picker._assistants["ollama"], preferences,
                       claude).current_model() == "claude/haiku"
    picker.select_model("opus")   # ohne Präfix: gehört zu Claude
    assert picker.current_model() == "claude/opus"
    assert "claude/" in picker.reply("hilfe").view.data["rows"][-1][1]
