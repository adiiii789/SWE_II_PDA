"""Reiseplan als Text (Chat und Sprachmodell) und als Ansicht (frontend/templates/travel.html.j2).

Die Ansicht hat je Verkehrsmittel einen Reiter mit Zeiten, Karte und Wegbeschreibung; zuerst ist
die Empfehlung gewählt. Umgeschaltet wird im iframe selbst (reines CSS), ohne Backend.

Bus und Bahn wie in der DB- oder VVS-App (_journey): oben Abfahrt → Ankunft, Dauer, Umstiege und
ein Balken aus den Etappen (Breite nach Dauer, Farbe der Linie), darunter die Zeitleiste - je Halt
Soll-Zeit und Prognose (grün pünktlich, rot verspätet), Gleis/Steig, je Fahrt das Linien-Badge mit
Richtung, aufklappbare Zwischenhalte und Hinweise, dazwischen Fußwege und Umstiegszeiten.
Linienfarben: von der Auskunft, sonst nach Verkehrsmittel (MODE_COLORS, wie im DB Navigator).
Fahrten, für die das Deutschlandticket nicht gilt (Fernverkehr), sind rot hinterlegt - vom
Einstieg bis zum Ausstieg (no_ticket an Etappe und Halten).

Die Karte ist ein SVG: die Route (Web-Mercator-Projektion wie die Kacheln) über
OpenStreetMap-Kacheln. Das iframe ist abgeschottet und lädt nichts nach - die Kacheln holt das
Backend (map_tiles.py) und bettet sie ein, jede nur einmal (alle Karten nutzen sie über <use>).
Ohne Kacheln (offline) bleibt die Skizze der Route. Bei Bus und Bahn hat jede Fahrt die Farbe
ihrer Linie, Fußwege sind gepunktet, Bus/Tram (geschätzt) gestrichelt, Halte und Umstiege markiert.
Die Karte steht oben im Reiter; ein Klick zeigt sie über die ganze Ansicht, dort lässt sie sich
zoomen und verschieben (Skript im Template). Damit sie auch groß scharf bleibt, ist sie in doppelter
Auflösung gerechnet (MAP_WIDTH × MAP_HEIGHT Kachelpixel) und wird klein in halber Größe gezeigt.
"""
from __future__ import annotations

import datetime
import math
from concurrent.futures import ThreadPoolExecutor

from backend.assistant.skills.travel.planner import (TRANSIT, VEHICLES, WALK, Option, Segment, Stage, TripPlan,
                                                     minutes_late, preferred_free)
from backend.integrations import map_tiles, weather
from backend.integrations.http import IntegrationError
from backend.integrations.map_tiles import MapTiles
from backend.integrations.openrouteservice import ATTRIBUTION
from backend.views import TemplateView

MAP_WIDTH, MAP_HEIGHT, MAP_PADDING = 960, 540, 48   # Kachelpixel; angezeigt halb so groß (scharf beim Vergrößern)
TILE_WORKERS = 2                                    # parallele Kachel-Downloads (OSM erlaubt höchstens 2)
MAX_MAP_POINTS = 300
MAX_STEPS = 15
ROUTE, STRAIGHT = "route", "straight"   # Linien der Karte außer WALK, TRANSIT, RAIL
TRAIN_COLORS = ("#e8590c", "#ae3ec9", "#0ca678", "#f08c00")   # je Zug, Bus oder Tram einer Verbindung
LINE_COLORS = {ROUTE: "#2f7de1", STRAIGHT: "#2f7de1", WALK: "#495057", TRANSIT: "#1098ad"}
# Verkehrsmittel → (Hintergrund, Schrift) des Linien-Badges, angelehnt an den DB Navigator
MODE_COLORS = {
    "SUBURBAN": ("#408335", "#ffffff"), "SUBWAY": ("#1455c0", "#ffffff"), "METRO": ("#1455c0", "#ffffff"),
    "TRAM": ("#c50014", "#ffffff"), "BUS": ("#814997", "#ffffff"), "COACH": ("#00a19a", "#ffffff"),
    "REGIONAL_RAIL": ("#646973", "#ffffff"), "REGIONAL_FAST_RAIL": ("#646973", "#ffffff"),
    "RAIL": ("#646973", "#ffffff"), "LONG_DISTANCE": ("#ec0016", "#ffffff"),
    "HIGHSPEED_RAIL": ("#ec0016", "#ffffff"), "NIGHT_RAIL": ("#282d37", "#ffffff"),
    "FERRY": ("#309fd1", "#ffffff"), "FUNICULAR": ("#a9455d", "#ffffff"),
}
OTHER_COLORS = ("#7d8590", "#ffffff")
MIN_BAR_PERCENT = 6   # so breit ist eine Etappe im Balken mindestens (sonst ist das Badge unlesbar)


def summary(plan: TripPlan, title: str = "", home: bool = False) -> str:
    """Kurzfassung für den Chat und als Werkzeugergebnis fürs Sprachmodell.
    home: Heimweg, title ist dann der Termin, von dem es heimgeht."""
    heading = (f"Heimweg von „{title}“" if title else "Heimweg") if home else         (f"Weg zu „{title}“" if title else "Weg")
    best = plan.recommended
    if best is None:
        return f"Ich habe keinen Weg gefunden ({heading}). " + " ".join(plan.notes)
    hurry = " – du bist schon spät dran" if _late(best) else ""
    behind = minutes_late(best, plan.arrive_by)
    if behind:
        hurry += f" – rechtzeitig geht es nicht mehr, du kommst {behind} Min. zu spät"
    text = (f"{heading}: am besten mit {best.label}"
            + (f" ({best.detail})" if best.detail and best.mode == "train" else "")
            + f". Los um {_time(best.depart_at)}{hurry}, an um {_time(best.arrive_at)}, "
            f"{duration(best.duration_s)}, {price(best)}.")
    others = [f"{o.label} {duration(o.duration_s)}/{price(o)}" for o in plan.options[1:]]
    if others:
        text += " Alternativen: " + ", ".join(others) + "."
    cheapest = free_preferred_over(plan)
    if cheapest is not None:
        text += f" {best.label} ist kostenlos und deshalb vorn – nach Kosten wäre {cheapest.label} besser."
    if plan.weather and any(o.weather_factor > 1 for o in plan.options):
        text += f" Wetter: {plan.weather.description} – Fahrrad/zu Fuß zählen deshalb schlechter."
    return text


def trip_view(plan: TripPlan, title: str = "", home: bool = False, tiles: MapTiles | None = None) -> TemplateView:
    """tiles: Kartenkacheln unter der Route; None = nur die Skizze."""
    if home:
        heading = f"Heimweg von: {title}" if title else "Heimweg"
    else:
        heading = f"Weg zu: {title}" if title else "Reiseplan"
    preferred = preferred_free(plan.options, plan.settings)
    shared: dict[tuple[int, int, int], dict] = {}   # Kacheln aller Karten, jede einmal
    maps: dict[tuple, dict] = {}                     # Auto und Taxi fahren dieselbe Route
    options = []
    for index, option in enumerate(plan.options):
        key = (option.geometry, option.segments)
        if key not in maps:
            maps[key] = _map(option, plan, tiles, shared)
        options.append({**_option(option, plan), "index": index, "recommended": index == 0,
                        "free": option.free, "preferred": option in preferred,
                        "steps": list(option.steps[:MAX_STEPS]), "map": maps[key],
                        "journey": _journey(option, plan) if option.stages else None})
    return TemplateView("travel", {
        "title": heading,
        "route": f"{plan.origin.label} → {plan.destination.label}",
        "arrive_by": _moment(plan.arrive_by) if plan.arrive_by else "",
        "depart_after": _moment(plan.depart_after) if plan.depart_after else "",
        "best": options[0] if options else None,
        "options": options,
        "free_note": _free_note(plan),
        "tiles": list(shared.values()),
        "columns": ["Verkehrsmittel", "Abfahrt", "Dauer", "Preis", "Kosten¹"],
        "rows": [[o.label + (f" ({o.weather_note})" if o.weather_note else ""), _time(o.depart_at),
                  duration(o.duration_s), price(o), euro(o.cost(plan.settings))]
                 for o in plan.options],
        "value_of_time": euro(plan.settings.value_of_time),
        "weather": plan.weather.description if plan.weather else "",
        "weather_attribution": weather.ATTRIBUTION if plan.weather else "",
        "notes": list(plan.notes),
        "attribution": " · ".join(dict.fromkeys([ATTRIBUTION,
                                                 *(o.attribution for o in plan.options if o.attribution)])),
    })


def _moment(moment: datetime.datetime) -> str:
    return f"{_weekday(moment)} {moment:%d.%m. %H:%M} Uhr"


def _option(option: Option, plan: TripPlan) -> dict:
    return {"label": option.label, "mode": option.mode, "detail": option.detail,
            "depart": _time(option.depart_at), "arrive": _time(option.arrive_at),
            "duration": duration(option.duration_s), "price": price(option), "late": _late(option),
            "minutes_late": minutes_late(option, plan.arrive_by), "weather_note": option.weather_note}


def _map(option: Option, plan: TripPlan, tiles: MapTiles | None = None,
         shared: dict[tuple[int, int, int], dict] | None = None) -> dict:
    """Route auf MAP_WIDTH × MAP_HEIGHT, in der größten Zoomstufe, in die sie ganz passt.
    Ohne Linie: Luftlinie (gestrichelt). Die Bahn besteht aus Segmenten (Fußwege, Züge), jedes
    eine eigene Linie; zwischen ihnen ein Punkt für den Bahnhof. shared sammelt die Kacheln aller
    Karten (Schlüssel Zoom, x, y) - die Karte verweist nur per id darauf."""
    segments = option.segments or (
        (Segment(ROUTE, option.geometry),) if option.geometry else
        (Segment(STRAIGHT, ((plan.origin.lon, plan.origin.lat), (plan.destination.lon, plan.destination.lat))),))
    step = max(1, sum(len(segment.points) for segment in segments) // MAX_MAP_POINTS)
    zoom = _zoom([point for segment in segments for point in segment.points])
    shown = [[map_tiles.pixel(lon, lat, zoom) for lon, lat in (*segment.points[:-1:step], segment.points[-1])]
             for segment in segments]
    xs, ys = [x for line in shown for x, _ in line], [y for line in shown for _, y in line]
    left = (min(xs) + max(xs) - MAP_WIDTH) / 2     # Route in der Mitte
    top = (min(ys) + max(ys) - MAP_HEIGHT) / 2
    shown = [[(x - left, y - top) for x, y in line] for line in shown]
    lines, trains = [], 0
    stages = option.stages if len(option.stages) == len(segments) else ()   # Farbe der Linie, wenn bekannt
    for index, (segment, line) in enumerate(zip(segments, shown)):
        color = LINE_COLORS.get(segment.kind) or (stage_colors(stages[index])[0] if stages
                                                  else TRAIN_COLORS[trains % len(TRAIN_COLORS)])
        trains += segment.kind in VEHICLES
        lines.append({"kind": segment.kind, "color": color, "label": segment.label,
                      "points": " ".join(f"{x:.1f},{y:.1f}" for x, y in line)})
    rides = [index for index, segment in enumerate(segments) if segment.kind in VEHICLES]
    stops = [{"x": round(line[0][0], 1), "y": round(line[0][1], 1), "name": segments[index - 1].end,
              "transfer": bool(rides) and rides[0] < index <= rides[-1]}   # zwischen zwei Fahrzeugen
             for index, line in enumerate(shown[1:], 1)]
    background = _tiles(tiles, zoom, left, top, {} if shared is None else shared)
    return {"width": MAP_WIDTH, "height": MAP_HEIGHT, "lines": lines, "stops": stops,
            "legend": [line for line in lines if line["label"]] if len(lines) > 1 else [],
            "start": [round(v, 1) for v in shown[0][0]], "end": [round(v, 1) for v in shown[-1][-1]],
            "straight": segments[0].kind == STRAIGHT, "tiles": background,
            "attribution": map_tiles.ATTRIBUTION if background else ""}


def free_preferred_over(plan: TripPlan) -> Option | None:
    """Das nach Kosten beste Verkehrsmittel, wenn die Empfehlung nur vorn ist, weil sie kostenlos ist."""
    best = plan.recommended
    if best is None or best not in preferred_free(plan.options, plan.settings):
        return None
    cheapest = min(plan.options, key=lambda option: option.cost(plan.settings))
    return cheapest if cheapest is not best and cheapest.cost(plan.settings) < best.cost(plan.settings) else None


def _free_note(plan: TripPlan) -> str:
    cheapest = free_preferred_over(plan)
    if cheapest is None:
        return ""
    return (f"{plan.recommended.label} steht vorn, weil es kostenlos ist – nach Kosten (Preis und Zeit) "
            f"wäre {cheapest.label} besser. Einstellen unter ⚙ Einstellungen → Reise.")


def stage_colors(stage: Stage) -> tuple[str, str]:
    """(Hintergrund, Schrift) für das Badge und die Linie einer Fahrt."""
    if stage.color:
        return stage.color, stage.text_color or "#ffffff"
    if stage.kind == TRANSIT:
        return MODE_COLORS["BUS"]
    return MODE_COLORS.get(stage.mode, OTHER_COLORS)


def _journey(option: Option, plan: TripPlan) -> dict:
    """Bus und Bahn für die Ansicht wie in der DB- oder VVS-App: Kopf mit Balken und Zeitleiste
    aus Halten (stops) und Etappen (links) im Wechsel."""
    stages = option.stages
    rides = [stage for stage in stages if stage.kind in VEHICLES]
    total = sum(max(stage.minutes, 1) for stage in stages)
    bar = []
    for stage in stages:
        background, text = stage_colors(stage) if stage.kind != WALK else ("", "")
        bar.append({"kind": stage.kind, "line": stage.line, "background": background, "text": text,
                    "no_ticket": stage.long_distance,
                    "percent": round(max(MIN_BAR_PERCENT, 100 * max(stage.minutes, 1) / total), 1)})
    items = [_halt(None, stages[0], plan)]
    for index, stage in enumerate(stages):
        before = stages[index - 1] if index else None
        after = stages[index + 1] if index + 1 < len(stages) else None
        items.append(_link(stage, transfer=stage.kind == WALK and before is not None and after is not None
                           and before.kind in VEHICLES and after.kind in VEHICLES))
        items.append(_halt(stage, after, plan))
    return {"depart": _time(option.depart_at), "arrive": _time(option.arrive_at),
            "duration": duration(option.duration_s),
            "transfers": "direkt" if len(rides) <= 1 else f"{len(rides) - 1} Umstieg" + ("e" if len(rides) > 2 else ""),
            "realtime": any(stage.realtime for stage in rides), "bar": bar, "items": items,
            "no_ticket": [stage.line for stage in rides if stage.long_distance]}


def _halt(arriving: Stage | None, leaving: Stage | None, plan: TripPlan) -> dict:
    """Halt zwischen zwei Etappen: Ankunft der einen, Abfahrt der nächsten. Start und Ziel heißen
    wie die Adressen; ein Umstieg ohne Fußweg zeigt die Wartezeit."""
    if arriving is None:
        name = plan.origin.label if leaving.origin == "Start" else leaving.origin
    else:
        name = plan.destination.label if arriving.destination == "Ziel" else arriving.destination
    ride_in = arriving is not None and arriving.kind in VEHICLES
    ride_out = leaving is not None and leaving.kind in VEHICLES
    wait = ""
    if ride_in and ride_out:
        wait = f"Umstieg · {max(0, round((leaving.departure - arriving.arrival).total_seconds() / 60))} Min."
    return {"name": name, "kind": _halt_kind(arriving, leaving),
            "arrive": _clock_times(arriving.arrival, arriving.arrival_delay, arriving.realtime) if ride_in else None,
            "depart": _clock_times(leaving.departure, leaving.departure_delay, leaving.realtime)
            if leaving is not None and (ride_out or arriving is None) else None,
            "end_time": _clock_times(arriving.arrival, 0, False) if leaving is None else None,
            "platform": _stand(leaving, leaving.platform) if ride_out and leaving.platform else
            _stand(arriving, arriving.arrival_platform) if ride_in and arriving.arrival_platform else "",
            "wait": wait, "line_in": _track(arriving), "line_out": _track(leaving),
            # Halt gehört zum roten Bereich, wenn hier eine Fernverkehrsfahrt beginnt oder endet
            "no_ticket_in": arriving is not None and arriving.long_distance,
            "no_ticket_out": leaving is not None and leaving.long_distance}


def _track(stage: Stage | None) -> dict:
    """Linienstück am Punkt eines Halts, damit die Zeitleiste durchgeht: Art (ride, walk, transit;
    leer = keins) und Farbe der Etappe davor bzw. danach."""
    if stage is None:
        return {"kind": "", "color": ""}
    if stage.kind in VEHICLES:
        return {"kind": "ride", "color": stage_colors(stage)[0]}
    if stage.kind == TRANSIT:
        return {"kind": "transit", "color": stage_colors(stage)[0]}
    return {"kind": "walk", "color": ""}


def _halt_kind(arriving: Stage | None, leaving: Stage | None) -> str:
    """start, end, transfer (zwischen zwei Fahrten, auch an beiden Enden eines Umstiegs-Fußwegs) oder stop."""
    if arriving is None:
        return "start"
    if leaving is None:
        return "end"
    ride_in, ride_out = arriving.kind in VEHICLES, leaving.kind in VEHICLES
    walk_on = leaving.kind == WALK and leaving.destination != "Ziel"      # zu Fuß zur nächsten Fahrt
    walked_in = arriving.kind == WALK and arriving.origin != "Start"      # zu Fuß von der letzten Fahrt
    return "transfer" if ride_in and (ride_out or walk_on) or ride_out and walked_in else "stop"


def _link(stage: Stage, transfer: bool) -> dict:
    """Etappe zwischen zwei Halten: Fahrt (Badge, Richtung, Zwischenhalte, Hinweise) oder Fußweg."""
    if stage.kind in VEHICLES:
        background, text = stage_colors(stage)
        return {"kind": "ride", "line": stage.line, "background": background, "text": text,
                "headsign": stage.headsign, "minutes": stage.minutes,
                "stops": [{"name": name, "time": _time(moment) if moment else ""} for name, moment in stage.stops],
                "messages": list(stage.messages), "no_ticket": stage.long_distance}
    if stage.kind == TRANSIT:
        return {"kind": "transit", "label": f"≈ {stage.minutes} Min. Bus/Tram (geschätzt)",
                "background": stage_colors(stage)[0], "no_ticket": False}
    return {"kind": "walk", "label": f"{'Umstieg · ' if transfer else ''}{stage.minutes} Min. Fußweg",
            "background": "", "no_ticket": False}


def _clock_times(moment: datetime.datetime, delay: int, realtime: bool) -> dict:
    """Soll-Zeit und Prognose wie auf der Anzeigetafel: pünktlich grün, verspätet rot."""
    planned = moment - datetime.timedelta(minutes=delay)
    return {"planned": _time(planned), "actual": _time(moment) if realtime or delay else "",
            "late": delay > 0}


def _stand(stage: Stage, platform: str) -> str:
    rail = stage.mode in ("SUBURBAN", "SUBWAY", "METRO", "REGIONAL_RAIL", "REGIONAL_FAST_RAIL", "RAIL",
                          "LONG_DISTANCE", "HIGHSPEED_RAIL", "NIGHT_RAIL")
    return f"{'Gl.' if rail else 'Steig'} {platform}"


def _zoom(points: list[tuple[float, float]]) -> int:
    for zoom in range(map_tiles.MAX_ZOOM, -1, -1):
        pixels = [map_tiles.pixel(lon, lat, zoom) for lon, lat in points]
        width = max(x for x, _ in pixels) - min(x for x, _ in pixels)
        height = max(y for _, y in pixels) - min(y for _, y in pixels)
        if width <= MAP_WIDTH - 2 * MAP_PADDING and height <= MAP_HEIGHT - 2 * MAP_PADDING:
            return zoom
    return 0


def _tiles(tiles: MapTiles | None, zoom: int, left: float, top: float,
           shared: dict[tuple[int, int, int], dict]) -> list[dict]:
    """Kacheln, die den Ausschnitt abdecken: Lage im SVG und id in shared (dort mit href). Alle oder keine."""
    if tiles is None:
        return []
    size, count = map_tiles.TILE_SIZE, 2 ** zoom
    placed = [((zoom, tile_x % count, tile_y), tile_x, tile_y)
              for tile_y in range(math.floor(top / size), math.floor((top + MAP_HEIGHT) / size) + 1)
              if 0 <= tile_y < count
              for tile_x in range(math.floor(left / size), math.floor((left + MAP_WIDTH) / size) + 1)]
    missing = list(dict.fromkeys(key for key, _, _ in placed if key not in shared))
    try:
        with ThreadPoolExecutor(TILE_WORKERS) as pool:
            hrefs = list(pool.map(lambda key: tiles.data_uri(*key), missing))
    except IntegrationError:
        return []
    for key, href in zip(missing, hrefs):
        shared[key] = {"id": "tile-%d-%d-%d" % key, "size": size, "href": href}
    return [{"x": round(tile_x * size - left, 1), "y": round(tile_y * size - top, 1), "size": size,
             "id": shared[key]["id"]} for key, tile_x, tile_y in placed]


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


LATE_TOLERANCE = datetime.timedelta(minutes=2)   # "jetzt los" ist ein paar Sekunden später nicht "spät dran"


def _late(option: Option) -> bool:
    return option.depart_at is not None and option.depart_at < datetime.datetime.now().astimezone() - LATE_TOLERANCE


_WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


def _weekday(moment: datetime.datetime) -> str:
    return _WEEKDAYS[moment.weekday()]
