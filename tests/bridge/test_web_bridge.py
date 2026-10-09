import json
import logging
import unittest
from concurrent.futures import Executor, Future, ThreadPoolExecutor

from PyQt5.QtWebEngineWidgets import QWebEnginePage

from tests.qt_helpers import qt_app

from backend.bridge import web_bridge
from backend.bridge.function_registry import FunctionRegistry
from backend.bridge.web_bridge import WebBridge
from backend.events import EventBus


def _fail():
    raise ValueError("broken")


class ImmediateExecutor(Executor):
    """Führt Aufgaben sofort im aufrufenden Thread aus - macht call() in Tests deterministisch."""

    def submit(self, fn, /, *args, **kwargs):
        future = Future()
        future.set_result(fn(*args, **kwargs))
        return future


class RecordingExecutor(Executor):
    """Merkt sich übergebene Aufgaben, ohne sie auszuführen."""

    def __init__(self):
        self.submitted = []

    def submit(self, fn, /, *args, **kwargs):
        self.submitted.append((fn, args))
        return Future()


class InvokeTest(unittest.TestCase):
    def setUp(self):
        self.bridge = WebBridge(FunctionRegistry({"add": lambda a, b: a + b, "fail": _fail}), ImmediateExecutor())
        logging.disable(logging.CRITICAL)  # erwartete Fehler-Logs nicht ausgeben
        self.addCleanup(logging.disable, logging.NOTSET)

    def _invoke(self, name, args):
        return json.loads(self.bridge.invoke(name, json.dumps(args)))

    def test_success_returns_result(self):
        self.assertEqual(self._invoke("add", [2, 3]), {"ok": True, "result": 5})

    def test_exception_is_reported_as_error(self):
        self.assertEqual(self._invoke("fail", []), {"ok": False, "error": "broken"})

    def test_unknown_function_is_reported_as_error(self):
        response = self._invoke("does_not_exist", [])
        self.assertFalse(response["ok"])
        self.assertIn("does_not_exist", response["error"])

    def test_empty_arguments_are_allowed(self):
        bridge = WebBridge(FunctionRegistry({"one": lambda: 1}), ImmediateExecutor())
        self.assertEqual(json.loads(bridge.invoke("one", "")), {"ok": True, "result": 1})


class AsyncCallTest(unittest.TestCase):
    def test_call_emits_finished_with_call_id(self):
        bridge = WebBridge(FunctionRegistry({"add": lambda a, b: a + b}), ImmediateExecutor())
        results = []
        bridge.finished.connect(lambda call_id, raw: results.append((call_id, json.loads(raw))))
        bridge.call(7, "add", "[2, 3]")
        self.assertEqual(results, [(7, {"ok": True, "result": 5})])

    def test_call_hands_work_to_executor_instead_of_running_it(self):
        executor = RecordingExecutor()
        bridge = WebBridge(FunctionRegistry({"add": lambda a, b: a + b}), executor)
        results = []
        bridge.finished.connect(lambda call_id, raw: results.append(call_id))
        bridge.call(1, "add", "[2, 3]")
        self.assertEqual(len(executor.submitted), 1)
        self.assertEqual(results, [])   # noch nicht ausgeführt - das macht der Executor-Thread

    def test_call_after_close_answers_with_error(self):
        bridge = WebBridge(FunctionRegistry({"add": lambda a, b: a + b}), ImmediateExecutor())
        results = []
        bridge.finished.connect(lambda call_id, raw: results.append((call_id, json.loads(raw))))
        bridge.close()
        bridge.call(3, "add", "[2, 3]")
        self.assertEqual(results, [(3, {"ok": False, "error": "Bridge ist geschlossen"})])

    def test_call_never_raises_when_executor_is_shut_down(self):
        # Eine Exception in einem Qt-Slot würde das ganze Programm beenden.
        executor = ThreadPoolExecutor(max_workers=1)
        executor.shutdown()
        bridge = WebBridge(FunctionRegistry({"add": lambda a, b: a + b}), executor)
        results = []
        bridge.finished.connect(lambda call_id, raw: results.append(json.loads(raw)["ok"]))
        bridge.call(1, "add", "[2, 3]")
        self.assertEqual(results, [False])

    def test_result_of_running_call_is_dropped_after_close(self):
        executor = RecordingExecutor()
        bridge = WebBridge(FunctionRegistry({"add": lambda a, b: a + b}), executor)
        results = []
        bridge.finished.connect(lambda call_id, raw: results.append(call_id))
        bridge.call(1, "add", "[2, 3]")
        bridge.close()
        fn, args = executor.submitted[0]
        fn(*args)   # Aufruf läuft erst nach close() zu Ende
        self.assertEqual(results, [])

    def test_no_events_after_close(self):
        bridge = WebBridge(FunctionRegistry({}), ImmediateExecutor())
        received = []
        bridge.event.connect(lambda name, raw: received.append(name))
        bridge.close()
        bridge.push_event("ping", {})
        self.assertEqual(received, [])

    def test_push_event_emits_json(self):
        bridge = WebBridge(FunctionRegistry({}), ImmediateExecutor())
        received = []
        bridge.event.connect(lambda name, raw: received.append((name, json.loads(raw))))
        bridge.push_event("ping", {"value": 1})
        self.assertEqual(received, [("ping", {"value": 1})])


class AttachTest(unittest.TestCase):
    def setUp(self):
        qt_app()
        self.page = QWebEnginePage()
        self.addCleanup(self.page.deleteLater)
        self.bus = EventBus()
        self.connection = web_bridge.attach(self.page, FunctionRegistry({"add": lambda a, b: a + b}), self.bus)
        self.addCleanup(self.connection.close)

    def test_channel_is_set_and_bridge_registered(self):
        self.assertIs(self.page.webChannel(), self.connection.channel)
        registered = self.connection.channel.registeredObjects()
        self.assertIs(registered[web_bridge.CHANNEL_OBJECT_NAME], self.connection.bridge)

    def test_client_script_is_injected_with_function_names(self):
        script = self.page.scripts().findScript("python-bridge")
        self.assertFalse(script.isNull())
        self.assertIn('const __PYTHON_FUNCTIONS__ = ["add"];', script.sourceCode())
        self.assertIn("QWebChannel", script.sourceCode())
        self.assertIn("onPythonEvent", script.sourceCode())

    def test_bus_events_are_forwarded_to_bridge(self):
        received = []
        self.connection.bridge.event.connect(lambda name, raw: received.append(name))
        self.bus.publish("ping", {})
        self.assertEqual(received, ["ping"])

    def test_close_stops_forwarding_events(self):
        received = []
        self.connection.bridge.event.connect(lambda name, raw: received.append(name))
        self.connection.close()
        self.bus.publish("ping", {})
        self.assertEqual(received, [])


class QtResourceTest(unittest.TestCase):
    def test_missing_resource_raises(self):
        with self.assertRaises(FileNotFoundError):
            web_bridge._read_qt_resource(":/gibt/es/nicht.js")


if __name__ == "__main__":
    unittest.main()
