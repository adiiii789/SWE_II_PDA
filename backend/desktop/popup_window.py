"""Rahmenloses Fenster am Menüleisten- oder Taskleistensymbol."""
from __future__ import annotations

from collections.abc import Callable
import sys

from PyQt5.QtCore import (QEvent, QEasingCurve, QPoint, QParallelAnimationGroup, QPropertyAnimation,
                          QRect, QRectF, Qt, QTimer, pyqtSignal)
from PyQt5.QtGui import QCursor, QGuiApplication, QPainterPath, QRegion
from PyQt5.QtWidgets import QApplication, QVBoxLayout, QWidget

from backend import config
from backend.desktop.foreground import bring_to_front
from backend.desktop.motion import reduce_motion


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
        self._closing = False
        self._native_rounded = False
        self.anchor: Callable[[], QPoint] = lambda: (self._screen().availableGeometry().topRight()
                                                    if sys.platform == "darwin"
                                                    else self._screen().availableGeometry().bottomRight())
        self.tray_geometry: Callable[[], QRect] = QRect
        self.enlarge_requested.connect(self.set_enlarged)
        self.show_requested.connect(self._on_show_requested)
        self.outside_click_detected.connect(self._dismiss_on_outside_click)
        self.setObjectName("popupRoot")
        # Tool-Fenster erlauben eine Schließanimation, bevor die Fläche versteckt wird.
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        if sys.platform == "darwin":
            self.setAttribute(Qt.WA_MacAlwaysShowToolWindow, True)
            QApplication.instance().installEventFilter(self)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"#popupRoot {{ background: {config.POPUP_BACKGROUND}; }}")

        self.content = content
        layout = QVBoxLayout(self)
        margin = config.POPUP_MARGIN_PX
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.addWidget(content)

        self._animation = QPropertyAnimation(self, b"geometry")
        self._animation.setDuration(config.POPUP_ANIMATION_MS)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self._opacity_animation = QPropertyAnimation(self, b"windowOpacity")
        self._opacity_animation.setDuration(config.POPUP_ANIMATION_MS)
        self._opacity_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._open_animation = QParallelAnimationGroup(self)
        self._open_animation.addAnimation(self._animation)
        self._open_animation.addAnimation(self._opacity_animation)
        self._close_geometry = QPropertyAnimation(self, b"geometry")
        self._close_opacity = QPropertyAnimation(self, b"windowOpacity")
        self._close_animation = QParallelAnimationGroup(self)
        for animation in (self._close_geometry, self._close_opacity):
            animation.setDuration(config.POPUP_CLOSE_ANIMATION_MS)
            animation.setEasingCurve(QEasingCurve.InCubic)
            self._close_animation.addAnimation(animation)
        self._close_animation.finished.connect(self._finish_dismiss)

    def show_at_cursor(self) -> None:
        """Popup so öffnen, dass seine untere rechte Ecke am Mauszeiger liegt."""
        self.show_at(QCursor.pos())

    def toggle_at_anchor(self) -> None:
        if self.isVisible():
            self.dismiss()
        else:
            self.show_at(self.anchor(), take_focus=sys.platform == "darwin")

    def show_at(self, corner: QPoint, take_focus: bool = False) -> None:
        """Popup am Symbol einfahren lassen: macOS darunter, Windows darüber.

        take_focus: Fokus auch ohne Klick des Nutzers holen (backend/desktop/foreground.py) -
        sonst gibt Windows ihn nicht her, und ein Qt.Popup schließt sich sofort wieder.
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
        if not self.isVisible() or self._closing:
            self.show_at(self.anchor(), take_focus=True)

    def _show_with_corner(self, corner: QPoint) -> None:
        self._last_anchor = QPoint(corner)
        was_visible = self.isVisible()
        previous_opacity = self.windowOpacity()
        self._open_animation.stop()
        self._close_animation.stop()
        self._closing = False
        width, height = self._target_size()
        end = popup_geometry(corner, self._screen().availableGeometry(), width, height, sys.platform == "darwin")
        self.setFixedSize(end.size())
        direction = -1 if sys.platform == "darwin" else 1
        start = self.geometry() if was_visible else end.translated(0, direction * config.POPUP_SLIDE_IN_OFFSET_PX)
        duration = 0 if reduce_motion() else config.POPUP_ANIMATION_MS
        self._animation.setDuration(duration)
        self._opacity_animation.setDuration(duration)
        self._opacity_animation.setStartValue(previous_opacity if was_visible else 0.0)
        self._opacity_animation.setEndValue(1.0)
        self.setGeometry(start)
        self._animation.setStartValue(start)
        self._animation.setEndValue(end)
        self.setWindowOpacity(previous_opacity if was_visible else 0.0)
        self.show()
        self._apply_rounding()
        self._open_animation.start()

    def dismiss(self) -> None:
        """Kurz in Richtung des Symbols ausblenden; Chat und Web-Seite bleiben erhalten."""
        if not self.isVisible() or self._closing:
            return
        self._open_animation.stop()
        if reduce_motion():
            self.hide()
            return
        self._closing = True
        start = self.geometry()
        direction = -1 if sys.platform == "darwin" else 1
        self._close_geometry.setStartValue(start)
        self._close_geometry.setEndValue(start.translated(0, direction * 8))
        self._close_opacity.setStartValue(self.windowOpacity())
        self._close_opacity.setEndValue(0.0)
        self._close_animation.start()

    def _finish_dismiss(self) -> None:
        if self._closing:
            self.hide()

    @property
    def enlarged(self) -> bool:
        return self._enlarged

    def set_enlarged(self, enlarged: bool) -> None:
        """Größe umschalten und die zum Symbol gerichtete Fensterkante beibehalten."""
        self._enlarged = enlarged
        if not self.isVisible():
            return   # gilt beim nächsten show_at_cursor
        self._open_animation.stop()
        self._close_animation.stop()
        self._closing = False
        self.setWindowOpacity(1.0)
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
        self._open_animation.stop()
        self._close_animation.stop()
        self._closing = False
        if self._outside_click_monitor is not None:
            self._outside_click_monitor.close()
            self._outside_click_monitor = None
        super().hideEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        self._apply_rounding()
        super().resizeEvent(event)

    def _apply_rounding(self) -> None:
        if sys.platform == "darwin":
            from backend.desktop.macos import round_window
            self._native_rounded = round_window(int(self.winId()), config.POPUP_CORNER_RADIUS_PX)
            if self._native_rounded:
                self.clearMask()
                return
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), config.POPUP_CORNER_RADIUS_PX, config.POPUP_CORNER_RADIUS_PX)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def changeEvent(self, event) -> None:  # noqa: N802
        if sys.platform != "darwin" and event.type() == QEvent.ActivationChange:
            QTimer.singleShot(0, self._dismiss_if_inactive)
        super().changeEvent(event)

    def _dismiss_if_inactive(self) -> None:
        app = QApplication.instance()
        active = app.activeWindow()
        if app.activePopupWidget() is not None or (active is not None and self.isAncestorOf(active)):
            return
        if self.isVisible() and not self.isActiveWindow():
            self._dismiss_on_outside_click()

    def _dismiss_on_outside_click(self) -> None:
        # Das Tray-Signal verarbeitet den Klick auf das Symbol selbst.
        if not self.tray_geometry().contains(QCursor.pos()):
            self.dismiss()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if self.isVisible() and event.type() == QEvent.MouseButtonPress:
            if QApplication.activePopupWidget() is not None:
                return super().eventFilter(watched, event)
            pos = event.globalPos()
            if not self.geometry().contains(pos) and not self.tray_geometry().contains(pos):
                self.dismiss()
        return super().eventFilter(watched, event)

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
        self.dismiss()
