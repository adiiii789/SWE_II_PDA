"""Gemeinsamer Verlauf, Befehle und Werkzeugaufrufe für Sprachmodell-Anbieter.

Riskante Werkzeuge (settings.CONFIRMED_TOOLS) laufen erst nach einer Zustimmung: Der erste Aufruf
wird nur vorgemerkt, das Modell fragt nach. Ausgeführt wird genau derselbe Aufruf erst, wenn die
nächste Nachricht des Nutzers zustimmt. Das prüft der Code, weil das Modell auch fremden Text
(Mails, Einladungen) liest: Eingeschleuster Text kann so nichts allein löschen.

Interne Werkzeuge (Präfix watch_, nur für backend/watcher.py) sieht das Modell nie.
"""
from __future__ import annotations

import datetime
import json
import logging
import re
from collections.abc import Callable
from dataclasses import replace

from backend import business_views
from backend.assistant.base import AssistantReply, ModelSelection
from backend.assistant.commands import COMMANDS
from backend.assistant.llm import ChatMessage, LanguageModelError, SelectableLanguageModel, ToolCall
from backend.assistant.settings import CONFIRMED_TOOLS, SETTINGS_KEYS, AssistantSettings, is_internal_tool
from backend.assistant.tools import Attachment, ToolProvider, ToolResult, ToolSpec
from backend.config import APP_NAME
from backend.preferences import PreferenceStore
from backend.views import TemplateView

log = logging.getLogger(__name__)

PROVIDER_PREFERENCE = "model_provider"
MODEL_PREFERENCES = frozenset({"ollama_model", "gemini_model", "claude_model", PROVIDER_PREFERENCE})
MAX_TOOL_RESULT_CHARS = 8000   # schützt das Kontextfenster kleiner Modelle

# Länge, Sprache, Ton, Emojis usw. legt der Nutzer im Popup fest (backend/assistant/settings.py).
BASE_INSTRUCTIONS = (
    f"Du bist {APP_NAME} (Enhanced Virtual Entity), ein persönlicher Assistent auf dem Computer des Nutzers. "
    f"Verwende für dich den Namen {APP_NAME}. Unterschreibe E-Mails in deinem eigenen Namen "
    f"mit {APP_NAME}, auch in Entwürfen. "
    "Nutze Werkzeuge nur, wenn du sie für die Antwort brauchst, und erfinde keine Ergebnisse."
)

# Vor dem Auftrag einer proaktiven Meldung - das Modell soll ihn nicht für eine Frage des Nutzers halten.
PROACTIVE_TRIGGER = ("[Automatischer Auslöser, nicht vom Nutzer geschrieben] Der Nutzer hat nichts gefragt. "
                     "Schreib ihm von dir aus eine Nachricht. Auftrag: ")

CONFIRM_REQUEST = ("Noch NICHT ausgeführt. Nenne dem Nutzer genau, was passieren würde, und frage, ob du das "
                   "tun sollst. Stimmt er in seiner nächsten Nachricht zu, rufe das Werkzeug mit genau "
                   "denselben Argumenten erneut auf. Sonst lass es.")
_AGREEMENT = re.compile(r"\W*(ja|jap|jo|jep|yes|yep|yeah|ok|okay|klar|gerne?|genau|mach|mache|bitte|los|sicher|"
                        r"einverstanden|bestätigt|bestätige|passt|richtig|korrekt|stimmt|natürlich|absolut|"
                        r"lösch|lösche|änder|ändere|verschieb|verschiebe|sag|sage)\b", re.IGNORECASE)
_REFUSAL = re.compile(r"\b(nein|nö|nicht|no|stop|stopp|abbrechen|warte)\b", re.IGNORECASE)

_WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")


class ModelAssistant:
    """Erfüllt Assistant, ModelSelection, ProactiveAssistant und ConsultingAssistant (base.py)."""

    provider: str
    model_preference: str
    model_commands: dict[str, str]
    model_hint: str
    no_model_hint: str
    unknown_model_message: str

    def __init__(self, model: SelectableLanguageModel, tools: ToolProvider, preferences: PreferenceStore,
                 instructions: str = "", max_tool_rounds: int = 5, max_history: int = 30,
                 clock: Callable[[], datetime.datetime] = datetime.datetime.now):
        self.model = model
        self.tools = tools
        self.preferences = preferences
        self.settings = AssistantSettings(preferences)   # Einstellungen aus dem Popup
        self.instructions = instructions
        self.max_tool_rounds = max_tool_rounds
        self.max_history = max_history
        self.clock = clock
        self.history: list[ChatMessage] = []
        self._proposed: set[str] = set()   # riskante Aufrufe, zu denen das Modell gerade nachfragt
        self._approved: set[str] = set()   # davon die, denen der Nutzer zugestimmt hat

    def new_conversation(self) -> None:
        """Verlauf und vorgemerkte riskante Aufrufe vergessen."""
        self.history.clear()
        self._proposed.clear()
        self._approved.clear()

    # --- Assistant -------------------------------------------------------------------
    def reply(self, message: str) -> AssistantReply:
        command = message.strip().lower()
        if command == "neu":
            self.new_conversation()
        if command == "hilfe":
            return model_help_reply(self.model_commands)
        if command in COMMANDS:
            return COMMANDS[command][1]()
        if command == "modelle":
            return model_list_reply(self, self.model_hint)
        if command.startswith("modell "):
            return model_select_reply(self, message.strip()[len("modell "):].strip())

        try:
            if not self._ensure_model():
                return AssistantReply(self.no_model_hint)
        except LanguageModelError as error:
            return AssistantReply(str(error))

        # Zustimmung gilt nur in der Nachricht direkt nach der Rückfrage und nur für die vorgemerkten Aufrufe.
        self._approved = self._proposed if _agrees(message) else set()
        self._proposed = set()
        start = len(self.history)
        self.history.append(ChatMessage("user", message))
        tool_log: list[tuple[ToolCall, ToolResult]] = []
        try:
            text = self._run(tool_log)
        except LanguageModelError as error:
            del self.history[start:]   # misslungene Runde nicht im Verlauf behalten
            return AssistantReply(f"Fehler von {self.provider} ({self.model.name}): {error}")
        self._trim_history()
        return AssistantReply(text, _tool_view(tool_log, self.settings, self.clock()), _attachments(tool_log))

    # --- ProactiveAssistant ------------------------------------------------------------
    def announce(self, instruction: str) -> str | None:
        """Meldung, die der Assistent von sich aus schickt (backend/proactive.py).

        Der Auftrag landet nicht im Verlauf, die Meldung schon - so kann der Nutzer
        direkt darauf antworten ("ja, mach das"). Ohne Werkzeuge, damit die Meldung schnell kommt.
        """
        try:
            if not self._ensure_model():
                return None
            trigger = ChatMessage("user", PROACTIVE_TRIGGER + instruction)
            response = self.model.chat([self._system_message(), *self.history, trigger], [])
        except LanguageModelError as error:
            log.warning("Proaktive Meldung ohne Modell: %s", error)
            return None
        text = response.message.content.strip()
        if not text:
            return None
        self.history.append(ChatMessage("assistant", text))
        self._trim_history()
        return text

    # --- ConsultingAssistant -----------------------------------------------------------
    def consult(self, prompt: str) -> str | None:
        """Einmalige Frage ohne Werkzeuge und Verlauf (Wächter); None, wenn das Modell nicht antwortet."""
        try:
            if not self._ensure_model():
                return None
            response = self.model.chat([ChatMessage("user", prompt)], [])
        except LanguageModelError as error:
            log.warning("Sprachmodell nicht erreichbar: %s", error)
            return None
        return response.message.content.strip() or None

    def _offered_tools(self) -> list[ToolSpec]:
        # Im Popup abgeschaltete und interne Werkzeuge bekommt das Modell gar nicht erst zu sehen.
        return [tool for tool in self.tools.list_tools()
                if not is_internal_tool(tool.name) and self.settings.tool_enabled(tool.name)]

    def _run(self, tool_log: list[tuple[ToolCall, ToolResult]]) -> str:
        tools = self._offered_tools()
        system = self._system_message([tool.name for tool in tools])
        for round_ in range(self.max_tool_rounds + 1):
            # In der letzten Runde keine Werkzeuge mehr anbieten: Das Modell muss antworten.
            offered = tools if round_ < self.max_tool_rounds else []
            response = self.model.chat([system, *self.history], offered)
            self.history.append(response.message)
            if not response.wants_tools:
                return response.message.content.strip() or "(Das Modell hat keine Antwort geliefert.)"
            for call in response.message.tool_calls:
                result = self._call_tool(call)
                tool_log.append((call, result))
                content = ("Fehler: " if result.is_error else "") + result.content[:MAX_TOOL_RESULT_CHARS]
                self.history.append(ChatMessage("tool", content, tool_name=call.name, tool_call_id=call.id))
        return "Ich habe zu viele Werkzeuge nacheinander aufgerufen und breche ab. Versuch es bitte genauer."

    def _call_tool(self, call: ToolCall) -> ToolResult:
        log.info("Werkzeug %s(%s)", call.name, call.arguments)
        if is_internal_tool(call.name):
            return ToolResult(f"Unbekanntes Werkzeug: {call.name!r}", is_error=True)
        if not self.settings.tool_enabled(call.name):
            return ToolResult(f"Das Werkzeug {call.name} hat der Nutzer in den Einstellungen abgeschaltet.",
                              is_error=True)
        if call.name in CONFIRMED_TOOLS:
            key = _call_key(call)
            if key not in self._approved:
                self._proposed.add(key)
                return ToolResult(CONFIRM_REQUEST)
            self._approved.discard(key)   # eine Zustimmung gilt für genau einen Aufruf
        try:
            return self.tools.call_tool(call.name, call.arguments)
        except Exception as error:   # z. B. erfundener Werkzeugname - das Modell soll es korrigieren
            log.warning("Werkzeug %s fehlgeschlagen: %s", call.name, error)
            return ToolResult(str(error), is_error=True)

    def _system_message(self, tools: list[str] = ()) -> ChatMessage:
        now = self.clock()
        parts = [BASE_INSTRUCTIONS,
                 f"Jetzt ist {_WEEKDAYS[now.weekday()]}, der {now:%d.%m.%Y}, {now:%H:%M} Uhr.",
                 self.settings.instructions(tools)]
        context = {k: v for k, v in self.preferences.all().items()
                   if k not in MODEL_PREFERENCES and k not in SETTINGS_KEYS}
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
            raise ValueError(self.unknown_model_message.format(name=name))
        previous = self.current_model()
        self.preferences.set(self.model_preference, name)
        self.model.name = name
        if name != previous:
            # Werkzeugaufrufe und Gemini-Signaturen gehören zum bisherigen Modell.
            self.history = [replace(message, provider_content=None) for message in self.history
                            if message.role != "tool" and not message.tool_calls]

    def _ensure_model(self) -> bool:
        raise NotImplementedError


def _agrees(message: str) -> bool:
    """Stimmt die Nachricht klar zu? Im Zweifel nein, dann fragt das Modell eben noch einmal."""
    return bool(_AGREEMENT.match(message)) and not _REFUSAL.search(message)


def _call_key(call: ToolCall) -> str:
    return call.name + json.dumps(call.arguments, sort_keys=True, ensure_ascii=False)


def model_help_reply(commands: dict[str, str]) -> AssistantReply:
    reply = COMMANDS["hilfe"][1]()
    data = reply.view.data
    rows = [*data["rows"], *([name, description] for name, description in commands.items())]
    return AssistantReply(reply.text, TemplateView(reply.view.template, {**data, "rows": rows}))


def model_list_reply(selection: ModelSelection, hint: str) -> AssistantReply:
    models = selection.available_models()
    current = selection.current_model()
    rows = []
    for model in models:
        key = model.get("id", model["name"])
        rows.append([("▶ " if key == current else "") + model["name"],
                     "Cloud" if model["cloud"] else "Lokal", "ja" if model["tools"] else "nein"])
    status = f"Aktuell: {current}. " if current else ""
    return AssistantReply(
        f'{status}Wechseln mit "modell <name>".',
        TemplateView("default", {"title": "Sprachmodelle", "text": hint,
                                 "columns": ["Modell", "Ort", "Werkzeuge"], "rows": rows}))


def model_select_reply(selection: ModelSelection, name: str) -> AssistantReply:
    try:
        selection.select_model(name)
    except (ValueError, LanguageModelError) as error:
        return AssistantReply(f'{error}. Alle Modelle zeigt "modelle".')
    return AssistantReply(f"Ich nutze jetzt {selection.current_model()}.")


def _tool_view(tool_log: list[tuple[ToolCall, ToolResult]], settings: AssistantSettings,
               now: datetime.datetime) -> TemplateView | None:
    """Anzeige oben: Termine, Aufgaben und Mails grafisch (backend/business_views.py) - nur für
    Gruppen, deren Einstellung "Anzeige oben" an ist. Andere Werkzeuge zeigen nichts an."""
    data = [result.data for call, result in tool_log
            if not result.is_error and result.data and settings.view_shown(call.name)]
    parts = business_views.components(data, now)
    return TemplateView("dashboard", {"components": parts}) if parts else None


def _attachments(tool_log: list[tuple[ToolCall, ToolResult]]) -> tuple[Attachment, ...]:
    """Alle mitgelieferten Dateien der Runde, jede nur einmal (z. B. read_email + read_attachment)."""
    unique = {attachment.uri: attachment for _, result in tool_log for attachment in result.attachments}
    return tuple(unique.values())

