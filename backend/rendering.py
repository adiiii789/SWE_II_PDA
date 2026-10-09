"""Macht aus einer Ansicht-Anfrage (View) HTML für das iframe im Frontend.

TemplateView: frontend/templates/<template>.html.j2 wird mit Jinja2 gefüllt.
              Autoescaping ist an - Text aus den Daten wird nie als HTML ausgeführt.
HtmlView:     das HTML wird unverändert übernommen. Geschützt ist es nur durch die
              Sandbox des iframes (kein Zugriff auf Popup-Seite und Python-Funktionen).
"""
from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound, select_autoescape

from backend.views import HtmlView, TemplateView, View

TEMPLATE_SUFFIX = ".html.j2"
_TEMPLATE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


class UnknownTemplateError(LookupError):
    """Zu diesem Namen gibt es kein Template."""


class ViewRenderer:
    def __init__(self, template_dir: Path, shared_dir: Path):
        """template_dir: die Templates; shared_dir: Dateien zum Einbinden (z. B. theme.css)."""
        self._env = Environment(
            loader=FileSystemLoader([str(template_dir), str(shared_dir)]),
            autoescape=select_autoescape(["html", "html.j2"]),
            undefined=StrictUndefined,   # fehlende Pflichtdaten fallen sofort auf
        )

    def render(self, view: View) -> str:
        if isinstance(view, HtmlView):
            return view.html
        if isinstance(view, TemplateView):
            return self._render_template(view)
        raise TypeError(f"Keine Ansicht: {view!r}")

    def _render_template(self, view: TemplateView) -> str:
        if not _TEMPLATE_NAME.match(view.template):
            raise UnknownTemplateError(f"Ungültiger Template-Name: {view.template!r}")
        try:
            template = self._env.get_template(view.template + TEMPLATE_SUFFIX)
        except TemplateNotFound:
            raise UnknownTemplateError(f"Unbekanntes Template: {view.template!r}") from None
        return template.render(view.data)
