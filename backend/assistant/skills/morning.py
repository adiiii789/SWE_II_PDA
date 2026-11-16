"""Baut das tägliche Morning-Briefing aus Kalender, Wetter, Aktien und Musik.

Die Daten kommen über die Werkzeuge des MCP-Servers (mcp_servers/pda_server.py), dieselben
Quellen, die auch das Sprachmodell nutzt (get_weather_forecast, get_stock_quotes):
  watch_calendar_events   Termine von heute (Google Kalender)
  watch_morning_weather   Wetter von heute (Open-Meteo, mcp_servers/morning_sources.py)
  watch_stock_quotes      Schlusskurse bis gestern (Alpha Vantage, ebenda)
Hier entsteht nur die Darstellung. Ohne Werkzeuge (nur feste Befehle) oder bei einem Fehler zeigt
das Briefing statt des Teils einen Hinweis; der Songvorschlag braucht keine Quelle.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from collections.abc import Callable
from typing import Any

from backend.assistant.skills.morning_music import song_for
from backend.assistant.tools import ToolResult
from backend.proactive import Occasion
from backend.views import TemplateView

_MAX_EVENTS = 5
_SOURCE_ERRORS = (ValueError, TypeError, KeyError, IndexError, OverflowError, AttributeError)
_WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")

CallTool = Callable[[str, dict[str, Any]], ToolResult]


def prepare(now: dt.datetime, options: dict[str, Any], call_tool: CallTool | None = None) -> Occasion:
    """Lädt das Briefing für den Chat und den Wächter mit denselben Quellen."""
    events = _source(call_tool, "watch_calendar_events", {"days": 1})
    weather = stocks = None
    if options["weather_location"].strip():
        weather = _source(call_tool, "watch_morning_weather", {"location": options["weather_location"]})
    if options["stock_symbols"].strip():
        yesterday = (now.date() - dt.timedelta(days=1)).isoformat()
        stocks = _source(call_tool, "watch_stock_quotes", {"symbols": options["stock_symbols"], "until": yesterday})
    return compose(now, options, events if isinstance(events, list) else None, weather, stocks)


def _source(call_tool: CallTool | None, name: str, arguments: dict[str, Any]) -> Any:
    """JSON eines Werkzeugs; {"error": Text} bei einem Fehler des Werkzeugs, None ohne Werkzeuge."""
    if call_tool is None:
        return None
    try:
        result = call_tool(name, arguments)
        if result.is_error:
            return {"error": result.content}
        return json.loads(result.content)
    except Exception:  # noqa: BLE001  # eine Quelle darf das Briefing nicht verhindern
        return None


def compose(now: dt.datetime, options: dict[str, Any], events: list[dict] | None,
            weather: Any = None, stocks: Any = None) -> Occasion:
    """Tagesübersicht, kompakte Chat-Nachricht und Text zum Vorlesen. weather/stocks: Antworten von
    watch_morning_weather bzw. watch_stock_quotes ({"error": …} bei einem Fehler, None = keine)."""
    day = now.date()
    title, artist, spotify_url, cover = song_for(day, options.get("music_genre", "mixed"))
    calendar = _calendar(events, day)
    weather = _weather(options["weather_location"], weather)
    weather.setdefault("location", options["weather_location"])
    stocks = _stocks(options["stock_symbols"], stocks)
    view = TemplateView("morning", {
        "date": f"{_WEEKDAYS[day.weekday()]}, {day:%d.%m.%Y}",
        "calendar": calendar, "weather": weather, "stocks": stocks,
        "song": {"title": title, "artist": artist, "url": spotify_url, "cover": cover},
    })
    text = "\n".join((
        "Guten Morgen! Hier ist dein Briefing.",
        f"Termine. {_calendar_text(calendar)}",
        f"Wetter. {_weather_text(weather)}",
        f"Börse. {_stock_text(stocks)}",
        f"Songvorschlag. {title} von {artist}.",
    ))
    chat_text = f"Dein Tagesüberblick ist bereit.\n\n[Auf Spotify anhören]({spotify_url})"
    return Occasion("Guten Morgen", "", text, "Täglich (Morning Assistant)", view=view, chat_text=chat_text)


def _calendar(events: list[dict] | None, day: dt.date) -> dict[str, Any]:
    if events is None:
        return {"status": "Google Kalender ist gerade nicht verfügbar."}
    midnight = dt.datetime.combine(day, dt.time.min)
    tomorrow = midnight + dt.timedelta(days=1)
    items = []
    try:
        for event in events:
            if event["response"] == "declined":
                continue
            if event["all_day"]:
                if not dt.date.fromisoformat(event["start"]) <= day < dt.date.fromisoformat(event["end"]):
                    continue
                start, label = midnight, "Ganztägig"
            else:
                start = dt.datetime.fromisoformat(event["start"]).astimezone().replace(tzinfo=None)
                end = dt.datetime.fromisoformat(event["end"]).astimezone().replace(tzinfo=None)
                if start >= tomorrow or (start < midnight and end <= midnight):
                    continue
                label = f"{start:%H:%M} Uhr" if start >= midnight else "Läuft bereits"
            items.append((start, label, _text(event["title"]) or "(ohne Titel)"))
    except _SOURCE_ERRORS:
        return {"status": "Google Kalender hat keine lesbaren Termine geliefert."}
    if not items:
        return {"status": "Heute stehen keine Termine an."}
    return {"entries": [{"time": label, "title": title} for _, label, title in sorted(items)[:_MAX_EVENTS]],
            "total": len(items), "remaining": max(0, len(items) - _MAX_EVENTS)}


def _weather(location: str, data: Any) -> dict[str, Any]:
    if not location.strip():
        return {"status": "Wetterort in den Einstellungen eintragen."}
    if isinstance(data, dict) and "error" in data:
        return {"status": _text(data["error"]) or "Open-Meteo ist gerade nicht verfügbar."}
    try:
        today = data["days"][0]
        return {"location": _text(data["location"]), "low": _degrees(today["low"]), "high": _degrees(today["high"]),
                "condition": _text(today["condition"]), "icon": _text(today["icon"]),
                "hours": [{"time": _text(hour["time"]), "condition": _text(hour["condition"]),
                           "icon": _text(hour["icon"]),
                           "temp": _degrees(hour["temp"]) if hour["temp"] is not None else None}
                          for hour in today["hours"]]}
    except _SOURCE_ERRORS:
        return {"status": "Open-Meteo ist gerade nicht verfügbar."}


def _stocks(watchlist: str, data: Any) -> dict[str, Any]:
    if not watchlist.strip():
        return {"status": "Aktienkürzel in den Einstellungen eintragen."}
    if isinstance(data, dict) and "error" in data:
        return {"status": _text(data["error"]) or "Börsendaten sind gerade nicht verfügbar."}
    try:
        quotes = [_quote(quote) for quote in data["quotes"]]
    except _SOURCE_ERRORS:
        return {"status": "Börsendaten sind gerade nicht verfügbar."}
    trend_sessions = max((quote["trend"]["sessions"] for quote in quotes if "trend" in quote), default=0)
    return {"quotes": quotes, "trend_sessions": trend_sessions}


def _quote(quote: dict[str, Any]) -> dict[str, Any]:
    label = _text(quote["symbol"])
    try:
        close, previous_close = _number(quote["close"]), _number(quote["previous_close"])
        if close <= 0 or previous_close <= 0:
            raise ValueError("Ungültiger Schlusskurs")
        percent = round((close / previous_close - 1) * 100, 2)
        return {"symbol": label, "close": f"{close:.2f}".replace(".", ","),
                "change": f"{percent:+.2f}".replace(".", ",") if percent else "0,00",
                "direction": "up" if percent > 0 else "down" if percent < 0 else "flat",
                "day": f"{dt.date.fromisoformat(quote['day']):%d.%m.}",
                "trend": _stock_trend([_number(value) for value in quote["closes"]] or [previous_close, close])}
    except _SOURCE_ERRORS:
        return {"symbol": label}


def _stock_trend(closes: list[float]) -> dict[str, Any]:
    """Kurslinie aus den Schlusskursen (älteste zuerst); die Endpunkte liegen bei x=2 und x=62."""
    closes = [close for close in closes if close > 0]
    if len(closes) < 2:
        raise ValueError("Zu wenige Kurse für eine Linie")
    low, high = min(closes), max(closes)
    ys = [2 + 20 * ((high - close) / (high - low)) if high > low else 12 for close in closes]
    points = " ".join(f"{2 + 60 * index / (len(ys) - 1):.1f},{y:.1f}" for index, y in enumerate(ys))
    return {"points": points, "last_y": f"{ys[-1]:.1f}", "sessions": len(ys)}


def _calendar_text(calendar: dict[str, Any]) -> str:
    if "status" in calendar:
        return calendar["status"]
    entries = [f"{entry['time']} {entry['title']}." for entry in calendar["entries"]]
    if calendar["remaining"]:
        entries.append(f"Und {calendar['remaining']} weitere.")
    return " ".join(entries)


def _weather_text(weather: dict[str, Any]) -> str:
    if "status" in weather:
        return weather["status"]
    return f"{weather['location']}, {weather['low']} bis {weather['high']} Grad. {weather['condition']}."


def _stock_text(stocks: dict[str, Any]) -> str:
    if "status" in stocks:
        return stocks["status"]
    return " ".join(
        f"{quote['symbol']} {quote['change']} Prozent, Schlusskurs {quote['close']} am {quote['day']}."
        if "close" in quote else f"{quote['symbol']}: keine Kursdaten verfügbar."
        for quote in stocks["quotes"]
    )


def _degrees(value: Any) -> str:
    return f"{_number(value):.0f}"


def _number(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Keine endliche Zahl")
    return number


def _text(value: Any) -> str:
    """Externe Texte auf eine kurze Zeile begrenzen. Das Template maskiert HTML."""
    return " ".join(str(value or "").split())[:100]
