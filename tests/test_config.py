import unittest

from backend import config


class ConfigTest(unittest.TestCase):
    def test_frontend_files_exist(self):
        self.assertTrue(config.POPUP_PAGE.is_file())

    def test_tray_icon_exists(self):
        self.assertTrue(config.TRAY_ICON.is_file())

    def test_popup_ratios_are_screen_fractions(self):
        for ratio in (config.POPUP_HEIGHT_RATIO, config.POPUP_MAX_WIDTH_RATIO,
                      config.POPUP_ENLARGED_HEIGHT_RATIO, config.POPUP_ENLARGED_MAX_WIDTH_RATIO):
            self.assertGreater(ratio, 0)
            self.assertLessEqual(ratio, 1)

    def test_ui_scale_range_is_ordered(self):
        lowest, highest = config.UI_SCALE_RANGE
        self.assertGreater(lowest, 0)
        self.assertLess(lowest, highest)


if __name__ == "__main__":
    unittest.main()
