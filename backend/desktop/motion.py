"""Bewegungseinstellungen des Betriebssystems für die Fensteranimationen."""
from __future__ import annotations

import ctypes
import os
import sys


def reduce_motion() -> bool:
    override = os.environ.get("PDA_REDUCE_MOTION")
    if override is not None:
        return override != "0"
    if sys.platform == "darwin":
        from AppKit import NSWorkspace
        return bool(NSWorkspace.sharedWorkspace().accessibilityDisplayShouldReduceMotion())
    if sys.platform == "win32":
        enabled = ctypes.c_int(1)
        if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0):
            return not bool(enabled.value)
    return False
