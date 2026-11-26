import io
import json
import urllib.error
from unittest.mock import patch

import pytest

from backend.assistant.gemini import MODELS, RETRY_DELAYS_S, GeminiError, GeminiModel
from backend.assistant.gemini_assistant import GeminiAssistant
from backend.assistant.llm import ChatMessage
from backend.assistant.tools import ToolResult, ToolSpec
from backend.preferences import JsonPreferenceStore


def test_gemini_round_trip_preserves_signatures_and_parallel_call_ids(tmp_path, monkeypatch):
    signed_turn = {"role": "model", "parts": [
        {"functionCall": {"name": "echo", "id": "call-1", "args": {"text": "eins"}},
         "thoughtSignature": "c2lnbmF0dXJl"},
        {"functionCall": {"name": "echo", "id": "call-2", "args": {"text": "zwei"}}},
    ]}
    final_turn = {"role": "model", "parts": [
        {"text": "Interne Überlegung", "thought": True},
        {"text": "Fertig."},
    ]}

    class Echo:
        def list_tools(self):
            return [ToolSpec("echo", "Text zurückgeben", {"type": "object"})]

        def call_tool(self, name, arguments):
            assert name == "echo"
            return ToolResult(arguments["text"])

    preferences_path = tmp_path / "preferences.json"
    preferences = JsonPreferenceStore(preferences_path)
    preferences.set("ollama_model", "altes-ollama-modell")
    model = GeminiModel("", timeout=1, api_key=lambda: "test-key\n")
    assistant = GeminiAssistant(model, Echo(), preferences)
    responses = [io.BytesIO(json.dumps({"candidates": [{"content": turn}]}).encode())
                 for turn in (signed_turn, final_turn, final_turn)]
    with patch("backend.assistant.gemini.urllib.request.urlopen", side_effect=responses) as http:
        assert assistant.reply("Wiederhole eins und zwei.").text == "Fertig."
        initial_request, followup_request = (call.args[0] for call in http.call_args_list)
        assert initial_request.full_url.endswith(f"/{MODELS[0]}:generateContent")
        assert initial_request.get_header("X-goog-api-key") == "test-key"
        initial = json.loads(initial_request.data)
        assert initial["tools"][0]["functionDeclarations"][0]["name"] == "echo"
        assert "altes-ollama-modell" not in json.dumps(initial)
        followup = json.loads(followup_request.data)
        assert followup["contents"][1] == signed_turn
        assert followup["contents"][2] == {"role": "user", "parts": [
            {"functionResponse": {"name": "echo", "id": "call-1", "response": {"output": "eins"}}},
            {"functionResponse": {"name": "echo", "id": "call-2", "response": {"output": "zwei"}}},
        ]}

        assistant.select_model(MODELS[1])
        assert JsonPreferenceStore(preferences_path).get("gemini_model") == MODELS[1]
        assert assistant.reply("Weiter bitte.").text == "Fertig."
        switched = json.loads(http.call_args.args[0].data)
        assert switched["contents"] == [
            {"role": "user", "parts": [{"text": "Wiederhole eins und zwei."}]},
            {"role": "model", "parts": [{"text": "Fertig."}]},
            {"role": "user", "parts": [{"text": "Weiter bitte."}]},
        ]


def _http_error(code):
    body = io.BytesIO(json.dumps({"error": {"code": code, "status": "UNAVAILABLE"}}).encode())
    return urllib.error.HTTPError("https://example.invalid", code, "error", {}, body)


def _ok():
    return io.BytesIO(json.dumps({"candidates": [{"content": {"role": "model", "parts": [{"text": "Hallo"}]}}]}).encode())


def _model(waits):
    model = GeminiModel("", timeout=1, api_key=lambda: "test-key", sleep=waits.append)
    model.name = MODELS[1]
    return model


def test_gemini_retries_when_overloaded():
    waits = []
    with patch("backend.assistant.gemini.urllib.request.urlopen", side_effect=[_http_error(503), _ok()]) as http:
        assert _model(waits).chat([ChatMessage("user", "Hi")]).message.content == "Hallo"
    assert http.call_count == 2
    assert waits == [RETRY_DELAYS_S[0]]


def test_gemini_gives_up_after_retries_and_suggests_other_models():
    waits = []
    errors = [_http_error(503) for _ in range(len(RETRY_DELAYS_S) + 1)]
    with patch("backend.assistant.gemini.urllib.request.urlopen", side_effect=errors) as http,             pytest.raises(GeminiError, match="überlastet") as raised:
        _model(waits).chat([ChatMessage("user", "Hi")])
    assert http.call_count == len(RETRY_DELAYS_S) + 1
    assert waits == list(RETRY_DELAYS_S)
    others = str(raised.value).split("(")[-1].rstrip(").").split(", ")
    assert others == [name for name in MODELS if name != MODELS[1]]


def test_gemini_does_not_retry_client_errors():
    waits = []
    with patch("backend.assistant.gemini.urllib.request.urlopen", side_effect=[_http_error(429)]) as http,             pytest.raises(GeminiError, match="Kontingent"):
        _model(waits).chat([ChatMessage("user", "Hi")])
    assert http.call_count == 1 and waits == []
