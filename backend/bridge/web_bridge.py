"""Verbindet eine Web-Seite mit einer FunctionRegistry und dem EventBus.

JavaScript -> Python: Aufrufe laufen in einem Hintergrund-Thread, damit langsame
    Funktionen (z. B. ein Sprachmodell) das Popup nicht einfrieren. Das Ergebnis
    kommt über das Signal  finished(call_id, json)  zurück.
Python -> JavaScript: Ereignisse aus backend.events gehen über das Signal
    event(name, json)  an  onPythonEvent(name, handler)  im Frontend.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PyQt5.QtCore import QFile, QIODevice, QObject, pyqtSignal, pyqtSlot
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWebEngineWidgets import QWebEnginePage, QWebEngineScript

from backend.bridge.function_registry import FunctionRegistry, UnknownFunctionError
from backend.events import EventBus

log = logging.getLogger(__name__)

CHANNEL_OBJECT_NAME = "bridge"
_QWEBCHANNEL_JS = ":/qtwebchannel/qwebchannel.js"
_CLIENT_JS = Path(__file__).with_name("bridge_client.js")


class WebBridge(QObject):
    """Wird per QWebChannel ins JavaScript gereicht; Antworten sind JSON-Umschläge."""

    finished = pyqtSignal(int, str)   # call_id, {"ok": ..., "result"/"error": ...}
    event = pyqtSignal(str, str)      # Ereignisname, Payload als JSON

    def __init__(self, registry: FunctionRegistry, executor: Executor, parent: QObject | None = None):
        super().__init__(parent)
        self._registry = registry
        self._executor = executor
        self._closed = False

    @pyqtSlot(int, str, str)
    def call(self, call_id: int, name: str, args_json: str) -> None:
        """Wird aus JavaScript aufgerufen; die Antwort kommt später über finished.

        Darf nie eine Exception werfen: PyQt beendet bei einer Exception in einem
        Slot das ganze Programm.
        """
        if self._closed:
            self.finished.emit(call_id, _error("Bridge ist geschlossen"))
            return
        try:
            self._executor.submit(self._run, call_id, name, args_json)
        except RuntimeError as exc:   # Executor bereits beendet
            self.finished.emit(call_id, _error(str(exc)))

    def close(self) -> None:
        """Keine neuen Aufrufe mehr annehmen und keine Ergebnisse mehr senden."""
        self._closed = True

    def _run(self, call_id: int, name: str, args_json: str) -> None:
        result = self.invoke(name, args_json)
        if not self._closed:
            # Signale dürfen aus jedem Thread gesendet werden; Qt stellt sie im Haupt-Thread zu.
            self.finished.emit(call_id, result)

    def invoke(self, name: str, args_json: str) -> str:
        """Funktion ausführen und das Ergebnis als JSON-Umschlag liefern (wirft nie)."""
        try:
            result = self._registry.call(name, json.loads(args_json or "[]"))
            return json.dumps({"ok": True, "result": result})
        except UnknownFunctionError as exc:
            log.warning("%s", exc)
            return _error(str(exc))
        except Exception as exc:  # noqa: BLE001  # Fehler ans Frontend melden statt abstürzen
            log.exception("Aufruf von %r fehlgeschlagen", name)
            return _error(str(exc))

    def push_event(self, name: str, payload: Any) -> None:
        if not self._closed:
            self.event.emit(name, json.dumps(payload))


def _error(message: str) -> str:
    return json.dumps({"ok": False, "error": message})


@dataclass(frozen=True)
class BridgeConnection:
    """Muss vom Aufrufer gehalten werden - sonst räumt Python die Bridge weg und
    das JavaScript sieht ihre Slots nicht mehr. close() beim Beenden aufrufen."""

    channel: QWebChannel
    bridge: WebBridge
    executor: Executor
    unsubscribe: Callable[[], None]

    def close(self) -> None:
        self.bridge.close()
        self.unsubscribe()
        # Nicht warten: ein laufender Aufruf (z. B. Sprachmodell) soll das Beenden nicht aufhalten.
        self.executor.shutdown(wait=False, cancel_futures=True)


def attach(page: QWebEnginePage, registry: FunctionRegistry, event_bus: EventBus) -> BridgeConnection:
    """Registriert die Bridge auf der Seite und injiziert das Client-Skript in jedes Dokument."""
    # Ein Worker: Aufrufe laufen nacheinander - der Assistent muss nicht thread-sicher sein.
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bridge")
    bridge = WebBridge(registry, executor, page)
    channel = QWebChannel(page)
    channel.registerObject(CHANNEL_OBJECT_NAME, bridge)
    page.setWebChannel(channel)
    unsubscribe = event_bus.subscribe(bridge.push_event)

    script = QWebEngineScript()
    script.setName("python-bridge")
    script.setInjectionPoint(QWebEngineScript.DocumentCreation)
    script.setWorldId(QWebEngineScript.MainWorld)
    script.setSourceCode(_client_source(registry.names))
    page.scripts().insert(script)
    return BridgeConnection(channel, bridge, executor, unsubscribe)


def _client_source(function_names: list[str]) -> str:
    return "\n".join((
        _read_qt_resource(_QWEBCHANNEL_JS),
        f"const __PYTHON_FUNCTIONS__ = {json.dumps(function_names)};",
        _CLIENT_JS.read_text(encoding="utf-8"),
    ))


def _read_qt_resource(path: str) -> str:
    file = QFile(path)
    if not file.open(QIODevice.ReadOnly):
        raise FileNotFoundError(path)
    try:
        return bytes(file.readAll()).decode("utf-8")
    finally:
        file.close()
