"""3D-Begleiter: durchsichtiges Fenster links neben dem Popup (Seite: frontend/companion.html).

Das Fenster folgt dem Popup (auch während es einfährt), erscheint und verschwindet mit ihm und nimmt
keinen Fokus an - ein Klick auf den Begleiter schließt das Popup also nicht. Es gehört zum Popup
(Qt-Elternfenster): Windows hält es damit immer direkt über dem Popup, statt es beim erneuten Öffnen
hinter andere Fenster zu legen (es wird ja nie selbst aktiviert). Links oder rechts vom Popup
stellt der Nutzer im Design-Panel ein. Was der Begleiter tut,
meldet das Popup über den EventBus (events.COMPANION, per notifyPython). Den Mauszeiger reicht dieses
Fenster an die Seite weiter, damit der Begleiter ihm mit dem Blick folgen kann.
"""
from __future__ import annotations

import json
from typing import Any

from PyQt5.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from backend import config
from backend.events import COMPANION, EventBus


SIDES = ("left", "right")


def companion_size(available: QRect, popup_height: int, height_ratio: float, aspect: float) -> tuple[int, int]:
    height = min(int(available.height() * height_ratio), popup_height)
    return int(height * aspect), height


def companion_geometry(popup: QRect, available: QRect, height_ratio: float, aspect: float, gap: int,
                       side: str = "left") -> QRect:
    """Neben dem Popup (side: "left" oder "right"), unten bündig; passt es dort nicht hin, auf der
    anderen Seite."""
    width, height = companion_size(available, popup.height(), height_ratio, aspect)
    top = popup.bottom() + 1 - height
    left_spot, right_spot = popup.left() - gap - width, popup.right() + 1 + gap
    fits_left, fits_right = left_spot >= available.left(), right_spot + width <= available.right() + 1
    left = right_spot if (side == "right" and fits_right) or not fits_left else left_spot
    left = max(available.left(), min(left, available.right() + 1 - width))
    top = max(available.top(), min(top, available.bottom() + 1 - height))
    return QRect(left, top, width, height)


class CompanionWindow(QWidget):
    # Aus jedem Thread: Begleiter ein- oder ausblenden (Einstellung im Design-Panel des Popups)
    visibility_requested = pyqtSignal(bool)

    # Aus jedem Thread: Seite wechseln ("left" oder "right")
    side_requested = pyqtSignal(str)

    def __init__(self, content: QWidget, popup: QWidget, event_bus: EventBus):
        super().__init__(popup)   # gehört zum Popup, liegt damit immer mit ihm oben (siehe oben)
        self.content = content
        self.popup = popup
        self.wanted = True   # vom Nutzer gewünscht (Design-Panel)
        self.side = "left"
        # Kein Fokus: Ein Klick auf den Begleiter darf das Popup nicht deaktivieren (es schlösse sich).
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
                            | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(content)

        self._pointer = QPoint(-1, -1)
        self._pointer_timer = QTimer(self)
        self._pointer_timer.setInterval(config.COMPANION_POINTER_MS)
        self._pointer_timer.timeout.connect(self._send_pointer)

        self.visibility_requested.connect(self.set_wanted)
        self.side_requested.connect(self.set_side)
        self._unsubscribe = event_bus.subscribe(self._on_event)
        popup.installEventFilter(self)

    # --- dem Popup folgen ----------------------------------------------------------------------
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt-API)
        if watched is self.popup:
            kind = event.type()
            if kind in (QEvent.Move, QEvent.Resize):
                self.follow()
            elif kind == QEvent.Show:
                self._show_beside_popup()
            elif kind == QEvent.WindowActivate and self.isVisible():
                self.raise_()
            elif kind == QEvent.Hide:
                self.hide()
        return super().eventFilter(watched, event)

    def follow(self) -> None:
        screen = self.popup.screen() if hasattr(self.popup, "screen") else None
        available = screen.availableGeometry() if screen is not None else self.popup.geometry()
        self.setGeometry(companion_geometry(self.popup.geometry(), available, config.COMPANION_HEIGHT_RATIO,
                                            config.COMPANION_ASPECT, config.COMPANION_GAP_PX, self.side))

    def _show_beside_popup(self) -> None:
        if not self.wanted:
            return
        self.follow()
        self.show()
        self.raise_()
        # Darstellung sicher fortsetzen: Seite war verborgen, ggf. ist der Grafikkontext neu
        self.content.page().runJavaScript("window.Companion && Companion.resume();")

    def set_wanted(self, wanted: bool) -> None:
        changed = self.wanted != bool(wanted)
        self.wanted = bool(wanted)
        if changed and self.side == "right" and hasattr(self.popup, "relayout"):
            self.popup.relayout()
        if self.wanted and self.popup.isVisible():
            self._show_beside_popup()
        elif not self.wanted:
            self.hide()

    def set_side(self, side: str) -> None:
        self.side = side if side in SIDES else "left"
        if hasattr(self.popup, "relayout"):
            self.popup.relayout()   # Popup rückt ggf. zur Seite, damit rechts Platz ist
        if self.isVisible():
            self.follow()

    def reserve(self) -> tuple[int, int]:
        """Platz, den das Popup am Bildschirmrand frei lassen soll (PopupWindow.side_reserve)."""
        if not self.wanted or self.side != "right":
            return 0, 0
        screen = self.popup.screen() if hasattr(self.popup, "screen") else None
        available = screen.availableGeometry() if screen is not None else self.popup.geometry()
        width, _ = companion_size(available, self.popup.height(), config.COMPANION_HEIGHT_RATIO,
                                  config.COMPANION_ASPECT)
        return 0, width + config.COMPANION_GAP_PX

    def _on_event(self, name: str, payload: Any) -> None:
        # Läuft im Thread des Senders - deshalb über Signale.
        if name != COMPANION or not isinstance(payload, dict):
            return
        if payload.get("kind") == "visible":
            self.visibility_requested.emit(bool(payload.get("value")))
        elif payload.get("kind") == "side" and payload.get("value") in SIDES:
            self.side_requested.emit(payload["value"])

    # --- Mauszeiger -----------------------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802
        self._pointer_timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802
        self._pointer_timer.stop()
        super().hideEvent(event)

    def _send_pointer(self) -> None:
        position = self.mapFromGlobal(QCursor.pos())
        if position == self._pointer:
            return
        self._pointer = position
        size = json.dumps([position.x(), position.y(), self.width(), self.height()])
        self.content.page().runJavaScript(f"window.Companion && Companion.pointer(...{size});")

    def contains_cursor(self) -> bool:
        return self.isVisible() and self.geometry().contains(QCursor.pos())

    def release(self) -> None:
        self._pointer_timer.stop()
        self._unsubscribe()
        self.popup.removeEventFilter(self)

    def closeEvent(self, event) -> None:  # noqa: N802
        event.ignore()
        self.hide()
