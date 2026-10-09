import unittest
from unittest import mock

import main


class MainTest(unittest.TestCase):
    @mock.patch.object(main, "configure_qt")
    @mock.patch.object(main, "Application")
    @mock.patch.object(main, "QApplication")
    def test_main_builds_application_and_returns_exit_code(self, qapp_cls, application_cls, configure_qt):
        qapp_cls.return_value.exec_.return_value = 7

        self.assertEqual(main.main(), 7)

        configure_qt.assert_called_once()
        application_cls.assert_called_once_with(qapp_cls.return_value)

    @mock.patch.object(main, "ctypes")
    @mock.patch.object(main, "QApplication")
    def test_configure_qt_sets_app_user_model_id_on_windows(self, qapp_cls, ctypes_mod):
        with mock.patch.object(main.sys, "platform", "win32"):
            main.configure_qt()
        self.assertEqual(qapp_cls.setAttribute.call_count, 2)
        ctypes_mod.windll.shell32.SetCurrentProcessExplicitAppUserModelID.assert_called_once_with(
            main.config.APP_USER_MODEL_ID)

    @mock.patch.object(main, "ctypes")
    @mock.patch.object(main, "QApplication")
    def test_configure_qt_skips_app_user_model_id_elsewhere(self, _qapp_cls, ctypes_mod):
        with mock.patch.object(main.sys, "platform", "linux"):
            main.configure_qt()
        ctypes_mod.windll.shell32.SetCurrentProcessExplicitAppUserModelID.assert_not_called()


if __name__ == "__main__":
    unittest.main()
