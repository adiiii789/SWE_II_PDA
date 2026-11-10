"""Hochfahren im Hintergrund (Ladebildschirm) und Vorladen des Sprachmodells."""
import threading
import unittest
from unittest import mock

from backend import api
from backend.assistant.ollama import OllamaError, OllamaModel
from backend.assistant.ollama_assistant import OllamaAssistant
from backend.events import STARTUP_PROGRESS, EventBus
from backend.startup import Startup, Step
from tests.assistant.test_settings import MemoryStore


class StartupTest(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.finished = threading.Event()
        self.reported = []

        def record(name, payload):
            self.reported.append((name, payload))
            if payload["done"]:
                self.finished.set()

        self.bus.subscribe(record)

    def run_steps(self, *steps):
        startup = Startup(steps, self.bus)
        startup.start()
        self.assertTrue(self.finished.wait(5))
        return startup

    def test_runs_steps_in_order_outside_the_calling_thread_and_reports_progress(self):
        threads = []
        self.run_steps(Step("eins", lambda: threads.append(threading.current_thread())), Step("zwei", lambda: None, True))
        self.assertIsNot(threads[0], threading.main_thread())
        self.assertEqual([name for name, _ in self.reported], [STARTUP_PROGRESS] * 3)
        self.assertEqual([(p["index"], p["label"], p["skippable"], p["done"]) for _, p in self.reported],
                         [(0, "eins", False, False), (1, "zwei", True, False), (2, "", False, True)])
        self.assertEqual(self.reported[0][1]["labels"], ["eins", "zwei"])
        self.assertEqual(self.reported[0][1]["total"], 2)

    def test_failed_step_does_not_stop_the_rest(self):
        ran = []

        def fail():
            raise RuntimeError("kaputt")

        with self.assertLogs("backend.startup", "ERROR"):
            startup = self.run_steps(Step("kaputt", fail), Step("danach", lambda: ran.append(True)))
        self.assertEqual(ran, [True])
        self.assertTrue(startup.status()["done"])

    def test_second_start_does_not_run_steps_again(self):
        runs = []
        startup = self.run_steps(Step("einmal", lambda: runs.append(True)))
        self.assertTrue(startup.start()["done"])
        self.assertEqual(runs, [True])

    def test_status_before_start_names_first_step(self):
        status = Startup([Step("eins", lambda: None)], self.bus).status()
        self.assertEqual((status["done"], status["index"], status["label"]), (False, 0, "eins"))


def ollama_model(client, name):
    model = OllamaModel(client)
    model.name = name
    return model


class PreloadTest(unittest.TestCase):
    def test_local_model_is_loaded_without_prompt(self):
        client = mock.Mock()
        ollama_model(client, "llama3.2").preload()
        client.post.assert_called_once_with("/api/generate", {"model": "llama3.2", "stream": False})

    def test_cloud_models_are_not_loaded(self):
        client = mock.Mock()
        ollama_model(client, "gemma4:cloud").preload()
        ollama_model(client, "gpt-oss:120b-cloud").preload()
        client.post.assert_not_called()

    def assistant(self, name, installed=()):
        model = mock.Mock(spec=OllamaModel)
        model.name = name
        model.selectable.return_value = list(installed)
        return OllamaAssistant(model, mock.Mock(), MemoryStore())

    def test_assistant_preloads_chosen_model(self):
        assistant = self.assistant("", ["llama3.2"])
        assistant.preload_model()
        self.assertEqual(assistant.model.name, "llama3.2")
        assistant.model.preload.assert_called_once_with()

    def test_assistant_without_installed_model_loads_nothing(self):
        assistant = self.assistant("")
        assistant.preload_model()
        assistant.model.preload.assert_not_called()

    def test_api_loads_model_only_for_assistants_that_can(self):
        class Preloading:   # echte Klasse: isinstance prüft Protokolle statisch, das sieht keine Mock-Attribute
            calls = 0

            def preload_model(self):
                Preloading.calls += 1

        with mock.patch.object(api, "_assistant", return_value=Preloading()):
            api._load_model()
        self.assertEqual(Preloading.calls, 1)
        with mock.patch.object(api, "_assistant", return_value=mock.Mock(spec=["reply"])):
            api._load_model()   # darf nicht scheitern

    def test_unreachable_ollama_is_a_failed_step_not_a_crash(self):
        bus, finished = EventBus(), threading.Event()
        bus.subscribe(lambda name, payload: payload["done"] and finished.set())
        client = mock.Mock()
        client.post.side_effect = OllamaError("weg")
        with self.assertLogs("backend.startup", "ERROR"):
            Startup([Step("Modell", ollama_model(client, "llama3.2").preload)], bus).start()
            self.assertTrue(finished.wait(5))


if __name__ == "__main__":
    unittest.main()
