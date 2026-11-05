"""Gemeinsame Hilfen für Tests, die Qt brauchen."""
from __future__ import annotations

from collections.abc import Callable

from PyQt5.QtCore import QEventLoop, QTimer

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
    qt_app()
    if condition():
        return True
    # macOS liefert WebEngine- und Cocoa-Ereignisse erst in einer echten Ereignisschleife.
    loop = QEventLoop()
    poll, timeout = QTimer(), QTimer()
    errors = []
    matched = []

    def check():
        try:
            if condition():
                matched.append(True)
                loop.quit()
        except Exception as error:
            errors.append(error)
            loop.quit()

    poll.timeout.connect(check)
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)
    poll.start(10)
    timeout.start(max(1, int(timeout_s * 1000)))
    loop.exec_()
    poll.stop()
    timeout.stop()
    if errors:
        raise errors[0]
    return bool(matched)


def run_js(page: QWebEnginePage, script: str, timeout_s: float = 10.0):
    """JavaScript ausführen und auf das Ergebnis warten."""
    result = []
    page.runJavaScript(script, result.append)
    if not wait_until(lambda: bool(result), timeout_s):
        raise TimeoutError(script)
    return result[0]
