import io
import json
from unittest.mock import patch

from backend.assistant.gemini import MODELS, GeminiModel
from backend.assistant.gemini_assistant import GeminiAssistant
from backend.assistant.tools import ToolResult, ToolSpec
from backend.preferences import JsonPreferenceStore


def test_gemini_round_trip_preserves_signatures_and_parallel_call_ids(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    key_file = tmp_path / "gemini-api-key.txt"
    key_file.write_text("test-key\n", encoding="utf-8")
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
    model = GeminiModel("", key_file, timeout=1)
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
