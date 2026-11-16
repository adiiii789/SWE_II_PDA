"""JsonHttp gegen einen lokalen Testserver (kein Internet nötig)."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from backend.integrations.http import IntegrationError, JsonHttp


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/json"):
            self._send(200, json.dumps({"path": self.path, "key": self.headers.get("X-Key")}))
        elif self.path.startswith("/text"):
            self._send(200, "<ok/>")
        elif self.path.startswith("/broken"):
            self._send(200, "{kaputt")
        else:
            self._send(404, "nicht da")

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self._send(200, json.dumps({"echo": body, "type": self.headers.get("Content-Type")}))

    def _send(self, status, text):
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class JsonHttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.http = JsonHttp(timeout_s=5)

    def test_get_json_with_params_and_headers(self):
        data = self.http.get_json(self.base + "/json", {"a": "ä b"}, {"X-Key": "geheim"})
        self.assertEqual(data, {"path": "/json?a=%C3%A4+b", "key": "geheim"})

    def test_get_text(self):
        self.assertEqual(self.http.get_text(self.base + "/text"), "<ok/>")

    def test_post_json(self):
        self.assertEqual(self.http.post_json(self.base + "/post", {"x": [1, 2]}),
                         {"echo": {"x": [1, 2]}, "type": "application/json"})

    def test_http_error_becomes_integration_error(self):
        with self.assertRaisesRegex(IntegrationError, "404: nicht da"):
            self.http.get_text(self.base + "/fehlt")

    def test_invalid_json(self):
        with self.assertRaisesRegex(IntegrationError, "Keine gültige JSON-Antwort"):
            self.http.get_json(self.base + "/broken")

    def test_unreachable_host(self):
        with self.assertRaisesRegex(IntegrationError, "nicht erreichbar"):
            JsonHttp(timeout_s=2).get_text("http://127.0.0.1:1/")


if __name__ == "__main__":
    unittest.main()
