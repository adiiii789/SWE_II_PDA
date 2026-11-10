"""Baut das tägliche Morning-Briefing aus Kalender, Wetter, Aktien und Musik."""
from __future__ import annotations

import datetime as dt
import json
import math
from collections.abc import Callable
from time import sleep
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

from backend import config
from backend.assistant.skills.morning_music import song_for
from backend.assistant.tools import ToolResult
from backend.proactive import Occasion
from backend.views import TemplateView

_OPENWEATHER = "https://api.openweathermap.org"
_ALPHA_VANTAGE = "https://www.alphavantage.co/query"
_MAX_EVENTS = 5
_MAX_SYMBOLS = 5
_TREND_SESSIONS = 7
_TIMEOUT_S = 5
_STOCK_REQUEST_GAP_S = 1.2
_SOURCE_ERRORS = (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError)
_WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
_WEATHER_ICONS = {
    "01": "sun", "01n": "moon", "02": "partly-cloudy", "02n": "cloud",
    "03": "cloud", "04": "cloud", "09": "rain", "10": "rain",
    "11": "storm", "13": "snow", "50": "fog",
}


def prepare(now: dt.datetime, options: dict[str, Any],
            call_tool: Callable[[str, dict[str, Any]], ToolResult] | None = None) -> Occasion:
    """Lädt das Briefing für den Chat und den Wächter mit denselben Quellen."""
    events = None
    if call_tool is not None:
        try:
            result = call_tool("watch_calendar_events", {"days": 1})
            if not result.is_error:
                events = json.loads(result.content)
        except Exception:  # noqa: BLE001  # Wetter, Börse und Musik bleiben verfügbar
            pass
    return compose(now, options, events)


def compose(now: dt.datetime, options: dict[str, Any], events: list[dict] | None) -> Occasion:
    """Tagesübersicht, kompakte Chat-Nachricht und Text zum Vorlesen."""
    day = now.date()
    title, artist, spotify_url, cover = song_for(day, options.get("music_genre", "mixed"))
    calendar = _calendar(events, day)
    weather = _weather(options["weather_location"], now)
    weather.setdefault("location", options["weather_location"])
    stocks = _stocks(options["stock_symbols"], day)
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


def _weather(location: str, now: dt.datetime) -> dict[str, str]:
    if not location:
        return {"status": "Wetterort in den Einstellungen eintragen."}
    try:
        key = _read_key("openweather")
        if not key:
            return {"status": "OpenWeather-Schlüssel hinterlegen."}
        places = _get_json(f"{_OPENWEATHER}/geo/1.0/direct", q=location, limit=1, appid=key)
        if not places:
            return {"status": "OpenWeather hat den Ort nicht gefunden."}
        place = places[0]
        forecast = _get_json(f"{_OPENWEATHER}/data/2.5/forecast", lat=place["lat"], lon=place["lon"],
                             appid=key, units="metric", lang="de")
        zone = dt.timezone(dt.timedelta(seconds=forecast["city"]["timezone"]))
        local_day = now.astimezone(zone).date()
        hours = [(dt.datetime.fromtimestamp(item["dt"], zone), item) for item in forecast["list"]]
        today = [(hour, item) for hour, item in hours if hour.date() == local_day]
        if not today:
            return {"status": "Keine Wettervorhersage mehr für heute verfügbar."}
        temps = [_number(item["main"]["temp"]) for _, item in today]
        hour, midday = min(today, key=lambda point: abs(point[0].hour * 60 + point[0].minute - 13 * 60))
        condition = midday["weather"][0]
        code = _text(condition.get("icon"))
        return {"location": _text(place["name"]), "low": f"{min(temps):.0f}", "high": f"{max(temps):.0f}",
                "condition": _text(condition["description"]), "time": f"{hour:%H:%M}",
                "icon": _WEATHER_ICONS.get(code, _WEATHER_ICONS.get(code[:2], ""))}
    except HTTPError as error:
        with error:
            if error.code == 401:
                return {"status": "OpenWeather akzeptiert den hinterlegten Schlüssel derzeit nicht."}
        return {"status": "OpenWeather ist gerade nicht verfügbar."}
    except _SOURCE_ERRORS:
        return {"status": "OpenWeather ist gerade nicht verfügbar."}


def _stocks(watchlist: str, day: dt.date) -> dict[str, Any]:
    symbols = list(dict.fromkeys(symbol.strip().upper() for symbol in watchlist.split(",") if symbol.strip()))
    if not symbols:
        return {"status": "Aktienkürzel in den Einstellungen eintragen."}
    try:
        key = _read_key("alphavantage")
    except (OSError, ValueError):
        return {"status": "Alpha-Vantage-Schlüssel ist nicht lesbar."}
    if not key:
        return {"status": "Alpha-Vantage-Schlüssel hinterlegen."}
    yesterday = (day - dt.timedelta(days=1)).isoformat()
    recaps = []
    for symbol in symbols[:_MAX_SYMBOLS]:
        if recaps:
            sleep(_STOCK_REQUEST_GAP_S)
        recaps.append(_stock(symbol, yesterday, key))
    trend_sessions = max((quote["trend"]["sessions"] for quote in recaps if "trend" in quote), default=0)
    return {"quotes": recaps, "trend_sessions": trend_sessions}


def _stock(symbol: str, yesterday: str, key: str) -> dict[str, Any]:
    label = _text(symbol)
    try:
        data = _get_json(_ALPHA_VANTAGE, function="TIME_SERIES_DAILY", symbol=symbol,
                         outputsize="compact", apikey=key)
        series = data["Time Series (Daily)"]
        days = sorted((date for date in series if date <= yesterday), reverse=True)[:_TREND_SESSIONS]
        last, previous = days[:2]
        close = _number(series[last]["4. close"])
        previous_close = _number(series[previous]["4. close"])
        if previous_close <= 0 or close <= 0:
            raise ValueError("Ungültiger Schlusskurs")
        percent = round((close / previous_close - 1) * 100, 2)
        return {"symbol": label, "close": f"{close:.2f}".replace(".", ","),
                "change": f"{percent:+.2f}".replace(".", ",") if percent else "0,00",
                "direction": "up" if percent > 0 else "down" if percent < 0 else "flat",
                "day": f"{dt.date.fromisoformat(last):%d.%m.}",
                "trend": _stock_trend(series, days)}
    except _SOURCE_ERRORS:
        return {"symbol": label}


def _stock_trend(series: dict[str, Any], days: list[str]) -> dict[str, Any]:
    closes = []
    for day in reversed(days):
        try:
            close = _number(series[day]["4. close"])
        except _SOURCE_ERRORS:
            continue
        if close > 0:
            closes.append(close)

    low, high = min(closes), max(closes)
    # Die letzten beiden Kurse sind bereits geprüft. Die Endpunkte liegen bei x=2 und x=62.
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


def _weather_text(weather: dict[str, str]) -> str:
    if "status" in weather:
        return weather["status"]
    return (f"{weather['location']}, {weather['low']} bis {weather['high']} Grad, "
            f"gegen {weather['time']} Uhr {weather['condition']}.")


def _stock_text(stocks: dict[str, Any]) -> str:
    if "status" in stocks:
        return stocks["status"]
    return " ".join(
        f"{quote['symbol']} {quote['change']} Prozent, Schlusskurs {quote['close']} am {quote['day']}."
        if "close" in quote else f"{quote['symbol']}: keine Kursdaten verfügbar."
        for quote in stocks["quotes"]
    )


def _get_json(url: str, **params: Any) -> Any:
    with urlopen(f"{url}?{urlencode(params)}", timeout=_TIMEOUT_S) as response:
        return json.load(response)


def _read_key(provider: str) -> str:
    try:
        return (config.APP_DATA_DIR / f"{provider}-api-key.txt").read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def _number(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Keine endliche Zahl")
    return number


def _text(value: str) -> str:
    """Externe Texte auf eine kurze Zeile begrenzen. Das Template maskiert HTML."""
    return " ".join(str(value or "").split())[:100]
