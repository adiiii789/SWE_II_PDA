"""Setzt die Bausteine zusammen (Composition Root)."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PyQt5.QtWidgets import QApplication

from backend import api, config
from backend.bridge.function_registry import FunctionRegistry
from backend.desktop.popup_window import PopupWindow
from backend.desktop.tray_icon import TrayIcon
from backend.desktop.web_view import WebView
from backend.events import POPUP_ENLARGED, EventBus, events


def create_popup() -> PopupWindow:
    view = WebView(config.POPUP_PAGE, FunctionRegistry.from_module(api), events, config.POPUP_BACKGROUND)
    return PopupWindow(view)


def forward_popup_events(popup: PopupWindow, event_bus: EventBus) -> Callable[[], None]:
    """Ereignisse fürs Fenster (z. B. vergrößern) ans Popup weiterleiten; gibt die Abmeldung zurück.

    Der Handler kennt nur das Popup, nicht die Application - sonst entstünde ein
    Referenzzyklus und Qt-Objekte würden erst irgendwann vom GC freigegeben.
    """
    def forward(name: str, payload: Any) -> None:
        # Läuft im Thread des Senders - deshalb über das Signal statt direkt am Fenster.
        if name == POPUP_ENLARGED:
            popup.enlarge_requested.emit(bool(payload))

    return event_bus.subscribe(forward)


class Application:
    """Verbindet Tray-Icon und Popup mit der laufenden QApplication."""

    def __init__(self, qt_app: QApplication):
        qt_app.setQuitOnLastWindowClosed(False)

        self.popup = create_popup()
        self.tray = TrayIcon(config.TRAY_ICON, config.APP_NAME)
        self.tray.left_clicked.connect(self.popup.show_at_cursor)
        self.tray.quit_requested.connect(qt_app.quit)
        self.tray.show()

        self._unsubscribe = forward_popup_events(self.popup, events)
        qt_app.aboutToQuit.connect(self.shutdown)

    def shutdown(self) -> None:
        """Bridge-Thread beenden und Web-View freigeben (vermeidet WebEngine-Warnungen)."""
        self._unsubscribe()
        self.tray.hide()
        self.popup.content.close_bridge()
        self.popup.content.deleteLater()
