"""Registrierte macOS-Tastenkürzel ohne Überwachung der Tastatureingaben."""
from __future__ import annotations

import ctypes
import logging
from collections.abc import Callable

log = logging.getLogger(__name__)


class EventTypeSpec(ctypes.Structure):
    _fields_ = [("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32)]


class EventHotKeyID(ctypes.Structure):
    _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]


_HANDLER = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
_SIGNATURE = int.from_bytes(b"PDAH", "big")
# ANSI-Hardwarecodes, unabhängig vom Buchstabenwert der Windows-Tastencodes.
_KEYS = {"a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9,
         "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19,
         "3": 20, "4": 21, "6": 22, "5": 23, "9": 25, "7": 26, "8": 28, "0": 29,
         "o": 31, "u": 32, "i": 34, "p": 35, "l": 37, "j": 38, "k": 40, "n": 45, "m": 46,
         "space": 49, "home": 115, "end": 119, "insert": 114,
         **dict(zip((f"f{i}" for i in range(1, 21)),
                    (122, 120, 99, 118, 96, 97, 98, 100, 101, 109, 103, 111, 105, 107, 113, 106, 64, 79, 80, 90)))}
_MODIFIERS = {"cmd": 1 << 8, "command": 1 << 8, "win": 1 << 8, "shift": 1 << 9,
              "alt": 1 << 11, "option": 1 << 11, "ctrl": 1 << 12, "strg": 1 << 12}


def parse_mac_hotkey(text: str) -> tuple[int, int]:
    *modifiers, key = [part.strip().lower() for part in text.split("+")]
    if key not in _KEYS or any(modifier not in _MODIFIERS for modifier in modifiers):
        raise ValueError(f"Ungültiges macOS-Tastenkürzel: {text!r}")
    bits = 0
    for modifier in modifiers:
        bits |= _MODIFIERS[modifier]
    return bits, _KEYS[key]


def _carbon():
    lib = ctypes.CDLL("/System/Library/Frameworks/Carbon.framework/Carbon")
    lib.GetApplicationEventTarget.restype = ctypes.c_void_p
    lib.InstallEventHandler.argtypes = [ctypes.c_void_p, _HANDLER, ctypes.c_uint32,
                                       ctypes.POINTER(EventTypeSpec), ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    lib.RegisterEventHotKey.argtypes = [ctypes.c_uint32, ctypes.c_uint32, EventHotKeyID,
                                       ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
    lib.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]
    lib.RemoveEventHandler.argtypes = [ctypes.c_void_p]
    lib.GetEventParameter.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                                     ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p]
    return lib


class MacHotkey:
    def __init__(self, text: str, identifier: int, callback: Callable[[], None]):
        modifiers, key = parse_mac_hotkey(text)
        self._lib = _carbon()
        self._hotkey = ctypes.c_void_p()
        self._handler = ctypes.c_void_p()
        self._id = EventHotKeyID(_SIGNATURE, identifier)

        def handle(_next, event, _data):
            received = EventHotKeyID()
            status = self._lib.GetEventParameter(event, int.from_bytes(b"----", "big"),
                                                 int.from_bytes(b"hkid", "big"), None,
                                                 ctypes.sizeof(received), None, ctypes.byref(received))
            if status == 0 and (received.signature, received.id) == (self._id.signature, self._id.id):
                try:
                    callback()
                except Exception:
                    log.exception("Tastenkürzel konnte nicht ausgeführt werden")
                return 0
            return -9874  # eventNotHandledErr: andere registrierte Kürzel weiterreichen

        self._callback = _HANDLER(handle)  # Carbon hält keinen Python-Verweis.
        event_type = EventTypeSpec(int.from_bytes(b"keyb", "big"), 6)  # kEventHotKeyPressed
        target = self._lib.GetApplicationEventTarget()
        if self._lib.InstallEventHandler(target, self._callback, 1, ctypes.byref(event_type), None,
                                         ctypes.byref(self._handler)) != 0:
            raise RuntimeError("macOS-Tastenkürzelhandler konnte nicht eingerichtet werden")
        if self._lib.RegisterEventHotKey(key, modifiers, self._id, target, 0, ctypes.byref(self._hotkey)) != 0:
            self.close()
            raise RuntimeError(f"Tastenkürzel {text} ist bereits belegt oder nicht verfügbar")

    def close(self) -> None:
        if self._hotkey.value:
            self._lib.UnregisterEventHotKey(self._hotkey)
            self._hotkey = ctypes.c_void_p()
        if self._handler.value:
            self._lib.RemoveEventHandler(self._handler)
            self._handler = ctypes.c_void_p()
