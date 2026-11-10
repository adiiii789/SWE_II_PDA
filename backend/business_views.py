"""Visuelle Ansichten für Kalender, Aufgaben und Mails im Anzeigebereich über dem Chat.

Die Werkzeuge list_calendar_events, list_tasks und list_emails (mcp_servers/pda_server.py) liefern
neben dem Text fürs Sprachmodell dieselben Daten als structuredContent (ToolResult.data). Daraus
entstehen hier Komponenten für frontend/templates/dashboard.html.j2:

  Kalender  1 Tag -> Tagesansicht, 2-7 Tage -> Wochenansicht, mehr -> Monatsraster
  Aufgaben  Liste zum Abhaken (das iframe meldet den Klick ans Popup, siehe api.complete_task_from_view)
  Mails     Postfach; ein Klick lässt den Assistenten die Mail vorlesen

Mehrere Abfragen einer Antwort ("Was steht heute an?" -> Termine + Aufgaben) erscheinen zusammen.
Alles Rechnen (Lage der Terminblöcke, Überschneidungen, Beschriftungen) passiert hier, damit das
Template einfach bleibt. Text aus den Daten setzt das Template nur escaped ein (Autoescaping), Farben
werden hier geprüft, weil sie in style-Attributen landen.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any

HOUR_PX = 44                 # Höhe einer Stunde in Tages- und Wochenansicht
MIN_EVENT_PX = 20            # auch kurze Termine bleiben lesbar
DEFAULT_SCROLL_HOUR = 7      # ohne Termine beginnt die Ansicht hier
VISIBLE_PX = 300             # sichtbare Höhe der Zeitleiste (max-height von .tl-scroll in dashboard.css)
MONTH_EVENTS_PER_DAY = 3     # danach "+n"
DEFAULT_COLOR = "#5B8DEF"

WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
WEEKDAYS_SHORT = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
MONTHS = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
          "November", "Dezember")
INVITATIONS = {"needsAction": "Einladung offen", "tentative": "Vorbehalt", "declined": "Abgesagt"}

_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")


# --- Einstieg ----------------------------------------------------------------------------------
def components(results: Iterable[Mapping[str, Any]], now: dt.datetime) -> list[dict[str, Any]]:
    """Komponenten aus den Daten der Werkzeug-Ergebnisse, in Aufrufreihenfolge, doppelte nur einmal."""
    found, seen = [], set()
    for data in results:
        builder = _BUILDERS.get(data.get("type")) if isinstance(data, Mapping) else None
        key = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str) if builder else ""
        if not builder or key in seen:
            continue
        seen.add(key)
        try:
            found.append(builder(data, now))
        except (KeyError, TypeError, ValueError):   # unerwartete Daten: lieber ohne Ansicht als Absturz
            continue
    return found


# --- Kalender ----------------------------------------------------------------------------------
def calendar_component(data: Mapping[str, Any], now: dt.datetime) -> dict[str, Any]:
    first = dt.date.fromisoformat(data["start"])
    days = max(1, int(data["days"]))
    events = [_event(raw) for raw in data.get("events", [])]
    today = now.date()
    subtitle = _count(len(events), "Termin", "Termine") + (" (es gibt weitere)" if data.get("more") else "")
    if data.get("query"):
        subtitle += f" · Suche: {data['query']}"
    if days > 7:
        return {"kind": "month", "title": _range_title(first, days), "subtitle": subtitle,
                **_month(first, days, events, today)}
    day_list = [first + dt.timedelta(days=offset) for offset in range(days)]
    title = _day_title(first, today) if days == 1 else _range_title(first, days)
    return {"kind": "day" if days == 1 else "week", "title": title, "subtitle": subtitle,
            **_timeline(day_list, events, now)}


def _event(raw: Mapping[str, Any]) -> dict[str, Any]:
    all_day = bool(raw.get("all_day"))
    if all_day:
        start = dt.datetime.combine(dt.date.fromisoformat(raw["start"]), dt.time.min)
        end = dt.datetime.combine(dt.date.fromisoformat(raw["end"]), dt.time.min)   # exklusiv
    else:
        start = _naive(dt.datetime.fromisoformat(raw["start"]))
        end = _naive(dt.datetime.fromisoformat(raw["end"]))
    color = raw.get("color") if _HEX_COLOR.fullmatch(str(raw.get("color", ""))) else DEFAULT_COLOR
    status = INVITATIONS.get(raw.get("invitation", ""), "")
    details = [raw.get("location", ""), raw.get("calendar", "") if not raw.get("primary") else "", status]
    return {"title": str(raw.get("title", "")) or "(ohne Titel)", "start": start, "end": max(end, start),
            "all_day": all_day, "color": color, "tint": _tint(color, 0.18), "location": raw.get("location", ""),
            "status": status, "declined": raw.get("invitation") == "declined",
            "details": " · ".join(part for part in details if part)}


def _timeline(day_list: list[dt.date], events: list[dict], now: dt.datetime) -> dict[str, Any]:
    columns, earliest = [], None
    for day in day_list:
        begin = dt.datetime.combine(day, dt.time.min)
        end = begin + dt.timedelta(days=1)
        timed = [event for event in events if not event["all_day"] and event["start"] < end
                 and (event["end"] > begin or event["start"] == event["end"] >= begin)]
        blocks = _place(timed, begin, end)
        if blocks:
            first_top = min(block["top"] for block in blocks)
            earliest = first_top if earliest is None else min(earliest, first_top)
        columns.append({
            "label": f"{WEEKDAYS_SHORT[day.weekday()]} {day.day}.", "date": day.isoformat(),
            "today": day == now.date(), "weekend": day.weekday() >= 5,
            "all_day": [_chip(event) for event in events if event["all_day"]
                        and event["start"].date() <= day < event["end"].date()],
            "blocks": blocks,
            "now": _minutes(now.replace(tzinfo=None) - begin) * HOUR_PX / 60 if day == now.date() else None,
        })
    # Startposition: beim ersten Termin; ist heute dabei, auch die aktuelle Uhrzeit noch im Bild
    scroll = (earliest if earliest is not None else DEFAULT_SCROLL_HOUR * HOUR_PX) - HOUR_PX / 2
    now_top = next((column["now"] for column in columns if column["now"] is not None), None)
    if now_top is not None:
        scroll = max(min(scroll, now_top - HOUR_PX), now_top - (VISIBLE_PX - HOUR_PX))
    return {"columns": columns, "hours": [f"{hour:02d}:00" for hour in range(24)], "hour_px": HOUR_PX,
            "height": 24 * HOUR_PX, "scroll": max(0, round(scroll)),
            "has_all_day": any(column["all_day"] for column in columns)}


def _place(timed: list[dict], begin: dt.datetime, end: dt.datetime) -> list[dict]:
    """Terminblöcke eines Tages; sich überschneidende stehen nebeneinander."""
    pieces = sorted(((max(event["start"], begin), min(max(event["end"], event["start"]), end), event)
                     for event in timed), key=lambda piece: (piece[0], -(piece[1] - piece[0]).total_seconds()))
    blocks: list[dict] = []
    cluster: list[dict] = []
    cluster_end = None
    lanes: list[dt.datetime] = []
    for start, stop, event in pieces:
        if cluster_end is not None and start >= cluster_end:   # neue Gruppe ohne Überschneidung
            _finish(cluster, len(lanes))
            cluster, lanes, cluster_end = [], [], None
        lane = next((index for index, lane_end in enumerate(lanes) if lane_end <= start), len(lanes))
        visible_stop = max(stop, start + dt.timedelta(minutes=MIN_EVENT_PX * 60 / HOUR_PX))
        if lane == len(lanes):
            lanes.append(visible_stop)
        else:
            lanes[lane] = visible_stop
        cluster_end = visible_stop if cluster_end is None else max(cluster_end, visible_stop)
        top = _minutes(start - begin) * HOUR_PX / 60
        height = max(MIN_EVENT_PX, _minutes(stop - start) * HOUR_PX / 60)
        block = {"title": event["title"], "time": _time_range(event, begin, end), "location": event["location"],
                 "details": event["details"], "color": event["color"], "tint": event["tint"],
                 "declined": event["declined"], "top": round(top, 1), "height": round(height, 1),
                 "lane": lane, "compact": height < 38}
        cluster.append(block)
        blocks.append(block)
    _finish(cluster, len(lanes))
    return blocks


def _finish(cluster: list[dict], lanes: int) -> None:
    for block in cluster:
        block["left"] = round(100 * block["lane"] / max(lanes, 1), 2)
        block["width"] = round(100 / max(lanes, 1), 2)


def _month(first: dt.date, days: int, events: list[dict], today: dt.date) -> dict[str, Any]:
    last = first + dt.timedelta(days=days - 1)
    cursor = first - dt.timedelta(days=first.weekday())
    weeks = []
    while cursor <= last:
        week = []
        for _ in range(7):
            day_events = sorted((event for event in events if _on_day(event, cursor)),
                                key=lambda event: (not event["all_day"], event["start"]))
            week.append({"day": cursor.day, "month_start": cursor.day == 1, "label": _month_label(cursor),
                         "in_range": first <= cursor <= last, "today": cursor == today,
                         "weekend": cursor.weekday() >= 5,
                         "events": [_chip(event) for event in day_events[:MONTH_EVENTS_PER_DAY]],
                         "more": max(0, len(day_events) - MONTH_EVENTS_PER_DAY)})
            cursor += dt.timedelta(days=1)
        weeks.append(week)
    return {"weekdays": list(WEEKDAYS_SHORT), "weeks": weeks}


def _on_day(event: dict, day: dt.date) -> bool:
    begin = dt.datetime.combine(day, dt.time.min)
    end = begin + dt.timedelta(days=1)
    if event["all_day"]:
        return event["start"].date() <= day < event["end"].date()
    return event["start"] < end and (event["end"] > begin or event["start"] == event["end"] >= begin)


def _chip(event: dict) -> dict[str, Any]:
    time = "" if event["all_day"] else f"{event['start']:%H:%M}"
    return {"title": event["title"], "time": time, "color": event["color"], "tint": event["tint"],
            "details": event["details"], "declined": event["declined"]}


def _time_range(event: dict, begin: dt.datetime, end: dt.datetime) -> str:
    start_text = f"{event['start']:%H:%M}" if event["start"] >= begin else "…"
    end_text = f"{event['end']:%H:%M}" if event["end"] <= end else "…"
    return start_text if event["start"] == event["end"] else f"{start_text}–{end_text}"


# --- Aufgaben ----------------------------------------------------------------------------------
def tasks_component(data: Mapping[str, Any], now: dt.datetime) -> dict[str, Any]:
    today = now.date()
    completed = bool(data.get("completed"))
    tasks = []
    for raw in data.get("tasks", []):
        due = dt.date.fromisoformat(raw["due"]) if raw.get("due") else None
        tasks.append({"id": str(raw["id"]), "title": str(raw.get("title", "")) or "(ohne Titel)",
                      "notes": raw.get("notes", ""), "time": raw.get("time", ""),
                      "list": raw.get("list", "") if data.get("several_lists") else "",
                      "depth": min(int(raw.get("depth", 0)), 3), "done": bool(raw.get("done")),
                      "due": _due_label(due, today) if due else "",
                      "due_state": "" if not due or completed else
                      "overdue" if due < today else "today" if due == today else ""})
    if completed:
        title, subtitle = "Erledigte Aufgaben", _count(len(tasks), "Aufgabe", "Aufgaben")
    else:
        title = "Aufgaben"
        subtitle = _count(len(tasks), "offene Aufgabe", "offene Aufgaben")
        if data.get("due_until"):
            subtitle += f" · fällig bis {_due_label(dt.date.fromisoformat(data['due_until']), today)}"
    if data.get("more"):
        subtitle += " (es gibt weitere)"
    if data.get("query"):
        subtitle += f" · Suche: {data['query']}"
    return {"kind": "tasks", "title": title, "subtitle": subtitle, "tasks": tasks, "completed": completed}


def _due_label(due: dt.date, today: dt.date) -> str:
    delta = (due - today).days
    named = {-1: "Gestern", 0: "Heute", 1: "Morgen"}.get(delta)
    if named:
        return named
    if 1 < delta < 7:
        return f"{WEEKDAYS_SHORT[due.weekday()]} {due:%d.%m.}"
    return f"{due:%d.%m.}" if due.year == today.year else f"{due:%d.%m.%Y}"


# --- Mails -------------------------------------------------------------------------------------
def mails_component(data: Mapping[str, Any], now: dt.datetime) -> dict[str, Any]:
    mails = []
    for raw in data.get("mails", []):
        sent = _naive(dt.datetime.fromisoformat(raw["date"])) if raw.get("date") else None
        uid = str(raw["uid"])
        if not uid.isdigit():
            continue
        mails.append({"uid": uid, "sender": str(raw.get("sender", "")) or str(raw.get("address", "")),
                      "address": raw.get("address", ""), "subject": str(raw.get("subject", "")),
                      "unread": not raw.get("seen"), "date": _mail_date(sent, now) if sent else ""})
    title = "Ungelesene Mails" if data.get("unread_only") else "Posteingang"
    subtitle = _count(len(mails), "Mail", "Mails")
    unread = sum(mail["unread"] for mail in mails)
    if unread and not data.get("unread_only"):
        subtitle += f" · {unread} ungelesen"
    if data.get("query"):
        subtitle += f" · Suche: {data['query']}"
    return {"kind": "mails", "title": title, "subtitle": subtitle, "mails": mails}


def _mail_date(sent: dt.datetime, now: dt.datetime) -> str:
    delta = (now.date() - sent.date()).days
    if delta == 0:
        return f"{sent:%H:%M}"
    if delta == 1:
        return "Gestern"
    if 1 < delta < 7:
        return WEEKDAYS_SHORT[sent.weekday()]
    return f"{sent:%d.%m.}" if sent.year == now.year else f"{sent:%d.%m.%Y}"


# --- Hilfen ------------------------------------------------------------------------------------
def _naive(moment: dt.datetime) -> dt.datetime:
    """Ortszeit ohne Zeitzone - die Daten kommen schon in Ortszeit, gerechnet wird lokal."""
    return moment.astimezone().replace(tzinfo=None) if moment.tzinfo else moment


def _minutes(delta: dt.timedelta) -> float:
    return delta.total_seconds() / 60


def _tint(color: str, alpha: float) -> str:
    red, green, blue = (int(color[index:index + 2], 16) for index in (1, 3, 5))
    return f"rgba({red}, {green}, {blue}, {alpha})"


def _count(number: int, one: str, many: str) -> str:
    return f"{'Keine' if number == 0 else number} {one if number == 1 else many}"


def _day_title(day: dt.date, today: dt.date) -> str:
    named = {0: "Heute", 1: "Morgen", -1: "Gestern"}.get((day - today).days)
    text = f"{WEEKDAYS[day.weekday()]}, {day.day}. {MONTHS[day.month - 1]}"
    if day.year != today.year:
        text += f" {day.year}"
    return f"{named} · {text}" if named else text


def _range_title(first: dt.date, days: int) -> str:
    last = first + dt.timedelta(days=days - 1)
    if first.day == 1 and (last + dt.timedelta(days=1)).day == 1 and first.month == last.month:
        return f"{MONTHS[first.month - 1]} {first.year}"
    if first.year != last.year:
        return f"{first:%d.%m.%Y} – {last:%d.%m.%Y}"
    if first.month != last.month:
        return f"{first.day}. {MONTHS[first.month - 1]} – {last.day}. {MONTHS[last.month - 1]} {last.year}"
    return f"{first.day}.–{last.day}. {MONTHS[first.month - 1]} {first.year}"


def _month_label(day: dt.date) -> str:
    return f"{day.day}. {MONTHS[day.month - 1][:3]}" if day.day == 1 else str(day.day)


_BUILDERS: dict[str, Callable[[Mapping[str, Any], dt.datetime], dict[str, Any]]] = {
    "calendar": calendar_component,
    "tasks": tasks_component,
    "mails": mails_component,
}
