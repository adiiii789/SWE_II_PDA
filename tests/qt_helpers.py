"""Gemeinsame Hilfen für Tests, die Qt brauchen."""
from __future__ import annotations

import time
from collections.abc import Callable

from PyQt5.QtWebEngineWidgets import QWebEnginePage  # muss vor QApplication importiert sein
from PyQt5.QtWidgets import QApplication

_APP: QApplication | None = None


def qt_app() -> QApplication:
    """Die eine QApplication des Testlaufs (Qt erlaubt nur eine pro Prozess).

    Die Referenz liegt modulweit, weil unittest Testobjekte nach dem Lauf
    freigibt - sonst würde Python die QApplication zwischendurch zerstören.
    """
    global _APP  # noqa: PLW0603
    if _APP is None:
        _APP = QApplication.instance() or QApplication([])
    return _APP


def wait_until(condition: Callable[[], bool], timeout_s: float = 10.0) -> bool:
    """Qt-Events verarbeiten, bis condition() wahr ist oder die Zeit abläuft."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        qt_app().processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


def run_js(page: QWebEnginePage, script: str, timeout_s: float = 10.0):
    """JavaScript ausführen und auf das Ergebnis warten."""
    result = []
    page.runJavaScript(script, result.append)
    if not wait_until(lambda: bool(result), timeout_s):
        raise TimeoutError(script)
    return result[0]
