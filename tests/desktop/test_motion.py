import ctypes
import os
import types
import unittest
from unittest import mock

from backend.desktop import motion


class MotionTest(unittest.TestCase):
    def test_explicit_motion_preference(self):
        with mock.patch.dict(os.environ, {"PDA_REDUCE_MOTION": "1"}):
            self.assertTrue(motion.reduce_motion())
        with mock.patch.dict(os.environ, {"PDA_REDUCE_MOTION": "0"}):
            self.assertFalse(motion.reduce_motion())

    def test_windows_animation_setting_is_respected(self):
        def query(action, size, output, flags):
            ctypes.cast(output, ctypes.POINTER(ctypes.c_int))[0] = 0
            return True
        library = types.SimpleNamespace(user32=types.SimpleNamespace(SystemParametersInfoW=query))
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(motion.sys, "platform", "win32"), \
                mock.patch.object(motion.ctypes, "windll", library, create=True):
            self.assertTrue(motion.reduce_motion())

    def test_unsupported_platform_uses_normal_motion(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(motion.sys, "platform", "linux"):
            self.assertFalse(motion.reduce_motion())
