import ctypes
import sys
import unittest

from tests.qt_helpers import qt_app, wait_until

from backend.desktop.hotkey import (MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, WM_HOTKEY, GlobalHotkey,
                                    parse_hotkey)


class ParseHotkeyTest(unittest.TestCase):
    def test_letters_digits_and_function_keys(self):
        self.assertEqual(parse_hotkey("Ctrl+Alt+P"), (MOD_CONTROL | MOD_ALT, ord("P")))
        self.assertEqual(parse_hotkey("strg + shift + 1"), (MOD_CONTROL | MOD_SHIFT, ord("1")))
        self.assertEqual(parse_hotkey("Win+F1"), (MOD_WIN, 0x70))
        self.assertEqual(parse_hotkey("F12"), (0, 0x7B))

    def test_invalid(self):
        for text in ("Ctrl+", "Hyper+P", "Ctrl+Ä", "Ctrl+Enterr"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_hotkey(text)


class GlobalHotkeyTest(unittest.TestCase):
    def setUp(self):
        qt_app()

    def test_empty_hotkey_is_off(self):
        hotkey = GlobalHotkey("")
        self.assertFalse(hotkey.registered)
        hotkey.unregister()   # schadet nicht

    def test_invalid_hotkey_is_logged(self):
        with self.assertLogs("backend.desktop.hotkey", "WARNING"):
            self.assertFalse(GlobalHotkey("Hyper+P").registered)

    @unittest.skipUnless(sys.platform == "win32", "nur unter Windows")
    def test_wm_hotkey_emits_triggered(self):
        hotkey = GlobalHotkey("Ctrl+Alt+Shift+F24")   # praktisch nie belegt
        self.addCleanup(hotkey.unregister)
        self.assertTrue(hotkey.registered)
        triggered = []
        hotkey.triggered.connect(lambda: triggered.append(True))
        # So meldet Windows das Kürzel: WM_HOTKEY an die Nachrichtenschleife dieses Threads.
        thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        self.assertTrue(ctypes.windll.user32.PostThreadMessageW(thread_id, WM_HOTKEY, hotkey._id, 0))
        self.assertTrue(wait_until(lambda: triggered == [True]))

    @unittest.skipUnless(sys.platform == "win32", "nur unter Windows")
    def test_taken_hotkey_is_logged(self):
        first = GlobalHotkey("Ctrl+Alt+Shift+F23")
        self.addCleanup(first.unregister)
        self.assertTrue(first.registered)
        with self.assertLogs("backend.desktop.hotkey", "WARNING"):
            self.assertFalse(GlobalHotkey("Ctrl+Alt+Shift+F23").registered)
        first.unregister()
        self.assertFalse(first.registered)


if __name__ == "__main__":
    unittest.main()
