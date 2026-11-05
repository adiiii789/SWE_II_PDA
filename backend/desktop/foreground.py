"""Fenster in den Vordergrund holen, auch ohne vorherige Aktion des Nutzers (Windows).

Windows gibt einem Programm nur dann den Fokus, wenn der Nutzer gerade mit ihm gearbeitet hat
(Foreground-Lock). Öffnet sich das Popup von selbst (proaktive Meldung), würde SetForegroundWindow
scheitern - und ein Qt.Popup ohne Fokus schließt sich sofort wieder.

Ausweg: Den eigenen Thread kurz an den Eingabe-Thread des aktuellen Vordergrundfensters hängen
(AttachThreadInput). Dann gilt das Programm für Windows als beteiligt und darf den Fokus übernehmen.
"""
from __future__ import annotations

import ctypes
import logging
import sys

log = logging.getLogger(__name__)


def _user32():
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    return user32


def bring_to_front(window_id: int) -> bool:
    """Fenster (HWND, z. B. int(widget.winId())) zum Vordergrundfenster machen. False außerhalb
    von Windows oder wenn Windows es trotzdem ablehnt."""
    if sys.platform == "darwin":
        from backend.desktop.macos import activate_application
        return activate_application()
    if sys.platform != "win32":
        return False
    user32 = _user32()
    foreground = user32.GetForegroundWindow()
    if foreground == window_id:
        return True
    own_thread = ctypes.windll.kernel32.GetCurrentThreadId()
    other_thread = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
    attached = bool(other_thread) and other_thread != own_thread \
        and bool(user32.AttachThreadInput(own_thread, other_thread, True))
    try:
        user32.BringWindowToTop(window_id)
        brought = bool(user32.SetForegroundWindow(window_id))
    finally:
        if attached:
            user32.AttachThreadInput(own_thread, other_thread, False)
    if not brought:
        log.warning("Windows hat das Fenster nicht in den Vordergrund gelassen")
    return brought
