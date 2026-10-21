"""FakeHttp: Attrappe für backend.integrations.http.JsonHttp - kein Test spricht mit echten Diensten."""
from __future__ import annotations

from typing import Any


class FakeHttp:
    """Antwortet je nach URL: Der erste Eintrag in responses, dessen Schlüssel in der URL
    vorkommt, gewinnt. Eine Exception als Antwort wird geworfen. Merkt sich alle Aufrufe."""

    def __init__(self, responses: dict[str, Any] | None = None):
        self.responses = dict(responses or {})
        self.calls: list[tuple[str, str, Any, Any]] = []   # (Methode, URL, params/body, headers)

    def get_text(self, url, params=None, headers=None):
        self.calls.append(("GET", url, params, headers))
        return self._answer(url)

    def get_json(self, url, params=None, headers=None):
        self.calls.append(("GET", url, params, headers))
        return self._answer(url)

    def post_json(self, url, body, headers=None):
        self.calls.append(("POST", url, body, headers))
        return self._answer(url)

    def _answer(self, url):
        for key, response in self.responses.items():
            if key in url:
                if isinstance(response, Exception):
                    raise response
                return response
        raise AssertionError(f"Keine vorbereitete Antwort für {url}")
