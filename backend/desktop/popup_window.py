"""Rahmenloses Fenster am Menüleisten- oder Taskleistensymbol."""
from __future__ import annotations

from collections.abc import Callable
import sys

from PyQt5.QtCore import QEvent, QEasingCurve, QPoint, QPropertyAnimation, QRect, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QCursor, QGuiApplication
from PyQt5.QtWidgets import QApplication, QVBoxLayout, QWidget

from backend import config
from backend.desktop.foreground import bring_to_front


def popup_geometry(anchor: QPoint, available: QRect, width: int, height: int, from_top: bool) -> QRect:
    """In logischen Bildschirmkoordinaten positionieren; auch kleine und weitere Monitore beachten."""
    width, height = min(width, available.width()), min(height, available.height())
    left = anchor.x() - (width // 2 if from_top else width)
    top = max(anchor.y(), available.top()) if from_top else anchor.y() - height
    left = max(available.left(), min(left, available.right() - width + 1))
    top = max(available.top(), min(top, available.bottom() - height + 1))
    return QRect(left, top, width, height)


class PopupWindow(QWidget):
    # Darf aus jedem Thread gesendet werden (z. B. Bridge-Aufruf) - Qt führt set_enlarged im Haupt-Thread aus.
    enlarge_requested = pyqtSignal(bool)
    # Ebenso aus jedem Thread: Popup von selbst öffnen (proaktive Meldung), wie bei einem Klick
    # aufs Tray-Icon - an dem Punkt, den anchor() liefert (Application: Mitte des Tray-Icons).
    show_requested = pyqtSignal()
    outside_click_detected = pyqtSignal()

    def __init__(self, content: QWidget):
        super().__init__()
        self._enlarged = False
        self._last_anchor: QPoint | None = None
        self._outside_click_monitor = None
        self.anchor: Callable[[], QPoint] = lambda: (self._screen().availableGeometry().topRight()
                                                    if sys.platform == "darwin"
                                                    else self._screen().availableGeometry().bottomRight())
        self.tray_geometry: Callable[[], QRect] = QRect
        self.enlarge_requested.connect(self.set_enlarged)
        self.show_requested.connect(self._on_show_requested)
        self.outside_click_detected.connect(self._hide_after_outside_click)
        # Qt.Popup fängt Klicks aufs Tray-Icon selbst ab und verliert unter Cocoa den Fokus.
        # Ohne System-Schatten: der ist unter Windows immer rechteckig und passt nicht zu runden Ecken.
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        if sys.platform == "darwin":
            self.setAttribute(Qt.WA_MacAlwaysShowToolWindow, True)
            QApplication.instance().installEventFilter(self)
        # Durchsichtiges Fenster: Die Seite zeichnet ihre Form selbst (Ecken je nach Design, siehe
        # --window-radius in frontend/theme.css) - geglättet und in beliebiger Größe, was Windows
        # selbst nicht kann (höchstens ca. 8 px). Die Web-Ansicht braucht dafür einen durchsichtigen
        # Seitenhintergrund (config.POPUP_BACKGROUND).
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self.content = content
        layout = QVBoxLayout(self)
        margin = config.POPUP_MARGIN_PX
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.addWidget(content)

        self._animation = QPropertyAnimation(self, b"geometry")
        self._animation.setDuration(config.POPUP_ANIMATION_MS)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)

    def show_at_cursor(self) -> None:
        """Popup so öffnen, dass seine untere rechte Ecke am Mauszeiger liegt."""
        self.show_at(QCursor.pos())

    def toggle_at_anchor(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.show_at(self.anchor(), take_focus=sys.platform == "darwin")

    def show_at(self, corner: QPoint, take_focus: bool = False) -> None:
        """Popup am Symbol einfahren lassen: macOS darunter, Windows darüber.

        take_focus: Fokus anfordern, auch wenn die App bisher im Hintergrund war.
        """
        self._show_with_corner(corner)
        if take_focus:
            bring_to_front(int(self.winId()))
        self.raise_()
        self.activateWindow()
        if sys.platform == "darwin" and self._outside_click_monitor is None:
            from backend.desktop.macos import OutsideClickMonitor
            self._outside_click_monitor = OutsideClickMonitor(self.outside_click_detected.emit)

    def _on_show_requested(self) -> None:
        if not self.isVisible():   # ist es schon offen, steht die Meldung ohnehin im Chat
            self.show_at(self.anchor(), take_focus=True)

    def _show_with_corner(self, corner: QPoint) -> None:
        self._last_anchor = QPoint(corner)
        self._animation.stop()
        width, height = self._target_size()
        end = popup_geometry(corner, self._screen().availableGeometry(), width, height, sys.platform == "darwin")
        self.setFixedSize(end.size())
        start = (end.translated(0, -min(24, config.POPUP_SLIDE_IN_OFFSET_PX)) if sys.platform == "darwin"
                 else end.translated(width, height + config.POPUP_SLIDE_IN_OFFSET_PX))
        self.setGeometry(start)
        self._animation.setStartValue(start)
        self._animation.setEndValue(end)
        self._animation.start()
        self.show()

    @property
    def enlarged(self) -> bool:
        return self._enlarged

    def set_enlarged(self, enlarged: bool) -> None:
        """Größe umschalten und die zum Symbol gerichtete Fensterkante beibehalten."""
        self._enlarged = enlarged
        if not self.isVisible():
            return   # gilt beim nächsten show_at_cursor
        self._animation.stop()
        width, height = self._target_size()
        from_top = sys.platform == "darwin"
        corner = (self._last_anchor or self.anchor()) if from_top else self.geometry().bottomRight() + QPoint(1, 1)
        rect = popup_geometry(corner, self._screen().availableGeometry(), width, height, from_top)
        self.setFixedSize(rect.size())
        self.setGeometry(rect)

    def _target_size(self) -> tuple[int, int]:
        geo = self._screen().geometry()
        width_ratio, height_ratio = config.POPUP_ENLARGED_SIZE_RATIO if self._enlarged else config.POPUP_SIZE_RATIO
        return int(geo.width() * width_ratio), int(geo.height() * height_ratio)

    def _screen(self):
        return QGuiApplication.screenAt(self._last_anchor or QCursor.pos()) or QGuiApplication.primaryScreen()

    def hideEvent(self, event) -> None:  # noqa: N802
        self._animation.stop()
        if self._outside_click_monitor is not None:
            self._outside_click_monitor.close()
            self._outside_click_monitor = None
        super().hideEvent(event)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if self.isVisible() and event.type() == QEvent.MouseButtonPress:
            if QApplication.activePopupWidget() is not None:
                return super().eventFilter(watched, event)
            pos = event.globalPos()
            if not self.geometry().contains(pos) and not self.tray_geometry().contains(pos):
                self.hide()
        return super().eventFilter(watched, event)

    def changeEvent(self, event) -> None:  # noqa: N802
        if sys.platform != "darwin" and event.type() == QEvent.ActivationChange:
            QTimer.singleShot(0, self._hide_if_inactive)
        super().changeEvent(event)

    def _hide_if_inactive(self) -> None:
        active = QApplication.activeWindow()
        if QApplication.activePopupWidget() is not None or (active is not None and self.isAncestorOf(active)):
            return
        if self.isVisible() and not self.isActiveWindow():
            self._hide_after_outside_click()

    def _hide_after_outside_click(self) -> None:
        # Den Klick auf das Symbol verarbeitet ausschließlich das Tray-Signal.
        if not self.tray_geometry().contains(QCursor.pos()):
            self.hide()

    def release_desktop_resources(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        if self._outside_click_monitor is not None:
            self._outside_click_monitor.close()
            self._outside_click_monitor = None

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt-API)
        # Nur verstecken: Inhalt und Zustand der Seite bleiben erhalten.
        event.ignore()
        self.hide()
