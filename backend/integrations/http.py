"""JsonHttp: gemeinsamer HTTP-Client der Integrationen (nur Standardbibliothek).

Jede Integration bekommt ein Http-Objekt übergeben. In den Tests steht dort eine
Attrappe (tests/integrations/fake_http.py), die vorbereitete Antworten liefert - so
läuft kein Test gegen echte Dienste.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import Any, Protocol

from backend import config


class IntegrationError(RuntimeError):
    """Ein externer Dienst ist nicht erreichbar oder antwortet mit einem Fehler."""


class Http(Protocol):
    def get_text(self, url: str, params: Mapping[str, Any] | None = None,
                 headers: Mapping[str, str] | None = None) -> str:
        ...

    def get_json(self, url: str, params: Mapping[str, Any] | None = None,
                 headers: Mapping[str, str] | None = None) -> Any:
        ...

    def post_json(self, url: str, body: Any, headers: Mapping[str, str] | None = None) -> Any:
        ...


class JsonHttp:
    def __init__(self, timeout_s: float = config.HTTP_TIMEOUT_S):
        self.timeout_s = timeout_s

    def get_text(self, url: str, params: Mapping[str, Any] | None = None,
                 headers: Mapping[str, str] | None = None) -> str:
        if params:
            url += "?" + urllib.parse.urlencode(params)
        return self._send(urllib.request.Request(url, headers=dict(headers or {})))

    def get_json(self, url: str, params: Mapping[str, Any] | None = None,
                 headers: Mapping[str, str] | None = None) -> Any:
        return _parse(self.get_text(url, params, {"Accept": "application/json", **(headers or {})}), url)

    def post_json(self, url: str, body: Any, headers: Mapping[str, str] | None = None) -> Any:
        request = urllib.request.Request(
            url, data=json.dumps(body).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json", **(headers or {})})
        return _parse(self._send(request), url)

    def _send(self, request: urllib.request.Request) -> str:
        host = urllib.parse.urlsplit(request.full_url).netloc
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:300]
            raise IntegrationError(f"{host} antwortet mit {error.code}: {detail}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise IntegrationError(f"{host} nicht erreichbar: {error}") from None


def _parse(text: str, url: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        raise IntegrationError(f"Keine gültige JSON-Antwort von {urllib.parse.urlsplit(url).netloc}") from None
