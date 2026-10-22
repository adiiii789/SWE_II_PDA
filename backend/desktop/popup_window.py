"""Rahmenloses Popup, das an der Mausposition (Tray) einfährt."""
from __future__ import annotations

from PyQt5.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt, pyqtSignal
from PyQt5.QtGui import QCursor, QGuiApplication
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from backend import config


class PopupWindow(QWidget):
    # Darf aus jedem Thread gesendet werden (z. B. Bridge-Aufruf) - Qt führt set_enlarged im Haupt-Thread aus.
    enlarge_requested = pyqtSignal(bool)

    def __init__(self, content: QWidget):
        super().__init__()
        self._enlarged = False
        self.enlarge_requested.connect(self.set_enlarged)
        self.setObjectName("popupRoot")
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
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

    def show_at_cursor(self) -> None:
        """Popup so öffnen, dass seine untere rechte Ecke am Mauszeiger liegt."""
        width, height = self._target_size()
        self.setFixedSize(width, height)
        cursor = QCursor.pos()
        end = QRect(cursor.x() - width, cursor.y() - height, width, height)
        start = end.translated(width, height + config.POPUP_SLIDE_IN_OFFSET_PX)
        self._animation.setStartValue(start)
        self._animation.setEndValue(end)
        self._animation.start()
        self.show()
        self.activateWindow()

    @property
    def enlarged(self) -> bool:
        return self._enlarged

    def set_enlarged(self, enlarged: bool) -> None:
        """Größe umschalten; die untere rechte Ecke bleibt, wo sie ist (passt auf den Bildschirm)."""
        self._enlarged = enlarged
        if not self.isVisible():
            return   # gilt beim nächsten show_at_cursor
        self._animation.stop()
        width, height = self._target_size()
        corner = self.geometry().bottomRight()
        available = self._screen().availableGeometry()
        right = min(corner.x(), available.right())
        bottom = min(corner.y(), available.bottom())
        rect = QRect(right - width + 1, bottom - height + 1, width, height)
        rect.moveLeft(max(rect.left(), available.left()))
        rect.moveTop(max(rect.top(), available.top()))
        self.setFixedSize(width, height)
        self.setGeometry(rect)

    def _target_size(self) -> tuple[int, int]:
        geo = self._screen().geometry()
        width_ratio, height_ratio = config.POPUP_ENLARGED_SIZE_RATIO if self._enlarged else config.POPUP_SIZE_RATIO
        return int(geo.width() * width_ratio), int(geo.height() * height_ratio)

    @staticmethod
    def _screen():
        return QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt-API)
        # Nur verstecken: Inhalt und Zustand der Seite bleiben erhalten.
        event.ignore()
        self.hide()
