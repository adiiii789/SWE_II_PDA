import unittest

from backend import config
from backend.desktop.layout import popup_size, ui_scale

# Freie Fläche (logische Pixel, Taskleiste abgezogen) typischer Bildschirme
SCREENS = {
    "480p 4:3 (640x480, 100 %)": (640, 440),
    "1024x768 4:3 (Beamer dupliziert)": (1024, 728),
    "1366x768 Laptop": (1366, 728),
    "1080p 16:9": (1920, 1040),
    "1080p 16:9 bei 125 %": (1536, 824),
    "2K 16:10 (2560x1600, 100 %)": (2560, 1560),
    "2K 16:10 (2560x1600, 150 %)": (1707, 1027),
    "1440p 21:9 Ultrawide": (3440, 1400),
    "4K 16:9 bei 150 %": (2560, 1400),
    "4K Ultrawide 32:9 (7680x2160, 100 %)": (7680, 2120),
    "4K 16:9 (100 %)": (3840, 2120),
    "1080p hochkant": (1080, 1880),
}


class UiScaleTest(unittest.TestCase):
    def test_reference_screen_is_scale_one(self):
        self.assertEqual(ui_scale(*config.UI_REFERENCE_SCREEN), 1.0)
        self.assertEqual(ui_scale(1920, 1040), 1.0)

    def test_grows_with_resolution(self):
        self.assertLess(ui_scale(1920, 1040), ui_scale(2560, 1400))
        self.assertLess(ui_scale(2560, 1400), ui_scale(3840, 2120))

    def test_ultrawide_scales_like_same_height_16_9(self):
        # mehr Breite macht die Oberfläche nicht größer - sie hängt an der Höhe
        self.assertEqual(ui_scale(3440, 1400), ui_scale(2560, 1400))
        self.assertEqual(ui_scale(7680, 2120), ui_scale(3840, 2120))

    def test_never_below_readable_or_above_maximum(self):
        lowest, highest = config.UI_SCALE_RANGE
        self.assertEqual(ui_scale(640, 440), lowest)
        self.assertEqual(ui_scale(20000, 10000), highest)

    def test_invalid_screen_falls_back_to_one(self):
        self.assertEqual(ui_scale(0, 0), 1.0)


class PopupSizeTest(unittest.TestCase):
    def test_fits_and_stays_usable_on_every_screen(self):
        for name, (width, height) in SCREENS.items():
            with self.subTest(name):
                scale = ui_scale(width, height)
                for enlarged in (False, True):
                    w, h = popup_size(width, height, scale, enlarged)
                    self.assertLessEqual(w, width)
                    self.assertLessEqual(h, height)
                    # in CSS-Pixeln (was die Seite sieht) mindestens das bedienbare Mindestmaß,
                    # außer der Bildschirm selbst ist kleiner
                    min_w, min_h = config.POPUP_MIN_CSS_SIZE
                    self.assertGreaterEqual(w / scale + 1, min(min_w, width / scale))
                    self.assertGreaterEqual(h / scale + 1, min(min_h, height / scale))

    def test_aspect_ratio_is_the_same_on_4_3_16_10_16_9_and_ultrawide(self):
        ratios = []
        for width, height in ((1440, 1040), (1920, 1040), (1707, 1027), (3440, 1400), (7680, 2120)):
            w, h = popup_size(width, height, ui_scale(width, height), enlarged=False)
            ratios.append(w / h)
        for ratio in ratios:
            self.assertAlmostEqual(ratio, config.POPUP_ASPECT, delta=0.01)

    def test_ultrawide_popup_is_not_a_wide_bar(self):
        w, h = popup_size(7680, 2120, ui_scale(7680, 2120), enlarged=True)
        self.assertLess(w / h, 1.5)

    def test_tiny_screen_gets_minimum_instead_of_a_fraction(self):
        scale = ui_scale(640, 440)
        w, h = popup_size(640, 440, scale, enlarged=False)
        self.assertGreater(h, 440 * config.POPUP_HEIGHT_RATIO)
        self.assertEqual((w, h), (int(config.POPUP_MIN_CSS_SIZE[0] * scale), int(config.POPUP_MIN_CSS_SIZE[1] * scale)))

    def test_enlarged_is_never_smaller(self):
        for name, (width, height) in SCREENS.items():
            with self.subTest(name):
                scale = ui_scale(width, height)
                normal = popup_size(width, height, scale, enlarged=False)
                enlarged = popup_size(width, height, scale, enlarged=True)
                self.assertGreaterEqual(enlarged[0], normal[0])
                self.assertGreaterEqual(enlarged[1], normal[1])

    def test_css_viewport_matches_design_on_every_16_9_screen(self):
        # gleicher Bildschirm-Typ, andere Auflösung: die Seite sieht (in CSS-Pixeln) gleich aus
        sizes = []
        for width, height in ((1920, 1040), (2560, 1400), (3840, 2120)):
            scale = ui_scale(width, height)
            w, h = popup_size(width, height, scale, enlarged=False)
            sizes.append((round(w / scale), round(h / scale)))
        for w, h in sizes:
            self.assertAlmostEqual(w, sizes[0][0], delta=3)
            self.assertAlmostEqual(h, sizes[0][1], delta=3)


if __name__ == "__main__":
    unittest.main()
