"""Gemini Developer API über HTTPS, ohne lokalen Dienst oder zusätzliche Pakete."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from functools import partial
from typing import Any

from backend import api_keys

from backend.assistant.llm import ChatMessage, LanguageModelError, ModelInfo, ModelResponse, ToolCall
from backend.assistant.tools import ToolSpec

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/"
MODELS = ("gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash")
KEY_HELP = ("Gemini braucht einen API-Schlüssel. Trag ihn unter ⚙ Einstellungen → Zugangsdaten ein "
            "(landet als GEMINI_API_KEY in der .env). Die Einrichtung steht in der README.")
# Überlastung bei Google ("high demand", meist nur Sekunden): kurz warten und noch einmal fragen
RETRY_CODES = frozenset({500, 503, 504})
RETRY_DELAYS_S = (1.0, 3.0)


class GeminiError(LanguageModelError):
    """Die Gemini API konnte die Anfrage nicht beantworten."""


class GeminiModel:
    def __init__(self, name: str, timeout: float, api_key: Callable[[], str] = partial(api_keys.get, "GEMINI_API_KEY"),
                 sleep: Callable[[float], None] = time.sleep):
        """api_key(): der Schlüssel, bei jeder Anfrage neu gelesen (Umgebungsvariable oder .env)."""
        self.name = ""
        self.default_name = name or MODELS[0]
        self.api_key = api_key
        self.timeout = timeout
        self.sleep = sleep

    def available_models(self) -> list[ModelInfo]:
        return [ModelInfo(name, supports_tools=True, cloud=True) for name in self.selectable()]

    def selectable(self) -> list[str]:
        return list(dict.fromkeys((self.default_name, *MODELS)))

    def chat(self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec] = ()) -> ModelResponse:
        key = self._api_key()
        if not re.fullmatch(r"gemini-[a-z0-9.-]+", self.name):
            raise GeminiError("Ungültiger Gemini-Modellname.")

        body: dict[str, Any] = {"contents": _contents(messages)}
        system = [{"text": message.content} for message in messages if message.role == "system"]
        if system:
            body["systemInstruction"] = {"parts": system}
        if tools:
            body["tools"] = [{"functionDeclarations": [
                {"name": tool.name, "description": tool.description,
                 "parametersJsonSchema": tool.input_schema or {"type": "object", "properties": {}}}
                for tool in tools
            ]}]
        request = urllib.request.Request(
            f"{API_URL}{self.name}:generateContent",
            json.dumps(body).encode("utf-8"),
            {"Content-Type": "application/json"},
        )
        request.add_unredirected_header("x-goog-api-key", key)
        return ModelResponse(_reply(self._send(request), allow_calls=bool(tools)))

    def _send(self, request: urllib.request.Request) -> dict[str, Any]:
        """Anfrage senden; bei Überlastung (RETRY_CODES) bis zu len(RETRY_DELAYS_S)-mal wiederholen."""
        for delay in (*RETRY_DELAYS_S, None):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.load(response)
            except urllib.error.HTTPError as error:
                with error:
                    if error.code not in RETRY_CODES or delay is None:
                        raise GeminiError(_http_error(error, self.name)) from None
            except OSError:
                raise GeminiError("Die Gemini API ist gerade nicht erreichbar.") from None
            except ValueError:
                raise GeminiError("Die Gemini API hat eine ungültige Antwort geliefert.") from None
            self.sleep(delay)
        raise AssertionError("unerreichbar")

    def _api_key(self) -> str:
        try:
            key = self.api_key().strip()
        except (OSError, UnicodeError):
            raise GeminiError("Die .env mit dem Gemini-Schlüssel ist nicht lesbar.") from None
        if not key:
            raise GeminiError(KEY_HELP)
        if any(character.isspace() or not character.isascii() for character in key):
            raise GeminiError("Der Gemini-Schlüssel enthält ungültige Zeichen.")
        return key


def _contents(messages: Sequence[ChatMessage]) -> list[dict[str, Any]]:
    contents: list[dict[str, Any]] = []
    previous_role = None
    for message in messages:
        if message.role == "system":
            continue
        if message.role == "tool":
            result: dict[str, Any] = {"name": message.tool_name, "response": {"output": message.content}}
            if message.tool_call_id:
                result["id"] = message.tool_call_id
            part = {"functionResponse": result}
            if previous_role == "tool":
                contents[-1]["parts"].append(part)
            else:
                contents.append({"role": "user", "parts": [part]})
        elif message.provider_content is not None:
            contents.append(message.provider_content)
        else:
            if not contents and message.role == "assistant":
                # Eine proaktive Meldung kann der erste Eintrag im lokalen Verlauf sein.
                contents.append({"role": "user", "parts": [{"text": "Eine proaktive Meldung wurde ausgelöst."}]})
            role = "model" if message.role == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": message.content}]})
        previous_role = message.role
    return contents


def _reply(data: dict[str, Any], allow_calls: bool) -> ChatMessage:
    try:
        candidate = (data.get("candidates") or [{}])[0]
        content = candidate.get("content") or {}
        parts = content.get("parts") or []
        text = "".join(part.get("text", "") for part in parts if not part.get("thought"))
        calls = tuple(
            ToolCall(call["name"], call.get("args", {}), call.get("id", ""))
            for part in parts if (call := part.get("functionCall")) is not None
        )
        if any(not call.name or not isinstance(call.arguments, dict) for call in calls):
            raise ValueError
    except (AttributeError, IndexError, KeyError, TypeError, ValueError):
        raise GeminiError("Die Gemini API hat eine ungültige Antwort geliefert.") from None
    if calls and (not allow_calls or candidate.get("finishReason") not in (None, "STOP")):
        raise GeminiError("Gemini hat einen unvollständigen oder unerwarteten Werkzeugaufruf geliefert.")
    if not text.strip() and not calls:
        raise GeminiError("Gemini hat keine verwendbare Antwort geliefert.")
    return ChatMessage("assistant", text, calls, provider_content=content)


def _http_error(error: urllib.error.HTTPError, model: str = "") -> str:
    if error.code == 400:
        try:
            details = json.load(error).get("error", {}).get("details", [])
            if any(detail.get("reason") == "API_KEY_INVALID" for detail in details):
                return "Google hat den Gemini-Schlüssel abgelehnt. Prüfe ihn in Google AI Studio."
        except (AttributeError, TypeError, ValueError):
            pass
    hints = {
        400: "Google hat die Anfrage abgelehnt. Prüfe das gewählte Modell und die Projekteinstellungen.",
        401: "Google hat den Gemini-Schlüssel abgelehnt. Prüfe ihn in Google AI Studio.",
        403: "Das Google-Projekt hat keinen Zugriff. Prüfe den Schlüssel und seine Berechtigungen.",
        404: "Das gewählte Gemini-Modell ist für dieses Projekt nicht verfügbar.",
        429: "Das Gemini-Kontingent ist erreicht. Prüfe das Limit deines Projekts oder versuche es später.",
    }
    if error.code in RETRY_CODES:
        others = ", ".join(name for name in MODELS if name != model)
        return (f"Das Gemini-Modell {model} ist bei Google gerade überlastet (HTTP {error.code}). "
                f"Versuch es gleich noch einmal oder wähle ein anderes Modell ({others}).")
    return hints.get(error.code, f"Die Gemini API antwortet mit HTTP {error.code}.")
