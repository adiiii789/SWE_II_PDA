import io
import json
from unittest.mock import patch

from backend.assistant.gemini import MODELS, GeminiModel
from backend.assistant import ConsultingAssistant
from backend.assistant.gemini_assistant import GeminiAssistant
from backend.assistant.model_picker import ModelPicker
from backend.assistant.ollama import OllamaClient, OllamaModel
from backend.assistant.ollama_assistant import OllamaAssistant
from backend.assistant.tools import CompositeToolProvider
from backend.preferences import JsonPreferenceStore


def _json_response(payload):
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


def _picker(path):
    prefs = JsonPreferenceStore(path)
    tools = CompositeToolProvider([])
    client = OllamaClient(chat_timeout=1, catalog_timeout=1)
    gemini = GeminiAssistant(GeminiModel("", path.parent / "gemini-api-key.txt", timeout=1), tools, prefs)
    ollama = OllamaAssistant(OllamaModel(client), tools, prefs)
    return ModelPicker(gemini, ollama, prefs), client


def test_picks_both_providers_and_keeps_local_history_out_of_gemini(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    path = tmp_path / "preferences.json"
    picker, client = _picker(path)
    local = {"name": "local:latest", "capabilities": ["completion"]}
    catalog = {"models": [local, {"name": "model:cloud"},
                          {"name": "alias:latest", "remote_model": "remote"}]}
    ollama_requests = []

    def ollama_response(request, **kwargs):
        assert request.host == "127.0.0.1:11434"
        if request.selector == "/api/tags":
            return _json_response(catalog)
        ollama_requests.append(json.loads(request.data))
        return _json_response({"message": {"role": "assistant", "content": "Lokal."}})

    gemini_reply = {"candidates": [{"content": {"role": "model", "parts": [{"text": "Cloud."}]}}]}
    with patch.object(client._opener, "open", side_effect=ollama_response), \
            patch("backend.assistant.gemini.urllib.request.urlopen", return_value=_json_response(gemini_reply)) as gemini_http:
        assert {model["id"] for model in picker.available_models()} == {
            "ollama/local:latest", *(f"gemini/{name}" for name in MODELS),
        }
        picker.select_model("ollama/local:latest")
        assert picker.reply("Lokaler Kontext").text == "Lokal."
        assert ollama_requests[0]["model"] == "local:latest"
        gemini_http.assert_not_called()

        restarted, _ = _picker(path)
        assert restarted.current_model() == "ollama/local:latest"
        assert picker.reply(f"modell gemini/{MODELS[0]}").text.startswith("Ich nutze jetzt")
        assert picker.reply("Gemini-Kontext").text == "Cloud."
        cloud_request = json.loads(gemini_http.call_args.args[0].data)
        assert cloud_request["contents"] == [{"role": "user", "parts": [{"text": "Gemini-Kontext"}]}]

        picker.select_model("ollama/local:latest")
        assert picker.reply("Weiter lokal").text == "Lokal."
        local_messages = ollama_requests[-1]["messages"]
        assert {"role": "user", "content": "Lokaler Kontext"} in local_messages
        assert "Gemini-Kontext" not in json.dumps(local_messages)

        local["remote_host"] = "https://ollama.com"
        assert "Modell fehlt" in picker.reply("Bleibt lokal").text
        assert len(ollama_requests) == 2
        gemini_http.assert_called_once()


def test_offline_ollama_preserves_selection_without_cloud_fallback(tmp_path):
    path = tmp_path / "preferences.json"
    prefs = JsonPreferenceStore(path)
    prefs.set("model_provider", "ollama")
    prefs.set("ollama_model", "local:latest")
    picker, client = _picker(path)
    with patch.object(client._opener, "open", side_effect=ConnectionRefusedError), \
            patch("backend.assistant.gemini.urllib.request.urlopen") as gemini_http:
        assert picker.current_model() == "ollama/local:latest"
        assert all(model["cloud"] for model in picker.available_models())
        assert "nicht erreichbar" in picker.reply("Nur lokal").text
        gemini_http.assert_not_called()


def test_consult_goes_to_the_active_assistant(tmp_path):
    picker, _ = _picker(tmp_path / "preferences.json")
    assert isinstance(picker, ConsultingAssistant)
    with patch.object(picker._assistants["gemini"], "consult", return_value="Ja") as gemini_consult, \
            patch.object(picker._assistants["ollama"], "consult") as ollama_consult:
        assert picker.consult("Wichtig?") == "Ja"
    gemini_consult.assert_called_once_with("Wichtig?")
    ollama_consult.assert_not_called()


def test_new_conversation_also_forgets_proposed_calls(tmp_path):
    picker, _ = _picker(tmp_path / "preferences.json")
    for assistant in picker._assistants.values():
        assistant._proposed.add("delete_task{}")
    picker.reply("neu")
    assert all(not assistant._proposed for assistant in picker._assistants.values())
