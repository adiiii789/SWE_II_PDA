"""Reiseplan als Text (Chat und Sprachmodell) und als Ansicht (frontend/templates/travel.html.j2).

Die Karte ist eine SVG-Skizze der Route ohne Kartenkacheln: Das iframe ist abgeschottet
und lädt nichts nach.
"""
from __future__ import annotations

import datetime
import math

from backend.assistant.skills.travel.planner import Option, TripPlan
from backend.integrations.openrouteservice import ATTRIBUTION
from backend.views import TemplateView

MAP_WIDTH, MAP_HEIGHT, MAP_PADDING = 320, 180, 12
MAX_MAP_POINTS = 300
MAX_STEPS = 15


def summary(plan: TripPlan, title: str = "") -> str:
    """Kurzfassung für den Chat und als Werkzeugergebnis fürs Sprachmodell."""
    target = f" zu „{title}“" if title else ""
    best = plan.recommended
    if best is None:
        return f"Ich habe keinen Weg{target} gefunden. " + " ".join(plan.notes)
    hurry = " – du bist schon spät dran" if _late(best) else ""
    text = (f"Weg{target}: am besten mit {best.label}"
            + (f" ({best.detail})" if best.detail and best.mode == "train" else "")
            + f". Los um {_time(best.depart_at)}{hurry}, an um {_time(best.arrive_at)}, "
            f"{duration(best.duration_s)}, {price(best)}.")
    others = [f"{o.label} {duration(o.duration_s)}/{price(o)}" for o in plan.options[1:]]
    if others:
        text += " Alternativen: " + ", ".join(others) + "."
    return text


def trip_view(plan: TripPlan, title: str = "") -> TemplateView:
    best = plan.recommended
    return TemplateView("travel", {
        "title": f"Weg zu: {title}" if title else "Reiseplan",
        "route": f"{plan.origin.label} → {plan.destination.label}",
        "arrive_by": f"{_weekday(plan.arrive_by)} {plan.arrive_by:%d.%m. %H:%M} Uhr",
        "best": _option(best, plan) if best else None,
        "columns": ["Verkehrsmittel", "Abfahrt", "Dauer", "Preis", "Kosten¹"],
        "rows": [[o.label, _time(o.depart_at), duration(o.duration_s), price(o), euro(o.cost(plan.settings))]
                 for o in plan.options],
        "value_of_time": euro(plan.settings.value_of_time),
        "steps": list(best.steps[:MAX_STEPS]) if best else [],
        "map": _map(best, plan) if best else None,
        "notes": list(plan.notes),
        "attribution": ATTRIBUTION,
    })


def _option(option: Option, plan: TripPlan) -> dict:
    return {"label": option.label, "detail": option.detail, "depart": _time(option.depart_at),
            "arrive": _time(option.arrive_at), "duration": duration(option.duration_s),
            "price": price(option), "late": _late(option)}


def _map(option: Option, plan: TripPlan) -> dict:
    """Route auf MAP_WIDTH × MAP_HEIGHT projiziert. Ohne Linie (Bahn): Luftlinie."""
    points = list(option.geometry) or [(plan.origin.lon, plan.origin.lat), (plan.destination.lon, plan.destination.lat)]
    points = points[::max(1, len(points) // MAX_MAP_POINTS)] + [points[-1]]
    scale_x = math.cos(math.radians(sum(lat for _, lat in points) / len(points)))   # Längengrade enger
    xs, ys = [lon * scale_x for lon, _ in points], [lat for _, lat in points]
    span = max(max(xs) - min(xs), max(ys) - min(ys)) or 1e-9
    size = min(MAP_WIDTH, MAP_HEIGHT) - 2 * MAP_PADDING
    offset_x = (MAP_WIDTH - (max(xs) - min(xs)) / span * size) / 2
    offset_y = (MAP_HEIGHT - (max(ys) - min(ys)) / span * size) / 2
    projected = [(offset_x + (x - min(xs)) / span * size, offset_y + (max(ys) - y) / span * size)
                 for x, y in zip(xs, ys)]
    return {"width": MAP_WIDTH, "height": MAP_HEIGHT,
            "points": " ".join(f"{x:.1f},{y:.1f}" for x, y in projected),
            "start": [round(v, 1) for v in projected[0]], "end": [round(v, 1) for v in projected[-1]],
            "straight": not option.geometry}


def duration(seconds: float) -> str:
    minutes = max(1, round(seconds / 60))
    hours, minutes = divmod(minutes, 60)
    return f"{hours} Std. {minutes} Min." if hours else f"{minutes} Min."


def euro(amount: float) -> str:
    return f"{amount:.2f} €".replace(".", ",")


def price(option: Option) -> str:
    if option.price_eur == 0 and not option.price_estimated:
        return "kostenlos"
    return ("≈ " if option.price_estimated else "") + euro(option.price_eur)


def _time(moment: datetime.datetime | None) -> str:
    return f"{moment.astimezone():%H:%M}" if moment else "–"


def _late(option: Option) -> bool:
    return option.depart_at is not None and option.depart_at < datetime.datetime.now().astimezone()


_WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


def _weekday(moment: datetime.datetime) -> str:
    return _WEEKDAYS[moment.weekday()]
