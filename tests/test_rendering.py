import tempfile
import unittest
from pathlib import Path

from jinja2 import UndefinedError

from backend import config
from backend.rendering import TEMPLATE_SUFFIX, UnknownTemplateError, ViewRenderer
from backend.views import START_VIEW, HtmlView, TemplateView


class DefaultTemplateTest(unittest.TestCase):
    def setUp(self):
        self.renderer = ViewRenderer(config.TEMPLATE_DIR, config.FRONTEND_DIR)

    def _render(self, **data):
        return self.renderer.render(TemplateView("default", data))

    def test_start_view_contains_shared_theme(self):
        html = self.renderer.render(START_VIEW)
        self.assertIn("<h2>Personal Digital Agent</h2>", html)
        self.assertIn("--background", html)   # theme.css ist eingebettet

    def test_title_only_has_no_text_and_no_table(self):
        html = self._render(title="Only title")
        self.assertIn("<h2>Only title</h2>", html)
        self.assertNotIn("<p>", html)
        self.assertNotIn("<table>", html)

    def test_text_is_shown(self):
        self.assertIn("<p>Hallo</p>", self._render(title="T", text="Hallo"))

    def test_table_renders_columns_and_rows(self):
        html = self._render(title="T", columns=["A", "B"], rows=[["1", "2"]])
        self.assertIn("<th>A</th><th>B</th>", html)
        self.assertIn("<td>1</td><td>2</td>", html)

    def test_table_without_header(self):
        html = self._render(title="T", rows=[["1"]])
        self.assertIn("<td>1</td>", html)
        self.assertNotIn("<thead>", html)

    def test_missing_title_raises(self):
        with self.assertRaises(UndefinedError):
            self._render(text="no title")

    def test_data_is_escaped(self):
        html = self._render(title="<script>alert(1)</script>", text="a & b")
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("a &amp; b", html)


class TemplateSelectionTest(unittest.TestCase):
    def setUp(self):
        self.renderer = ViewRenderer(config.TEMPLATE_DIR, config.FRONTEND_DIR)

    def test_unknown_template_raises(self):
        with self.assertRaises(UnknownTemplateError):
            self.renderer.render(TemplateView("does_not_exist"))

    def test_invalid_template_names_are_rejected(self):
        for name in ("../popup", "Default", "default.html.j2", ""):
            with self.subTest(name=name), self.assertRaises(UnknownTemplateError):
                self.renderer.render(TemplateView(name))

    def test_selects_template_by_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "one" + TEMPLATE_SUFFIX).write_text("one {{ x }}", encoding="utf-8")
            Path(tmp, "two" + TEMPLATE_SUFFIX).write_text("two {{ x }}", encoding="utf-8")
            renderer = ViewRenderer(Path(tmp), Path(tmp))
            self.assertEqual(renderer.render(TemplateView("one", {"x": 1})), "one 1")
            self.assertEqual(renderer.render(TemplateView("two", {"x": 2})), "two 2")

    def test_autoescape_is_active_for_html_j2(self):
        # select_autoescape entscheidet nach Dateiendung - .html.j2 muss eingeschlossen sein.
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "greeting" + TEMPLATE_SUFFIX).write_text("Hallo {{ name }}", encoding="utf-8")
            renderer = ViewRenderer(Path(tmp), Path(tmp))
            self.assertEqual(renderer.render(TemplateView("greeting", {"name": "<b>"})), "Hallo &lt;b&gt;")


class HtmlViewTest(unittest.TestCase):
    def test_custom_html_is_passed_through_unchanged(self):
        renderer = ViewRenderer(config.TEMPLATE_DIR, config.FRONTEND_DIR)
        self.assertEqual(renderer.render(HtmlView("<h1>Eigenes HTML</h1>")), "<h1>Eigenes HTML</h1>")

    def test_non_view_raises(self):
        renderer = ViewRenderer(config.TEMPLATE_DIR, config.FRONTEND_DIR)
        with self.assertRaises(TypeError):
            renderer.render({"html": "dict statt View"})


if __name__ == "__main__":
    unittest.main()
