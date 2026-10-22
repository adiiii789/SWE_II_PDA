"""OllamaModel: LanguageModel (llm.py) über die HTTP-API eines lokalen Ollama.

Ollama läuft als eigener Dienst (Standard: http://localhost:11434). Modelle lädt
man vorher herunter, z. B. "ollama pull llama3.2". Genutzt werden:
  POST /api/chat   nächste Antwort, optional mit Werkzeugen (Tool-Calling)
  GET  /api/tags   installierte Modelle
  POST /api/show   Details eines Modells (u. a. ob es Tool-Calling kann)

Cloud-Modelle: Das lokale Ollama leitet Modelle mit der Endung "cloud"
(z. B. "gpt-oss:120b-cloud", "gemma4:cloud") an ollama.com weiter - nichts wird
heruntergeladen. Voraussetzung ist einmalig "ollama signin" (Konto auf ollama.com,
der Free-Plan reicht für einige Modelle). Welche Cloud-Modelle es gibt, liefert
GET https://ollama.com/api/tags (öffentlich, ohne Anmeldung).

Nur Standardbibliothek (urllib), damit keine weitere Abhängigkeit nötig ist.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from backend.assistant.llm import ChatMessage, ModelResponse, ToolCall
from backend.assistant.tools import ToolSpec

log = logging.getLogger(__name__)


class OllamaError(RuntimeError):
    """Ollama ist nicht erreichbar oder hat mit einem Fehler geantwortet."""


@dataclass(frozen=True)
class ModelInfo:
    name: str
    supports_tools: bool
    cloud: bool = False


class OllamaClient:
    """Dünne Hülle um die HTTP-API. Getrennt vom Modell, damit Tests sie ersetzen können."""

    def __init__(self, base_url: str, timeout: float,
                 unreachable_hint: str = "Läuft Ollama (Tray-Icon bzw. 'ollama serve')?"):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.unreachable_hint = unreachable_hint

    def get(self, path: str) -> dict[str, Any]:
        return self._request(urllib.request.Request(self.base_url + path))

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(self.base_url + path, data, {"Content-Type": "application/json"})
        return self._request(request)

    def _request(self, request: urllib.request.Request) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise OllamaError(_error_message(error)) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            raise OllamaError(
                f"{self.base_url} ist nicht erreichbar ({error}). {self.unreachable_hint}") from None


# Hinweise zu Fehlern, die bei Cloud-Modellen auftreten (Ollamas eigener Text bleibt davor stehen).
_HTTP_HINTS = {
    401: "Für Cloud-Modelle bei ollama.com anmelden: im Terminal 'ollama signin' ausführen.",
    402: "Dieses Cloud-Modell ist nicht im Free-Plan enthalten - wähle ein anderes ('modelle').",
    429: "Das Nutzungskontingent ist aufgebraucht (Free-Plan) - später erneut versuchen "
         "oder ein lokales Modell wählen ('modelle').",
}


def _error_message(error: urllib.error.HTTPError) -> str:
    try:
        message = json.loads(error.read().decode("utf-8"))["error"]
    except Exception:
        message = f"HTTP {error.code}: {error.reason}"
    hint = _HTTP_HINTS.get(error.code)
    return f"{message} {hint}" if hint else message


class OllamaModel:
    """Erfüllt LanguageModel. Das Modell lässt sich zur Laufzeit wechseln (Attribut name)."""

    def __init__(self, client: OllamaClient, name: str, options: dict[str, Any] | None = None,
                 cloud_catalog: OllamaClient | None = None):
        self.client = client
        self.name = name
        self.options = options or {}
        self.cloud_catalog = cloud_catalog   # ollama.com; None = Cloud-Modelle nicht anbieten

    def chat(self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec] = ()) -> ModelResponse:
        body: dict[str, Any] = {
            "model": self.name,
            "messages": [_message_to_ollama(m) for m in messages],
            "stream": False,
        }
        if self.options:
            body["options"] = self.options
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
        return ModelResponse(_message_from_ollama(data["message"]))

    def installed(self) -> list[str]:
        """Namen aller in Ollama installierten Modelle, alphabetisch."""
        return sorted(model["name"] for model in self.client.get("/api/tags").get("models", []))

    def cloud_models(self) -> list[ModelInfo]:
        """Cloud-Modelle von ollama.com unter ihrem lokalen Namen, alphabetisch.
        Ohne Katalog oder Internet leer - lokale Modelle gehen trotzdem."""
        if self.cloud_catalog is None:
            return []
        try:
            models = self.cloud_catalog.get("/api/tags").get("models", [])
        except OllamaError as error:
            log.warning("Cloud-Modelle nicht abrufbar: %s", error)
            return []
        return sorted((ModelInfo(cloud_name(m["name"]), "tools" in (m.get("capabilities") or ["tools"]), True)
                       for m in models), key=lambda info: info.name)

    def available_models(self) -> list[ModelInfo]:
        """Installierte Modelle, danach die übrigen Cloud-Modelle - jeweils mit der Angabe,
        ob sie Tool-Calling können."""
        local = self.client.get("/api/tags").get("models", [])
        result = [ModelInfo(m["name"], self._supports_tools(m["name"]), _is_cloud(m))
                  for m in sorted(local, key=lambda m: m["name"])]
        names = {info.name for info in result}
        return result + [info for info in self.cloud_models() if info.name not in names]

    def selectable(self) -> list[str]:
        """Alle wählbaren Namen: installierte und Cloud-Modelle."""
        return [info.name for info in self.available_models()]

    def _supports_tools(self, name: str) -> bool:
        try:
            capabilities = self.client.post("/api/show", {"model": name}).get("capabilities")
        except OllamaError:
            return True   # unbekannt - im Zweifel anbieten, chat() fällt notfalls zurück
        # Ältere Ollama-Versionen liefern keine capabilities.
        return capabilities is None or "tools" in capabilities


def cloud_name(name: str) -> str:
    """Name eines Modells von ollama.com im lokalen Ollama: "gpt-oss:120b" -> "gpt-oss:120b-cloud",
    "gemma4" -> "gemma4:cloud"."""
    return f"{name}-cloud" if ":" in name else f"{name}:cloud"


def _is_cloud(model: dict[str, Any]) -> bool:
    return bool(model.get("remote_host")) or model["name"].endswith(("-cloud", ":cloud"))


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
    calls = tuple(
        ToolCall(call["function"]["name"], _parse_arguments(call["function"].get("arguments")))
        for call in data.get("tool_calls") or ())
    return ChatMessage(data.get("role", "assistant"), data.get("content") or "", calls)


def _parse_arguments(arguments: Any) -> dict[str, Any]:
    # Normalerweise ein Objekt; manche Modelle liefern die Argumente als JSON-Text.
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str) and arguments.strip():
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}
