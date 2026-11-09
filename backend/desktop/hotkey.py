"""Globales Tastenkürzel für Windows und macOS, auch bei geschlossenem Popup.

Windows meldet das Kürzel (RegisterHotKey) als WM_HOTKEY an die Nachrichtenschleife des
Haupt-Threads; ein nativer Event-Filter von Qt fängt sie ab und sendet das Signal `triggered`.
macOS registriert sein Kürzel in macos_hotkey.py mit Carbon.
Heute das Test-Makro für proaktive Meldungen (config.PROACTIVE_HOTKEY).
"""
from __future__ import annotations

import ctypes
import logging
import sys
from collections.abc import Callable

from PyQt5.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, pyqtSignal

log = logging.getLogger(__name__)

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
_MODIFIERS = {"ctrl": MOD_CONTROL, "strg": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT, "win": MOD_WIN}
_KEYS = {**{f"f{n}": 0x6F + n for n in range(1, 25)},   # F1 = 0x70
         "space": 0x20, "pause": 0x13, "insert": 0x2D, "home": 0x24, "end": 0x23}


def parse_hotkey(text: str) -> tuple[int, int]:
    """"Ctrl+Alt+P" → (Modifier-Bits, virtueller Tastencode). Wirft ValueError."""
    *modifiers, key = [part.strip().lower() for part in text.split("+")]
    if not key:
        raise ValueError(f"Tastenkürzel ohne Taste: {text!r}")
    bits = 0
    for modifier in modifiers:
        if modifier not in _MODIFIERS:
            raise ValueError(f"Unbekannte Zusatztaste {modifier!r} in {text!r} (erlaubt: {sorted(_MODIFIERS)})")
        bits |= _MODIFIERS[modifier]
    if len(key) == 1 and key.isalnum() and key.isascii():
        return bits, ord(key.upper())
    if key in _KEYS:
        return bits, _KEYS[key]
    raise ValueError(f"Unbekannte Taste {key!r} in {text!r}")


class _HotkeyFilter(QAbstractNativeEventFilter):
    """Eigene Klasse: PyQt5 erlaubt keine Mehrfachvererbung von QObject und diesem Filter."""

    def __init__(self, hotkey_id: int, callback: Callable[[], None]):
        super().__init__()
        self._id = hotkey_id
        self._callback = callback

    def nativeEventFilter(self, event_type, message):  # noqa: N802 (Qt-API)
        if event_type == b"windows_generic_MSG" and message:
            from ctypes import wintypes
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == self._id:
                self._callback()
                return True, 0
        return False, 0


class GlobalHotkey(QObject):
    """Meldet sich mit `triggered`, wenn das Kürzel gedrückt wird. `registered` sagt, ob es geklappt hat
    (nicht unterstützt, ungültig oder bereits belegt → False)."""

    triggered = pyqtSignal()
    _next_id = 0xB000   # Windows erlaubt für Anwendungen 0x0000-0xBFFF

    def __init__(self, text: str, parent: QObject | None = None):
        super().__init__(parent)
        self.text = text
        GlobalHotkey._next_id += 1
        self._id = GlobalHotkey._next_id
        self._filter: _HotkeyFilter | None = None
        self._mac_hotkey = None
        self.registered = self._register()

    def _register(self) -> bool:
        if not self.text:
            return False
        if sys.platform == "darwin":
            from backend.desktop.macos_hotkey import MacHotkey
            try:
                self._mac_hotkey = MacHotkey(self.text, self._id, self.triggered.emit)
                return True
            except (ValueError, OSError, RuntimeError) as error:
                log.warning("Tastenkürzel nicht verfügbar: %s", error)
                return False
        if sys.platform != "win32":
            return False
        try:
            modifiers, key = parse_hotkey(self.text)
        except ValueError as error:
            log.warning("Tastenkürzel ungültig: %s", error)
            return False
        if not ctypes.windll.user32.RegisterHotKey(None, self._id, modifiers | MOD_NOREPEAT, key):
            log.warning("Tastenkürzel %s ist schon belegt", self.text)
            return False
        self._filter = _HotkeyFilter(self._id, self.triggered.emit)
        QCoreApplication.instance().installNativeEventFilter(self._filter)
        return True

    def unregister(self) -> None:
        if not self.registered:
            return
        self.registered = False
        if self._mac_hotkey is not None:
            self._mac_hotkey.close()
            self._mac_hotkey = None
            return
        ctypes.windll.user32.UnregisterHotKey(None, self._id)
        app = QCoreApplication.instance()
        if app is not None and self._filter is not None:
            app.removeNativeEventFilter(self._filter)
        self._filter = None
