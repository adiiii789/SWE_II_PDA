"""Ansicht-Anfragen: was im iframe angezeigt werden soll.

Eine Anfrage ist entweder
  TemplateView - ein Template aus frontend/templates/<template>.html.j2 plus Daten, oder
  HtmlView     - eigenes HTML, das unverändert angezeigt wird.

Als JSON (z. B. vom Frontend über api.render_view):
  {"template": "default", "data": {"title": "...", "text": "..."}}
  {"html": "<h1>...</h1>"}
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Union


@dataclass(frozen=True)
class TemplateView:
    template: str                                    # Name ohne Endung, z. B. "default"
    data: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HtmlView:
    html: str


View = Union[TemplateView, HtmlView]

START_VIEW = TemplateView("default", {
    "title": "Personal Digital Agent",
    "text": "Frag den Assistenten unten nach Daten – sie werden hier angezeigt.",
})


class InvalidViewRequestError(ValueError):
    """Die Anfrage ist weder ein gültiges Template noch gültiges HTML."""


def view_from_dict(request: Mapping[str, Any]) -> View:
    """JSON-Anfrage in eine View umwandeln - genau eins von "template" oder "html"."""
    if not isinstance(request, Mapping):
        raise InvalidViewRequestError("Anfrage muss ein Objekt sein")
    has_template, has_html = "template" in request, "html" in request
    if has_template == has_html:
        raise InvalidViewRequestError('Anfrage braucht genau eins von "template" oder "html"')

    if has_html:
        if not isinstance(request["html"], str):
            raise InvalidViewRequestError('"html" muss ein Text sein')
        return HtmlView(request["html"])

    template, data = request["template"], request.get("data", {})
    if not isinstance(template, str):
        raise InvalidViewRequestError('"template" muss ein Text sein')
    if not isinstance(data, Mapping):
        raise InvalidViewRequestError('"data" muss ein Objekt sein')
    return TemplateView(template, data)
