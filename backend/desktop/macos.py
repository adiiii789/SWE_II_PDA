"""macOS-Anbindung; Importe erfolgen erst beim tatsächlichen Aufruf auf dem Mac."""
from __future__ import annotations

import threading


def configure_application() -> None:
    from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

    NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)


def activate_application() -> bool:
    from AppKit import NSApplication

    NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    return True


class OutsideClickMonitor:
    """Mausklicks in anderen Anwendungen schließen das Menüleistenfenster."""

    def __init__(self, callback):
        from AppKit import NSEvent, NSEventMaskLeftMouseDown, NSEventMaskRightMouseDown, NSEventMaskOtherMouseDown

        self._event = NSEvent
        self._token = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            NSEventMaskLeftMouseDown | NSEventMaskRightMouseDown | NSEventMaskOtherMouseDown,
            lambda event: callback())

    def close(self):
        if self._token is not None:
            self._event.removeMonitor_(self._token)
            self._token = None


def require_microphone_access() -> None:
    """Aus dem Aufnahme-Worker aufrufen; nur ein Klick auf das Mikrofon fordert Zugriff an."""
    from AVFoundation import (AVCaptureDevice, AVMediaTypeAudio, AVAuthorizationStatusAuthorized,
                              AVAuthorizationStatusNotDetermined)

    status = AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio)
    if status == AVAuthorizationStatusAuthorized:
        return
    if status == AVAuthorizationStatusNotDetermined:
        finished = threading.Event()
        result = []

        def completed(granted):
            result.append(bool(granted))
            finished.set()

        AVCaptureDevice.requestAccessForMediaType_completionHandler_(AVMediaTypeAudio, completed)
        if not finished.wait(60):
            raise RuntimeError("Die Mikrofonfreigabe steht noch aus. Bitte bestätigen und erneut aufnehmen.")
        if result and result[0]:
            return
    raise RuntimeError("Mikrofonzugriff fehlt. Bitte unter Systemeinstellungen → Datenschutz & Sicherheit → "
                       "Mikrofon die Anwendung freigeben (beim Start aus PyCharm: PyCharm bzw. Python).")
