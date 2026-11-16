"""3D-Begleiter: durchsichtiges Fenster links neben dem Popup (Seite: frontend/companion.html).

Das Fenster folgt dem Popup (auch während es einfährt), erscheint und verschwindet mit ihm und nimmt
keinen Fokus an - ein Klick auf den Begleiter schließt das Popup also nicht. Es gehört zum Popup
(Qt-Elternfenster): Windows hält es damit immer direkt über dem Popup, statt es beim erneuten Öffnen
hinter andere Fenster zu legen (es wird ja nie selbst aktiviert). Links oder rechts vom Popup
stellt der Nutzer im Design-Panel ein. Was der Begleiter tut,
meldet das Popup über den EventBus (events.COMPANION, per notifyPython). Den Mauszeiger reicht dieses
Fenster an die Seite weiter, damit der Begleiter ihm mit dem Blick folgen kann.

Runde ums Popup (Modell-Option "click": "lap", z. B. das Auto): Nach einem Klick meldet die Seite
events.COMPANION_LAP. Der Begleiter fährt dann einen Kreis in die Tiefe (lap_frame): von seinem Platz nach
hinten weg, hinter dem Popup entlang (kleiner, etwas höher; eine Fenstermaske blendet aus, was das Popup
verdeckt), auf der anderen Seite herum und vor dem Popup zurück. Fahrtrichtung und Größe bekommt die Seite
in jedem Schritt (Companion.drive), damit das Modell sich in Fahrtrichtung dreht.
"""
from __future__ import annotations

import json
import math
import time
from typing import Any

from PyQt5.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QCursor, QRegion
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from backend import config
from backend.events import COMPANION, COMPANION_LAP, EventBus


SIDES = ("left", "right")
LAP_SECONDS = 3.2                     # Dauer einer Runde ums Popup
LAP_FRAME_MS = 16
LAP_FAR_SCALE = 0.62                  # so groß ist der Begleiter ganz hinten
LAP_FAR_LIFT = 0.22                   # so viel höher (Anteil seiner Höhe) - weiter weg wirkt höher


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


class LapFrame:
    """Ein Schritt der Runde: Fensterplatz, Fahrtrichtung (Grad, 0 = zum Betrachter, 90 = nach rechts,
    180 = vom Betrachter weg), Größe und ob der Begleiter gerade hinter dem Popup fährt."""

    def __init__(self, position: QPoint, heading: float, scale: float, behind: bool):
        self.position, self.heading, self.scale, self.behind = position, heading, scale, behind


def lap_frame(home: QRect, popup: QRect, progress: float) -> LapFrame:
    """Kreis in die Tiefe um die Mitte des Popups, beginnend und endend am Platz (home).
    progress 0..1; zuerst geht es nach hinten, dann vor dem Popup zurück."""
    angle = 2 * math.pi * progress
    popup_center = popup.left() + popup.width() / 2
    home_center = home.left() + home.width() / 2
    radius = home_center - popup_center   # negativ: steht links vom Popup
    depth = math.sin(angle)               # > 0: hinter dem Popup
    far = max(0.0, depth)
    center = popup_center + radius * math.cos(angle)
    left = round(center - home.width() / 2)
    top = round(home.top() - LAP_FAR_LIFT * home.height() * far)
    # Richtung = Ableitung der Bahn: seitlich -radius*sin, in die Tiefe (zum Betrachter) -cos
    sideways = -math.copysign(1.0, radius) * math.sin(angle)
    heading = math.degrees(math.atan2(sideways, -math.cos(angle)))
    return LapFrame(QPoint(left, top), heading, 1 - (1 - LAP_FAR_SCALE) * far, depth > 0)


def _ease(t: float) -> float:
    return 2 * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 2 / 2


class CompanionWindow(QWidget):
    # Aus jedem Thread: Begleiter ein- oder ausblenden (Einstellung im Design-Panel des Popups)
    visibility_requested = pyqtSignal(bool)

    # Aus jedem Thread: Seite wechseln ("left" oder "right")
    side_requested = pyqtSignal(str)

    # Aus jedem Thread: einmal ums Popup fahren (die Seite wurde angeklickt)
    lap_requested = pyqtSignal()

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

        self._lap_home: QRect | None = None   # Platz neben dem Popup während einer Runde, sonst None
        self._lap_started = 0.0
        self._lap_timer = QTimer(self)
        self._lap_timer.setInterval(LAP_FRAME_MS)
        self._lap_timer.timeout.connect(self._drive_lap)

        self.visibility_requested.connect(self.set_wanted)
        self.side_requested.connect(self.set_side)
        self.lap_requested.connect(self.start_lap)
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
                self._end_lap()
                self.hide()
        return super().eventFilter(watched, event)

    def follow(self) -> None:
        self._end_lap()   # Popup bewegt sich oder die Seite wechselt: Runde abbrechen, zurück an den Platz
        self.setGeometry(self._home())

    def _home(self) -> QRect:
        screen = self.popup.screen() if hasattr(self.popup, "screen") else None
        available = screen.availableGeometry() if screen is not None else self.popup.geometry()
        return companion_geometry(self.popup.geometry(), available, config.COMPANION_HEIGHT_RATIO,
                                  config.COMPANION_ASPECT, config.COMPANION_GAP_PX, self.side)

    # --- Runde ums Popup ------------------------------------------------------------------------
    @property
    def lapping(self) -> bool:
        return self._lap_home is not None

    def start_lap(self) -> None:
        if self.lapping or not self.isVisible():
            return
        self._lap_home = self._home()
        self.setGeometry(self._lap_home)
        self._lap_started = time.monotonic()
        self._lap_timer.start()
        self._drive_lap()

    def _drive_lap(self) -> None:
        home = self._lap_home
        if home is None:
            return
        progress = min(1.0, (time.monotonic() - self._lap_started) / LAP_SECONDS)
        if progress >= 1.0:
            self.follow()
            return
        step = lap_frame(home, self.popup.geometry(), _ease(progress))
        self.move(step.position)
        self._mask_lap(step.behind)
        self.content.page().runJavaScript(
            f"window.Companion && Companion.drive({step.heading:.1f}, {step.scale:.3f});")

    def _mask_lap(self, behind: bool) -> None:
        """Nur auf dem Bildschirm zeichnen; hinter dem Popup verdeckt es den Begleiter."""
        screen = self.popup.screen() if hasattr(self.popup, "screen") else None
        visible = QRegion(screen.availableGeometry()) if screen is not None else QRegion(self.geometry())
        if behind:
            visible = visible.subtracted(QRegion(self.popup.geometry()))
        self.setMask(visible.translated(-self.x(), -self.y()))

    def _end_lap(self) -> None:
        if self._lap_home is None:
            return
        self._lap_home = None
        self._lap_timer.stop()
        self.clearMask()
        self.content.page().runJavaScript("window.Companion && Companion.drive(null);")   # wieder zum Betrachter

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
        if name == COMPANION_LAP:
            self.lap_requested.emit()
            return
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
        self._lap_timer.stop()
        self._unsubscribe()
        self.popup.removeEventFilter(self)

    def closeEvent(self, event) -> None:  # noqa: N802
        event.ignore()
        self.hide()
