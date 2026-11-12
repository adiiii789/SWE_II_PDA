"""3D-Begleiter neben dem Popup (backend/desktop/companion_window.py) und der schnelle Weg
Seite -> EventBus (WebBridge.notify), über den das Popup ihm Zustand und Gesten meldet."""
import json
import tempfile
import unittest
from pathlib import Path

from PyQt5.QtCore import QRect, Qt
from PyQt5.QtWidgets import QLabel, QWidget

from tests.qt_helpers import qt_app

from backend.bridge.function_registry import FunctionRegistry
from backend.bridge.web_bridge import WebBridge
from backend.desktop.companion_window import CompanionWindow, companion_geometry
from backend.events import COMPANION, EventBus

SCREEN = QRect(0, 0, 1920, 1040)


class GeometryTest(unittest.TestCase):
    def test_left_of_popup_bottom_aligned(self):
        popup = QRect(1340, 416, 576, 624)
        rect = companion_geometry(popup, SCREEN, 0.34, 0.7, 4)
        self.assertEqual(rect.height(), int(1040 * 0.34))
        self.assertEqual(rect.width(), int(rect.height() * 0.7))
        self.assertEqual(rect.right(), popup.left() - 4 - 1)
        self.assertEqual(rect.bottom(), popup.bottom())

    def test_never_taller_than_popup(self):
        rect = companion_geometry(QRect(1340, 900, 576, 140), SCREEN, 0.34, 0.7, 4)
        self.assertEqual(rect.height(), 140)

    def test_right_side_when_chosen_and_room(self):
        popup = QRect(1000, 416, 576, 624)
        rect = companion_geometry(popup, SCREEN, 0.34, 0.7, 4, side="right")
        self.assertEqual(rect.left(), popup.right() + 1 + 4)

    def test_right_side_without_room_falls_back_to_left(self):
        popup = QRect(1340, 416, 576, 624)
        rect = companion_geometry(popup, SCREEN, 0.34, 0.7, 4, side="right")
        self.assertLess(rect.right(), popup.left())

    def test_right_of_popup_when_no_room_on_the_left(self):
        popup = QRect(0, 416, 576, 624)
        rect = companion_geometry(popup, SCREEN, 0.34, 0.7, 4)
        self.assertEqual(rect.left(), popup.right() + 1 + 4)


class ImmediateExecutor:
    def submit(self, fn, *args):
        fn(*args)


class NotifyTest(unittest.TestCase):
    def setUp(self):
        qt_app()
        self.bus = EventBus()
        self.received = []
        self.bus.subscribe(lambda name, payload: self.received.append((name, payload)))

    def bridge(self, *names):
        return WebBridge(FunctionRegistry({}), ImmediateExecutor(), None, self.bus, frozenset(names))

    def test_allowed_name_is_published_at_once(self):
        self.bridge(COMPANION).notify(COMPANION, json.dumps({"kind": "state", "state": "thinking"}))
        self.assertEqual(self.received, [(COMPANION, {"kind": "state", "state": "thinking"})])

    def test_other_names_and_broken_json_are_ignored(self):
        bridge = self.bridge(COMPANION)
        bridge.notify("proactive_notice", "{}")
        bridge.notify(COMPANION, "{kaputt")
        self.assertEqual(self.received, [])

    def test_closed_bridge_publishes_nothing(self):
        bridge = self.bridge(COMPANION)
        bridge.close()
        bridge.notify(COMPANION, "{}")
        self.assertEqual(self.received, [])


class FakeView(QLabel):
    """Statt der Web-Ansicht: merkt sich, was ans JavaScript ginge."""

    def __init__(self):
        super().__init__("Begleiter")
        self.scripts = []
        view = self

        class Page:
            def runJavaScript(self, source):  # noqa: N802 (Qt-API)
                view.scripts.append(source)

        self._page = Page()

    def page(self):
        return self._page


class CompanionWindowTest(unittest.TestCase):
    def setUp(self):
        qt_app()
        self.bus = EventBus()
        self.popup = QWidget()
        self.popup.setGeometry(1200, 400, 500, 600)
        self.companion = CompanionWindow(FakeView(), self.popup, self.bus)
        self.addCleanup(self.companion.release)
        self.addCleanup(self.companion.hide)
        self.addCleanup(self.popup.hide)

    def test_takes_no_focus_and_is_translucent(self):
        self.assertTrue(self.companion.windowFlags() & Qt.WindowDoesNotAcceptFocus)
        self.assertTrue(self.companion.testAttribute(Qt.WA_TranslucentBackground))

    def test_follows_popup_visibility(self):
        self.popup.show()
        self.assertTrue(self.companion.isVisible())
        self.assertLess(self.companion.geometry().right(), self.popup.geometry().left())
        self.popup.hide()
        self.assertFalse(self.companion.isVisible())

    def test_can_be_switched_off_from_the_popup(self):
        self.popup.show()
        self.bus.publish(COMPANION, {"kind": "visible", "value": False})
        self.assertFalse(self.companion.isVisible())
        self.popup.hide()
        self.popup.show()
        self.assertFalse(self.companion.isVisible())   # bleibt aus, bis es wieder gewünscht ist
        self.bus.publish(COMPANION, {"kind": "visible", "value": True})
        self.assertTrue(self.companion.isVisible())

    def test_belongs_to_the_popup(self):
        # Windows hält zugehörige Fenster über dem Popup - sonst verschwände er beim erneuten Öffnen
        # hinter anderen Fenstern, weil er selbst nie aktiviert wird
        self.assertIs(self.companion.parent(), self.popup)
        self.assertTrue(self.companion.isWindow())

    def test_right_side_reserves_room_next_to_the_popup(self):
        self.assertEqual(self.companion.reserve(), (0, 0))
        self.bus.publish(COMPANION, {"kind": "side", "value": "right"})
        self.assertEqual(self.companion.side, "right")
        self.assertGreater(self.companion.reserve()[1], 0)
        self.bus.publish(COMPANION, {"kind": "visible", "value": False})
        self.assertEqual(self.companion.reserve(), (0, 0))   # aus: kein Platz nötig
        self.bus.publish(COMPANION, {"kind": "side", "value": "oben"})
        self.assertEqual(self.companion.side, "right")         # ungültige Seite wird ignoriert

    def test_pointer_is_forwarded_only_when_it_moved(self):
        self.popup.show()
        self.companion._send_pointer()
        self.companion._send_pointer()
        pointer = [script for script in self.companion.content.scripts if "Companion.pointer" in script]
        self.assertEqual(len(pointer), 1)

    def test_resumes_drawing_when_shown_again(self):
        self.popup.show()
        self.popup.hide()
        self.companion.content.scripts.clear()
        self.popup.show()
        self.assertTrue(any("Companion.resume" in script for script in self.companion.content.scripts))


class ModelQueryTest(unittest.TestCase):
    def test_existing_model_is_passed_as_file_url(self):
        from backend.desktop.application import companion_query
        with tempfile.TemporaryDirectory() as folder:
            model = Path(folder) / "mein modell.glb"
            model.write_bytes(b"glTF")
            query = companion_query(model)
        self.assertTrue(query.startswith("model=file:"))
        self.assertIn("mein%20modell.glb", query)

    def test_missing_or_other_files_are_ignored(self):
        from backend.desktop.application import companion_query
        with tempfile.TemporaryDirectory() as folder:
            other = Path(folder) / "bild.png"
            other.write_bytes(b"png")
            self.assertEqual(companion_query(other), "")
            self.assertEqual(companion_query(Path(folder) / "fehlt.glb"), "")


if __name__ == "__main__":
    unittest.main()
