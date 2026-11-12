"""Web-Ansicht, deren Seite Python-Funktionen aufrufen und Backend-Ereignisse empfangen kann."""
from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QColor
from PyQt5.QtWebEngineWidgets import QWebEngineView

from backend.bridge import web_bridge
from backend.bridge.function_registry import FunctionRegistry
from backend.events import EventBus


class WebView(QWebEngineView):
    def __init__(self, page_path: Path, registry: FunctionRegistry, event_bus: EventBus, background: str,
                 notifications: frozenset[str] = frozenset(), query: str = ""):
        super().__init__()
        self.page().setBackgroundColor(QColor(background))  # kein weißes Aufblitzen beim Laden
        self._connection = web_bridge.attach(self.page(), registry, event_bus, notifications)
        url = QUrl.fromLocalFile(str(page_path))
        if query:
            url.setQuery(query)   # z. B. model=file:///... für den Begleiter
        self.load(url)

    def close_bridge(self) -> None:
        """Hintergrund-Thread beenden und keine Ereignisse mehr annehmen."""
        self._connection.close()
