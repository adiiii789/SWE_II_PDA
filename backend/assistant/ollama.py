"""Lokal installierte Ollama-Modelle über die API auf dem eigenen Rechner."""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Sequence
from typing import Any

from backend.assistant.llm import ChatMessage, LanguageModelError, ModelInfo, ModelResponse, ToolCall
from backend.assistant.tools import ToolSpec

log = logging.getLogger(__name__)


class OllamaError(LanguageModelError):
    """Ollama ist nicht erreichbar oder hat mit einem Fehler geantwortet."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class OllamaClient:
    """Für lokale Anfragen werden weder Proxys noch HTTP-Weiterleitungen benutzt."""

    def __init__(self, chat_timeout: float, catalog_timeout: float):
        self.chat_timeout = chat_timeout
        self.catalog_timeout = catalog_timeout
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())

    def get(self, path: str) -> dict[str, Any]:
        request = urllib.request.Request("http://127.0.0.1:11434" + path)
        return self._request(request, self.catalog_timeout)

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request("http://127.0.0.1:11434" + path, json.dumps(body).encode("utf-8"),
                                         {"Content-Type": "application/json"})
        return self._request(request, self.chat_timeout)

    def _request(self, request: urllib.request.Request, timeout: float) -> dict[str, Any]:
        try:
            with self._opener.open(request, timeout=timeout) as response:
                data = json.load(response)
                if not isinstance(data, dict):
                    raise ValueError
                return data
        except urllib.error.HTTPError as error:
            with error:
                try:
                    message = str(json.load(error)["error"])
                except (KeyError, TypeError, ValueError):
                    message = f"HTTP {error.code}"
            raise OllamaError(message) from None
        except OSError:
            raise OllamaError("Ollama ist lokal nicht erreichbar. Starte die Ollama-App oder `ollama serve`.") from None
        except ValueError:
            raise OllamaError("Ollama hat eine ungültige Antwort geliefert.") from None


class OllamaModel:
    """Erfüllt LanguageModel. Das Modell lässt sich zur Laufzeit wechseln (Attribut name)."""

    def __init__(self, client: OllamaClient):
        self.client = client
        self.name = ""

    def chat(self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec] = ()) -> ModelResponse:
        # Auch nach der Auswahl prüfen: Ein Modell kann entfernt oder ersetzt worden sein.
        local = self._installed()
        if self.name not in local:
            raise OllamaError("Das ausgewählte lokale Modell fehlt. Wähle ein installiertes Ollama-Modell.")
        if not local[self.name].supports_tools:
            tools = ()
        body: dict[str, Any] = {
            "model": self.name,
            "messages": [_message_to_ollama(m) for m in messages],
            "stream": False,
        }
        if tools:
            body["tools"] = [_tool_to_ollama(t) for t in tools]
        try:
            data = self.client.post("/api/chat", body)
        except OllamaError as error:
            # Nicht jedes Modell kann Tool-Calling - dann eben ohne Werkzeuge antworten.
            if not tools or "does not support tools" not in str(error):
                raise
            log.warning("Modell %s kann kein Tool-Calling, antworte ohne Werkzeuge", self.name)
            del body["tools"]
            data = self.client.post("/api/chat", body)
            tools = ()
        try:
            message = _message_from_ollama(data["message"])
            if message.tool_calls and not tools:
                raise ValueError
        except (AttributeError, KeyError, TypeError, ValueError):
            raise OllamaError("Ollama hat eine ungültige Chat-Antwort geliefert.") from None
        return ModelResponse(message)

    def _installed(self) -> dict[str, ModelInfo]:
        try:
            return {model["name"]: ModelInfo(model["name"], _supports_tools(model))
                    for model in self.client.get("/api/tags").get("models", [])
                    if not _is_cloud(model)}
        except (AttributeError, KeyError, TypeError):
            raise OllamaError("Ollama hat eine ungültige Modellliste geliefert.") from None

    def available_models(self) -> list[ModelInfo]:
        return sorted(self._installed().values(), key=lambda model: model.name)

    def selectable(self) -> list[str]:
        return sorted(self._installed())


def _supports_tools(model: dict[str, Any]) -> bool:
    # Ältere Ollama-Versionen melden in /api/tags keine Capabilities.
    capabilities = model.get("capabilities")
    return capabilities is None or "tools" in capabilities


def _is_cloud(model: dict[str, Any]) -> bool:
    return bool(model.get("remote_host") or model.get("remote_model")
                or model["name"].endswith(("-cloud", ":cloud")))


# --- Übersetzung in das JSON-Format von Ollama --------------------------------
def _message_to_ollama(message: ChatMessage) -> dict[str, Any]:
    result: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        result["tool_calls"] = [
            {"function": {"name": call.name, "arguments": call.arguments}} for call in message.tool_calls]
    if message.tool_name:
        result["tool_name"] = message.tool_name
    return result


def _tool_to_ollama(spec: ToolSpec) -> dict[str, Any]:
    schema = spec.input_schema or {"type": "object", "properties": {}}
    return {"type": "function",
            "function": {"name": spec.name, "description": spec.description, "parameters": schema}}


def _message_from_ollama(data: dict[str, Any]) -> ChatMessage:
    text = data.get("content") or ""
    if not isinstance(text, str):
        raise ValueError
    calls = tuple(
        ToolCall(call["function"]["name"], _parse_arguments(call["function"].get("arguments")))
        for call in data.get("tool_calls") or ())
    if any(not isinstance(call.name, str) or not call.name for call in calls):
        raise ValueError
    return ChatMessage("assistant", text, calls)


def _parse_arguments(arguments: Any) -> dict[str, Any]:
    # Normalerweise ein Objekt; manche Modelle liefern die Argumente als JSON-Text.
    if isinstance(arguments, dict):
        return arguments
    if arguments is None:
        return {}
    if isinstance(arguments, str):
        parsed = json.loads(arguments)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError
