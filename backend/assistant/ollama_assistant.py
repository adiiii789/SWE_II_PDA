"""OllamaAssistant: Assistent mit lokalem Sprachmodell und Werkzeugen (Tool-Calling).

Ablauf von reply(message):
  1. Feste Befehle (commands.COMMANDS, z. B. "hilfe") direkt beantworten, ebenso
     MODEL_COMMANDS ("modelle", "modell <name>") zum Wechseln des Sprachmodells -
     lokal installiert oder in der Ollama-Cloud.
  2. Nachricht an den Gesprächsverlauf anhängen.
  3. model.chat(Systemanweisung + Verlauf, alle Werkzeuge)
  4. Will das Modell Werkzeuge nutzen, ruft der Assistent sie über den ToolProvider
     auf (eigene Integrationen oder MCP-Server) und hängt jedes Ergebnis als
     "tool"-Nachricht an. Weiter bei 3 - höchstens max_tool_rounds-mal.
  5. Sonst ist der Text des Modells die Antwort. Wurden Werkzeuge genutzt,
     zeigt die Ansicht oben eine Tabelle mit Aufrufen und Ergebnissen. Dateien,
     die Werkzeuge mitliefern (z. B. Mail-Anhänge), hängen an der Antwort.
"""
from __future__ import annotations

import datetime
import json
import logging
from collections.abc import Callable

from backend.assistant.base import AssistantReply
from backend.assistant.commands import COMMANDS
from backend.assistant.llm import ChatMessage, ToolCall
from backend.assistant.ollama import OllamaError, OllamaModel, cloud_name
from backend.assistant.tools import Attachment, ToolProvider, ToolResult
from backend.preferences import PreferenceStore
from backend.views import TemplateView

log = logging.getLogger(__name__)

MODEL_PREFERENCE = "ollama_model"
MAX_TOOL_RESULT_CHARS = 8000   # schützt das Kontextfenster kleiner Modelle

BASE_INSTRUCTIONS = (
    "Du bist der Personal Digital Agent, ein persönlicher Assistent auf dem Windows-PC des Nutzers. "
    "Antworte immer auf Deutsch, kurz und freundlich. Verwende niemals Emojis"
    "Nutze Werkzeuge nur, wenn du sie für die Antwort brauchst, und erfinde keine Ergebnisse. "
    "Fehlt dir eine Angabe, frag kurz nach."
)

_WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")

MODEL_COMMANDS = {
    "modelle": "Zeigt lokale und Cloud-Sprachmodelle",
    "modell <name>": "Wechselt das Sprachmodell, z. B. modell gemma4:31b-cloud",
}
CLOUD_HINT = ("Cloud-Modelle laufen auf ollama.com statt auf deinem PC. Dafür einmal im Terminal "
              "'ollama signin' ausführen. Im Free-Plan sind nur einige Modelle enthalten, mit einem "
              "Nutzungskontingent.")


class OllamaAssistant:
    """Erfüllt Assistant und ModelSelection (base.py)."""

    def __init__(self, model: OllamaModel, tools: ToolProvider, preferences: PreferenceStore,
                 instructions: str = "", max_tool_rounds: int = 5, max_history: int = 30,
                 clock: Callable[[], datetime.datetime] = datetime.datetime.now):
        self.model = model
        self.tools = tools
        self.preferences = preferences
        self.instructions = instructions
        self.max_tool_rounds = max_tool_rounds
        self.max_history = max_history
        self.clock = clock
        self.history: list[ChatMessage] = []

    # --- Assistant -------------------------------------------------------------------
    def reply(self, message: str) -> AssistantReply:
        command = message.strip().lower()
        if command == "neu":
            self.history.clear()
        if command == "hilfe":
            return _with_model_commands(COMMANDS[command][1]())
        if command in COMMANDS:
            return COMMANDS[command][1]()
        if command == "modelle":
            return self._models_reply()
        if command.startswith("modell "):
            return self._select_reply(message.strip()[len("modell "):].strip())

        try:
            if not self._ensure_model():
                return AssistantReply("In Ollama ist noch kein Modell installiert. Lade eins herunter, "
                                      "z. B. mit: ollama pull llama3.2 - oder nutze ein Cloud-Modell "
                                      "(Liste mit 'modelle'). " + CLOUD_HINT)
        except OllamaError as error:
            return AssistantReply(str(error))

        start = len(self.history)
        self.history.append(ChatMessage("user", message))
        tool_log: list[tuple[ToolCall, ToolResult]] = []
        try:
            text = self._run(tool_log)
        except OllamaError as error:
            del self.history[start:]   # misslungene Runde nicht im Verlauf behalten
            return AssistantReply(f"Fehler von Ollama ({self.model.name}): {error}")
        self._trim_history()
        return AssistantReply(text, _tool_view(tool_log) if tool_log else None, _attachments(tool_log))

    def _run(self, tool_log: list[tuple[ToolCall, ToolResult]]) -> str:
        tools = self.tools.list_tools()
        for round_ in range(self.max_tool_rounds + 1):
            # In der letzten Runde keine Werkzeuge mehr anbieten: Das Modell muss antworten.
            offered = tools if round_ < self.max_tool_rounds else []
            response = self.model.chat([self._system_message(), *self.history], offered)
            self.history.append(response.message)
            if not response.wants_tools:
                return response.message.content.strip() or "(Das Modell hat keine Antwort geliefert.)"
            for call in response.message.tool_calls:
                result = self._call_tool(call)
                tool_log.append((call, result))
                content = ("Fehler: " if result.is_error else "") + result.content[:MAX_TOOL_RESULT_CHARS]
                self.history.append(ChatMessage("tool", content, tool_name=call.name))
        return "Ich habe zu viele Werkzeuge nacheinander aufgerufen und breche ab. Versuch es bitte genauer."

    def _call_tool(self, call: ToolCall) -> ToolResult:
        log.info("Werkzeug %s(%s)", call.name, call.arguments)
        try:
            return self.tools.call_tool(call.name, call.arguments)
        except Exception as error:   # z. B. erfundener Werkzeugname - das Modell soll es korrigieren
            log.warning("Werkzeug %s fehlgeschlagen: %s", call.name, error)
            return ToolResult(str(error), is_error=True)

    def _models_reply(self) -> AssistantReply:
        try:
            self._ensure_model()
            models = self.model.available_models()
        except OllamaError as error:
            return AssistantReply(str(error))
        rows = [[("▶ " if info.name == self.model.name else "") + info.name,
                 "Cloud" if info.cloud else "Lokal",
                 "ja" if info.supports_tools else "nein"] for info in models]
        current = f"Aktuell: {self.model.name}. " if self.model.name else ""
        return AssistantReply(
            f'{current}Wechseln mit "modell <name>".',
            TemplateView("default", {"title": "Sprachmodelle", "text": CLOUD_HINT,
                                     "columns": ["Modell", "Ort", "Werkzeuge"], "rows": rows}))

    def _select_reply(self, name: str) -> AssistantReply:
        try:
            selectable = self.model.selectable()
            if name not in selectable and cloud_name(name) in selectable:
                name = cloud_name(name)   # "gemma4:31b" meint das Cloud-Modell "gemma4:31b-cloud"
            self.select_model(name)
        except (ValueError, OllamaError) as error:
            return AssistantReply(f'{error}. Alle Modelle zeigt "modelle".')
        return AssistantReply(f"Ich nutze jetzt {name}.")

    def _system_message(self) -> ChatMessage:
        now = self.clock()
        parts = [BASE_INSTRUCTIONS,
                 f"Jetzt ist {_WEEKDAYS[now.weekday()]}, der {now:%d.%m.%Y}, {now:%H:%M} Uhr."]
        context = {k: v for k, v in self.preferences.all().items() if k != MODEL_PREFERENCE}
        if context:
            parts.append("Bekanntes über den Nutzer: " + json.dumps(context, ensure_ascii=False))
        if self.instructions:
            parts.append(self.instructions)
        return ChatMessage("system", "\n\n".join(parts))

    def _trim_history(self) -> None:
        # Vorne kürzen, aber immer an einer Nutzernachricht beginnen
        # (keine "tool"-Nachricht ohne den zugehörigen Aufruf).
        while len(self.history) > self.max_history:
            del self.history[0]
            while self.history and self.history[0].role != "user":
                del self.history[0]

    # --- ModelSelection ---------------------------------------------------------------
    def available_models(self) -> list[dict]:
        return [{"name": info.name, "tools": info.supports_tools, "cloud": info.cloud}
                for info in self.model.available_models()]

    def current_model(self) -> str:
        self._ensure_model()
        return self.model.name

    def select_model(self, name: str) -> None:
        if name not in self.model.selectable():
            raise ValueError(f"Modell {name!r} ist weder installiert noch in der Ollama-Cloud verfügbar")
        self.model.name = name
        self.preferences.set(MODEL_PREFERENCE, name)

    def _ensure_model(self) -> bool:
        """Modell festlegen, falls noch keins gewählt ist: zuletzt gewähltes (auch Cloud),
        sonst erstes installiertes."""
        if self.model.name:
            return True
        installed = self.model.installed()
        saved = self.preferences.get(MODEL_PREFERENCE)
        if saved and (saved in installed or saved in {info.name for info in self.model.cloud_models()}):
            self.model.name = saved
        else:
            self.model.name = installed[0] if installed else ""
        return bool(self.model.name)


def _with_model_commands(reply: AssistantReply) -> AssistantReply:
    data = reply.view.data
    rows = [*data["rows"], *([name, description] for name, description in MODEL_COMMANDS.items())]
    return AssistantReply(reply.text, TemplateView(reply.view.template, {**data, "rows": rows}))


def _tool_view(tool_log: list[tuple[ToolCall, ToolResult]]) -> TemplateView:
    rows = [[call.name, json.dumps(call.arguments, ensure_ascii=False),
             ("Fehler: " if result.is_error else "") + _shorten(result.content)]
            for call, result in tool_log]
    return TemplateView("default", {"title": "Verwendete Werkzeuge",
                                    "columns": ["Werkzeug", "Argumente", "Ergebnis"], "rows": rows})


def _attachments(tool_log: list[tuple[ToolCall, ToolResult]]) -> tuple[Attachment, ...]:
    """Alle mitgelieferten Dateien der Runde, jede nur einmal (z. B. read_email + read_attachment)."""
    unique = {attachment.uri: attachment for _, result in tool_log for attachment in result.attachments}
    return tuple(unique.values())


def _shorten(text: str, limit: int = 300) -> str:
    return text if len(text) <= limit else text[:limit] + " …"
