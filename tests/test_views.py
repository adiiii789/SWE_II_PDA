import unittest

from backend.views import HtmlView, InvalidViewRequestError, TemplateView, view_from_dict


class ViewFromDictTest(unittest.TestCase):
    def test_template_with_data(self):
        view = view_from_dict({"template": "default", "data": {"title": "T"}})
        self.assertEqual(view, TemplateView("default", {"title": "T"}))

    def test_template_without_data(self):
        self.assertEqual(view_from_dict({"template": "default"}), TemplateView("default", {}))

    def test_html(self):
        self.assertEqual(view_from_dict({"html": "<p>x</p>"}), HtmlView("<p>x</p>"))

    def test_invalid_requests_are_rejected(self):
        invalid = [
            {},                                          # weder noch
            {"template": "default", "html": "<p>"},      # beides
            {"html": 5},
            {"template": 5},
            {"template": "default", "data": [1, 2]},
            "kein Objekt",
        ]
        for request in invalid:
            with self.subTest(request=request), self.assertRaises(InvalidViewRequestError):
                view_from_dict(request)


if __name__ == "__main__":
    unittest.main()
