"""Setzt die Bausteine zusammen (Composition Root)."""
from __future__ import annotations

from PyQt5.QtWidgets import QApplication

from backend import api, config
from backend.bridge.function_registry import FunctionRegistry
from backend.desktop.popup_window import PopupWindow
from backend.desktop.tray_icon import TrayIcon
from backend.desktop.web_view import WebView
from backend.events import events


def create_popup() -> PopupWindow:
    view = WebView(config.POPUP_PAGE, FunctionRegistry.from_module(api), events, config.POPUP_BACKGROUND)
    return PopupWindow(view)


class Application:
    """Verbindet Tray-Icon und Popup mit der laufenden QApplication."""

    def __init__(self, qt_app: QApplication):
        qt_app.setQuitOnLastWindowClosed(False)

        self.popup = create_popup()
        self.tray = TrayIcon(config.TRAY_ICON, config.APP_NAME)
        self.tray.left_clicked.connect(self.popup.show_at_cursor)
        self.tray.quit_requested.connect(qt_app.quit)
        self.tray.show()

        qt_app.aboutToQuit.connect(self.shutdown)

    def shutdown(self) -> None:
        """Bridge-Thread beenden und Web-View freigeben (vermeidet WebEngine-Warnungen)."""
        self.tray.hide()
        self.popup.content.close_bridge()
        self.popup.content.deleteLater()
