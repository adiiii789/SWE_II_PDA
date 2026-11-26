"""Größen relativ zum Bildschirm - für jede Auflösung und jedes Seitenverhältnis.

Alles rechnet in logischen Pixeln (die Skalierung von Windows/macOS ist schon eingerechnet) und nur mit
der freien Fläche eines Bildschirms (ohne Taskleiste). Zwei Größen kommen heraus:

- Maßstab der Oberfläche (ui_scale): Faktor, mit dem die Web-Seite gezeichnet wird (Zoom der Web-Ansicht).
  Die Pixelwerte in den CSS-Dateien sind damit Entwurfsmaße für einen 1080p-Bildschirm und wachsen bzw.
  schrumpfen mit dem Bildschirm mit - Text, Knöpfe, Abstände, Ansicht im iframe, alles im gleichen
  Verhältnis. Er hängt an der Höhe (ein Ultrawide ist nicht "größer" als ein 16:9 gleicher Höhe), bei
  schmalen Bildschirmen (4:3, hochkant) an der Breite. Nach unten begrenzt, damit Text lesbar und Knöpfe
  treffbar bleiben, nach oben, damit nichts absurd groß wird.
- Fenstergröße (popup_size): Anteil der Bildschirmhöhe mit festem Seitenverhältnis statt Anteil von Breite
  und Höhe - sonst würde das Popup auf 21:9/32:9 zum Querbalken und auf 4:3 zum schmalen Streifen. Nie
  kleiner als die Seite zum Bedienen braucht (Mindestmaß in CSS-Pixeln mal Maßstab), nie größer als der
  Bildschirm.
"""
from __future__ import annotations

from backend import config


def ui_scale(available_width: int, available_height: int) -> float:
    """Zoom der Oberfläche für eine freie Bildschirmfläche (logische Pixel)."""
    reference_width, reference_height = config.UI_REFERENCE_SCREEN
    lowest, highest = config.UI_SCALE_RANGE
    if available_width <= 0 or available_height <= 0:
        return 1.0
    raw = min(available_width / reference_width, available_height / reference_height)
    return round(max(lowest, min(raw, highest)), 3)


def _clamped_size(available_width: int, available_height: int, height_ratio: float, aspect: float,
                  max_width_ratio: float, minimum: tuple[float, float]) -> tuple[int, int]:
    height = available_height * height_ratio
    width = min(height * aspect, available_width * max_width_ratio)
    width, height = max(width, minimum[0]), max(height, minimum[1])
    return int(min(width, available_width)), int(min(height, available_height))


def popup_size(available_width: int, available_height: int, scale: float, enlarged: bool) -> tuple[int, int]:
    """Breite und Höhe des Popups (logische Pixel) auf einem Bildschirm mit dieser freien Fläche."""
    min_css_width, min_css_height = config.POPUP_MIN_CSS_SIZE
    minimum = (min_css_width * scale, min_css_height * scale)
    normal = _clamped_size(available_width, available_height, config.POPUP_HEIGHT_RATIO, config.POPUP_ASPECT,
                           config.POPUP_MAX_WIDTH_RATIO, minimum)
    if not enlarged:
        return normal
    # vergrößert nie kleiner als normal - auf kleinen Bildschirmen ist das Popup schon so groß wie möglich
    return _clamped_size(available_width, available_height, config.POPUP_ENLARGED_HEIGHT_RATIO,
                         config.POPUP_ENLARGED_ASPECT, config.POPUP_ENLARGED_MAX_WIDTH_RATIO, normal)
