"""Setzt die Bausteine zusammen (Composition Root)."""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from PyQt5.QtWidgets import QApplication

from backend import api, config
from backend.assistant.skills import start_triggers
from backend.bridge.function_registry import FunctionRegistry
from backend.desktop.hotkey import GlobalHotkey
from backend.desktop.popup_window import PopupWindow
from backend.desktop.tray_icon import TrayIcon
from backend.desktop.web_view import WebView
from backend.events import POPUP_ENLARGED, PROACTIVE_NOTICE, EventBus, events

log = logging.getLogger(__name__)


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


def forward_proactive_notices(tray: TrayIcon, popup: PopupWindow, event_bus: EventBus,
                              open_popup: bool = config.PROACTIVE_OPEN_POPUP) -> Callable[[], None]:
    """Proaktive Meldungen (backend/proactive.py) sichtbar machen: das Popup öffnet sich von selbst
    wie bei einem Klick aufs Tray-Icon - oder (open_popup=False) eine Systembenachrichtigung,
    deren Klick das Popup öffnet. Gibt die Abmeldung zurück."""
    def forward(name: str, payload: Any) -> None:
        if name != PROACTIVE_NOTICE:
            return
        # Läuft im Thread des Auslösers - deshalb über Signale. "display" setzt die Einstellung im Popup.
        if payload.get("display", "popup" if open_popup else "notice") == "popup":
            popup.show_requested.emit()
        else:
            tray.notify_requested.emit(payload["title"], payload["text"], config.PROACTIVE_NOTICE_MS)

    return event_bus.subscribe(forward)


class ProactiveTrigger:
    """Startet eine proaktive Meldung im Hintergrund - das Sprachmodell braucht ein paar Sekunden,
    Tray und Tastenkürzel sollen so lange nicht blockieren. Solange eine läuft, zählt kein weiterer Druck."""

    def __init__(self, send: Callable[[str], Any] = api.proactive_message):
        self._send = send
        self._busy = threading.Lock()

    def fire(self, occasion: str = "demo") -> bool:
        """Gibt False zurück, wenn gerade schon eine Meldung entsteht."""
        if not self._busy.acquire(blocking=False):
            return False
        threading.Thread(target=self._run, args=(occasion,), name="proactive", daemon=True).start()
        return True

    def _run(self, occasion: str) -> None:
        try:
            self._send(occasion)
        except Exception:  # noqa: BLE001  # Hintergrund-Thread: nur protokollieren
            log.exception("Proaktive Meldung %r fehlgeschlagen", occasion)
        finally:
            self._busy.release()


class Application:
    """Verbindet Tray-Icon und Popup mit der laufenden QApplication."""

    def __init__(self, qt_app: QApplication):
        qt_app.setQuitOnLastWindowClosed(False)

        self.popup = create_popup()
        self.tray = TrayIcon(config.TRAY_ICON, config.APP_NAME)
        self.popup.anchor = self.tray.anchor
        self.popup.tray_geometry = self.tray.geometry
        self.tray.left_clicked.connect(self.popup.toggle_at_anchor)
        self.tray.quit_requested.connect(qt_app.quit)
        self.tray.show()

        # Proaktive Meldungen: Test-Makro (Tastenkürzel) und Tray-Menü lösen die Vorführung aus.
        self.proactive = ProactiveTrigger()
        self.hotkey = GlobalHotkey(config.PROACTIVE_HOTKEY)
        self.hotkey.triggered.connect(self.proactive.fire)
        self.tray.proactive_test_requested.connect(self.proactive.fire)
        self.tray.messageClicked.connect(self.popup.show_requested.emit)
        if self.hotkey.registered:
            self.tray.setToolTip(f"{config.APP_NAME} - Test-Meldung: {config.PROACTIVE_HOTKEY}")

        self._unsubscribe = [forward_popup_events(self.popup, events),
                             forward_proactive_notices(self.tray, self.popup, events)]
        self.watcher = api._proactive_watcher() if config.PROACTIVE_WATCH else None
        if self.watcher is not None:
            self.watcher.start()   # meldet sich von selbst bei Mails, Aufgaben und Terminen
        self.stop_triggers = start_triggers()   # autonome Fähigkeiten, z. B. Reise-Erinnerung
        qt_app.aboutToQuit.connect(self.shutdown)

    def shutdown(self) -> None:
        """Bridge-Thread beenden und Web-View freigeben (vermeidet WebEngine-Warnungen)."""
        self.stop_triggers()
        if self.watcher is not None:
            self.watcher.stop()
        for unsubscribe in self._unsubscribe:
            unsubscribe()
        self._unsubscribe = []
        self.hotkey.unregister()
        self.tray.hide()
        self.popup.hide()
        self.popup.release_desktop_resources()
        self.popup.content.close_bridge()
        self.popup.content.deleteLater()
