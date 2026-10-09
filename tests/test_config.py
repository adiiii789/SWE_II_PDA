import unittest

from backend import config


class ConfigTest(unittest.TestCase):
    def test_frontend_files_exist(self):
        self.assertTrue(config.POPUP_PAGE.is_file())

    def test_tray_icon_exists(self):
        self.assertTrue(config.TRAY_ICON.is_file())

    def test_popup_size_ratio_is_a_screen_fraction(self):
        for ratio in config.POPUP_SIZE_RATIO:
            self.assertGreater(ratio, 0)
            self.assertLessEqual(ratio, 1)


if __name__ == "__main__":
    unittest.main()
