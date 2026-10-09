"""Integrationstests: echte Web-Seite ruft Python-Funktionen auf und empfängt Backend-Ereignisse."""
import logging
import tempfile
import threading
import unittest
from pathlib import Path

from PyQt5.QtCore import QUrl

from tests.qt_helpers import qt_app, run_js, wait_until

from backend.bridge.function_registry import FunctionRegistry
from backend.desktop.web_view import WebView
from backend.events import EventBus

PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>
<script>
  add(2, 3).then(r => window.sum = r);
  fail().catch(e => window.errorMessage = e.message);
  thread_name().then(name => window.threadName = name);
  onPythonEvent("ping", payload => window.ping = payload.value);
</script>
</body></html>"""


def _fail():
    raise ValueError("broken")


class WebViewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt_app()
        logging.disable(logging.CRITICAL)  # erwartete Fehler-Logs nicht ausgeben
        cls._tmp = tempfile.TemporaryDirectory()
        cls.page_path = Path(cls._tmp.name) / "test.html"
        cls.page_path.write_text(PAGE, encoding="utf-8")
        registry = FunctionRegistry({
            "add": lambda a, b: a + b,
            "fail": _fail,
            "thread_name": lambda: threading.current_thread().name,
        })
        cls.bus = EventBus()
        cls.view = WebView(cls.page_path, registry, cls.bus, "#123456")
        loaded = []
        cls.view.loadFinished.connect(loaded.append)
        if not wait_until(lambda: loaded):
            raise TimeoutError("Seite nicht geladen")

    @classmethod
    def tearDownClass(cls):
        cls.view.close_bridge()
        cls.view.deleteLater()
        qt_app().processEvents()
        cls._tmp.cleanup()
        logging.disable(logging.NOTSET)

    def _wait_for_js(self, expression):
        self.assertTrue(wait_until(lambda: run_js(self.view.page(), expression) is not None),
                        f"{expression} wurde nicht gesetzt")
        return run_js(self.view.page(), expression)

    def test_loads_given_page(self):
        self.assertEqual(self.view.url(), QUrl.fromLocalFile(str(self.page_path)))

    def test_background_color(self):
        self.assertEqual(self.view.page().backgroundColor().name(), "#123456")

    def test_python_function_is_callable_from_javascript(self):
        self.assertEqual(self._wait_for_js("window.sum"), 5)

    def test_python_exception_rejects_promise(self):
        self.assertEqual(self._wait_for_js("window.errorMessage"), "broken")

    def test_calls_run_in_background_thread(self):
        self.assertTrue(self._wait_for_js("window.threadName").startswith("bridge"))

    def test_backend_event_reaches_javascript(self):
        self._wait_for_js("window.sum")   # Seite verbunden
        self.bus.publish("ping", {"value": 42})
        self.assertEqual(self._wait_for_js("window.ping"), 42)

    def test_only_registered_functions_exist(self):
        self.assertEqual(run_js(self.view.page(), "typeof does_not_exist"), "undefined")


if __name__ == "__main__":
    unittest.main()
