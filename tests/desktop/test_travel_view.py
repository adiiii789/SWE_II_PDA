"""Ende-zu-Ende: die Reise-Ansicht (travel.html.j2) im echten Chromium - Reiter, Karte groß mit
Zoom, zugeklappter Vergleich. Ohne Netz: Kacheln kommen von einer Attrappe."""
import datetime
import unittest

from PyQt5.QtCore import QSize
from PyQt5.QtWebEngineWidgets import QWebEngineView

from backend import config
from backend.assistant.skills.travel import planner, view
from backend.assistant.skills.travel.planner import Option, TravelSettings, TripPlan
from backend.rendering import ViewRenderer
from tests.assistant.travel.fakes import HOME, NOW, UNI, transit_journey
from tests.qt_helpers import qt_app, run_js, wait_until

PNG = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9aw"
       "AAAABJRU5ErkJggg==")   # 1 × 1 Pixel
VIEW_BOX = "document.querySelector('#panel-0 svg.map').getAttribute('viewBox')"
ZOOMED = "document.getElementById('zoom-0').checked"


class Tiles:
    def data_uri(self, zoom, x, y):
        return PNG


class TravelViewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt_app()
        later = NOW + datetime.timedelta(days=365)
        transit = planner.transit_option(transit_journey(later), TravelSettings())
        car = Option("car", 1500, 3.0, geometry=((8.46, 49.48), (8.55, 49.45), (8.67, 49.41)),
                     depart_at=later, arrive_at=later)
        plan = TripPlan(HOME, UNI, later, (transit, car), TravelSettings())
        html = ViewRenderer(config.TEMPLATE_DIR, config.FRONTEND_DIR).render(view.trip_view(plan, tiles=Tiles()))
        cls.view = QWebEngineView()
        cls.view.resize(QSize(480, 640))
        cls.view.show()
        loaded = []
        cls.view.loadFinished.connect(loaded.append)
        cls.view.setHtml(html)
        if not wait_until(lambda: loaded, 40):
            raise TimeoutError("Reise-Ansicht nicht geladen")
        cls.page = cls.view.page()

    @classmethod
    def tearDownClass(cls):
        cls.view.close()
        cls.view.deleteLater()
        qt_app().processEvents()

    def js(self, script):
        return run_js(self.page, script)

    def tearDown(self):
        self.js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape'}))")

    def test_map_is_on_top_of_the_panel(self):
        self.assertEqual(self.js("document.querySelector('#panel-0').firstElementChild.className"), "zoom")
        self.assertTrue(self.js("document.querySelector('#panel-0 .map').getBoundingClientRect().top"
                                " < document.querySelector('#panel-0 .conn').getBoundingClientRect().top"))

    def test_click_enlarges_and_buttons_zoom(self):
        full = self.js(VIEW_BOX)
        self.js("document.querySelector('#panel-0 .map-open').click()")
        self.assertTrue(wait_until(lambda: self.js(ZOOMED)))
        self.assertEqual(self.js("getComputedStyle(document.querySelector('#panel-0 .map-box')).position"), "fixed")
        self.assertTrue(self.js("(r => r.left === 0 && r.top === 0 && r.width >= document.body.clientWidth"
                                " && r.height >= innerHeight - 1)"
                                "(document.querySelector('#panel-0 .map-box').getBoundingClientRect())"))
        self.assertTrue(self.js("document.body.classList.contains('map-zoomed')"))   # Seite scrollt nicht mit
        self.js("document.querySelector('#panel-0 [data-step=\"1.6\"]').click()")
        zoomed = self.js(VIEW_BOX)
        self.assertNotEqual(zoomed, full)
        self.assertLess(float(zoomed.split()[2]), float(full.split()[2]))   # kleinerer Ausschnitt
        self.js("document.querySelector('#panel-0 .map-open').click()")      # Klick auf die große Karte …
        self.assertTrue(self.js(ZOOMED))                                     # … schließt sie nicht
        self.js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape'}))")
        self.assertFalse(self.js(ZOOMED))
        self.assertEqual(self.js(VIEW_BOX), full)                            # wieder ganz
        self.assertFalse(self.js("document.body.classList.contains('map-zoomed')"))

    def test_wheel_zooms_only_when_enlarged(self):
        full = self.js(VIEW_BOX)
        wheel = ("document.querySelector('#panel-0 svg.map').dispatchEvent(new WheelEvent('wheel', "
                 "{deltaY: -100, clientX: 100, clientY: 100, bubbles: true, cancelable: true}))")
        self.js(wheel)
        self.assertEqual(self.js(VIEW_BOX), full)
        self.js("document.querySelector('#panel-0 .map-open').click()")
        self.js(wheel)
        self.assertNotEqual(self.js(VIEW_BOX), full)

    def test_markers_keep_their_size(self):
        radius = "document.querySelector('#panel-0 circle.start').getBoundingClientRect().width"
        small = self.js(radius)
        self.js("document.querySelector('#panel-0 .map-open').click()")
        self.js("document.querySelector('#panel-0 [data-step=\"1.6\"]').click()")
        self.assertTrue(wait_until(lambda: abs(self.js(radius) - small) < 2))   # 12 px groß, auch gezoomt

    def test_comparison_is_collapsed_and_tabs_switch(self):
        self.assertFalse(self.js("document.querySelector('details.compare').open"))
        self.js("document.querySelector('label[for=\"mode-1\"]').click()")
        self.assertEqual(self.js("getComputedStyle(document.getElementById('panel-1')).display"), "block")
        self.assertEqual(self.js("getComputedStyle(document.getElementById('panel-0')).display"), "none")
        self.js("document.querySelector('label[for=\"mode-0\"]').click()")


if __name__ == "__main__":
    unittest.main()
