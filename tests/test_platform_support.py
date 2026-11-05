"""Plattformverhalten unabhängig vom Betriebssystem des Testrechners prüfen."""
import os
import types
import unittest
import wave
from pathlib import Path
from unittest import mock

from PyQt5.QtCore import QPoint, QRect

from backend import platform_paths, speech
from backend.desktop.macos import require_microphone_access
from backend.desktop.macos_hotkey import parse_mac_hotkey
from backend.desktop.popup_window import popup_geometry


class DataPathsTest(unittest.TestCase):
    def test_platform_defaults_and_override(self):
        cases = {
            "darwin": Path.home() / "Library/Application Support/PersonalDigitalAgent",
            "win32": Path("/roaming/PersonalDigitalAgent"),
            "linux": Path("/data/PersonalDigitalAgent"),
        }
        for platform, expected in cases.items():
            with self.subTest(platform=platform), \
                    mock.patch.object(platform_paths.sys, "platform", platform), \
                    mock.patch.dict(os.environ, {"APPDATA": "/roaming", "XDG_DATA_HOME": "/data"}, clear=True):
                self.assertEqual(platform_paths.app_data_dir(), expected)
                os.environ["PDA_APP_DATA_DIR"] = "/custom/pda"
                self.assertEqual(platform_paths.app_data_dir(), Path("/custom/pda"))


class PopupGeometryTest(unittest.TestCase):
    def test_mac_opens_below_menu_and_windows_above_taskbar(self):
        screen = QRect(0, 30, 1440, 830)
        self.assertEqual(popup_geometry(QPoint(700, 15), screen, 400, 500, True), QRect(500, 30, 400, 500))
        self.assertEqual(popup_geometry(QPoint(1400, 860), screen, 400, 500, False), QRect(1000, 360, 400, 500))

    def test_both_platforms_fit_all_edges_small_screens_and_negative_monitors(self):
        for screen in (QRect(0, 30, 1440, 830), QRect(-900, -800, 900, 780), QRect(100, 50, 250, 200)):
            for anchor in (screen.topLeft(), screen.topRight(), screen.bottomLeft(), screen.bottomRight()):
                for top in (True, False):
                    with self.subTest(screen=screen, anchor=anchor, top=top):
                        self.assertTrue(screen.contains(popup_geometry(anchor, screen, 400, 600, top)))


class MacHotkeyParsingTest(unittest.TestCase):
    def test_command_option_and_function_keys(self):
        self.assertEqual(parse_mac_hotkey("Cmd+Alt+P"), ((1 << 8) | (1 << 11), 35))
        self.assertEqual(parse_mac_hotkey("Ctrl+Shift+F12"), ((1 << 12) | (1 << 9), 111))

    def test_invalid_keys_are_rejected(self):
        for text in ("", "Cmd+", "Hyper+P", "Cmd+Ä", "Cmd+F24"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_mac_hotkey(text)


class MacMicrophonePermissionTest(unittest.TestCase):
    def setUp(self):
        self.capture = mock.Mock()
        module = types.SimpleNamespace(AVCaptureDevice=self.capture, AVMediaTypeAudio="audio",
                                       AVAuthorizationStatusAuthorized=3, AVAuthorizationStatusNotDetermined=0)
        patcher = mock.patch.dict("sys.modules", {"AVFoundation": module})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_existing_permission_does_not_prompt(self):
        self.capture.authorizationStatusForMediaType_.return_value = 3
        require_microphone_access()
        self.capture.requestAccessForMediaType_completionHandler_.assert_not_called()

    def test_first_request_acceptance_and_denial(self):
        self.capture.authorizationStatusForMediaType_.return_value = 0
        request = self.capture.requestAccessForMediaType_completionHandler_
        request.side_effect = lambda media, completed: completed(True)
        require_microphone_access()
        request.side_effect = lambda media, completed: completed(False)
        with self.assertRaisesRegex(RuntimeError, "Systemeinstellungen"):
            require_microphone_access()

    def test_denied_permission_has_actionable_error_without_new_prompt(self):
        self.capture.authorizationStatusForMediaType_.return_value = 2
        with self.assertRaisesRegex(RuntimeError, "Mikrofonzugriff"):
            require_microphone_access()
        self.capture.requestAccessForMediaType_completionHandler_.assert_not_called()


class MacSpeechTest(unittest.TestCase):
    def test_text_goes_to_stdin_and_temporary_audio_is_removed(self):
        paths = []

        def run(command, **kwargs):
            if command == ["/usr/bin/say", "-v", "?"]:
                return types.SimpleNamespace(stdout="Anna    de_DE    # Hallo\nSamantha en_US # Hello\n")
            path = Path(command[command.index("-o") + 1])
            paths.append(path)
            self.assertEqual(kwargs["input"], "--voice=anderer Text")
            self.assertEqual(command[-2:], ["-v", "Anna"])
            with wave.open(str(path), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(22050)
                audio.writeframes(b"\x01\x00" * 10)
            return types.SimpleNamespace()

        with mock.patch.object(speech.subprocess, "run", side_effect=run):
            samples, rate = speech.MacSynthesizer("de").synthesize("--voice=anderer Text")
        self.assertEqual((len(samples), rate), (10, 22050))
        self.assertFalse(paths[0].exists())

    def test_mac_fallback_is_available_without_piper(self):
        with mock.patch.object(speech.sys, "platform", "darwin"), \
                mock.patch.object(speech, "_installed", side_effect=lambda *m: "piper" not in m):
            output = speech.create_speech_output()
        self.assertEqual([type(s) for s in output._synthesizer._synthesizers], [speech.MacSynthesizer])
