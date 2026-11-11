"""Baut das tägliche Morning-Briefing aus Kalender, Wetter, Aktien und Musik."""
from __future__ import annotations

import datetime as dt
import json
import math
import re
from collections import Counter
from collections.abc import Callable
from time import sleep
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from backend import config
from backend.assistant.skills.morning_music import song_for
from backend.assistant.tools import ToolResult
from backend.proactive import Occasion
from backend.views import TemplateView

_WEATHER_SEARCH = "https://geocoding-api.open-meteo.com/v1/search"
_WEATHER_FORECAST = "https://api.open-meteo.com/v1/forecast"
_ALPHA_VANTAGE = "https://www.alphavantage.co/query"
_MAX_EVENTS = 5
_MAX_SYMBOLS = 5
_TREND_SESSIONS = 7
_TIMEOUT_S = 5
_STOCK_REQUEST_GAP_S = 1.2
_SOURCE_ERRORS = (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError)
_WEEKDAYS = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
_STORM_GUST_KMH = 62  # Untergrenze von Beaufort 8
_WEATHER_CONDITIONS = {
    0: ("Sonnig", "sun"), 1: ("Meist sonnig", "sun"),
    2: ("Teilweise bewölkt", "partly-cloudy"), 3: ("Bedeckt", "cloud"),
    **dict.fromkeys((45, 48), ("Nebel", "fog")),
    **dict.fromkeys((51, 53, 55), ("Nieselregen", "rain")),
    **dict.fromkeys((56, 57, 66, 67), ("Gefrierender Regen", "rain")),
    **dict.fromkeys((61, 63, 65), ("Regen", "rain")),
    **dict.fromkeys((71, 73, 75, 77), ("Schneefall", "snow")),
    **dict.fromkeys((80, 81, 82), ("Regenschauer", "rain")),
    **dict.fromkeys((85, 86), ("Schneeschauer", "snow")),
    95: ("Gewitter", "storm"),
    **dict.fromkeys((96, 99), ("Gewitter mit Hagel", "storm")),
}
_DAILY_CONDITIONS = {
    "sun": "Überwiegend sonnig", "partly-cloudy": "Sonne und Wolken",
    "cloud": "Überwiegend bewölkt", "rain": "Überwiegend regnerisch",
    "fog": "Überwiegend neblig", "snow": "Schneefall",
    "storm": "Gewitter", "wind": "Stürmische Böen",
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
    weather = _weather(options["weather_location"])
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


def _weather(location: str) -> dict[str, Any]:
    if not location:
        return {"status": "Wetterort in den Einstellungen eintragen."}
    try:
        name, _, country = location.rpartition(",")
        query = {"name": location}
        if name.strip() and re.fullmatch(r"[A-Za-z]{2}", country.strip()):
            query = {"name": name.strip(), "countryCode": country.strip().upper()}
        places = _get_json(_WEATHER_SEARCH, count=1, language="de", **query).get("results")
        if not places:
            return {"status": "Open-Meteo hat den Ort nicht gefunden."}
        place = places[0]
        forecast = _get_json(
            _WEATHER_FORECAST, latitude=place["latitude"], longitude=place["longitude"],
            hourly="temperature_2m,weather_code,is_day,wind_gusts_10m",
            daily="temperature_2m_min,temperature_2m_max,weather_code",
            timezone="auto", forecast_days=1, wind_speed_unit="kmh",
        )
        return _weather_day(_text(place["name"]), forecast)
    except _SOURCE_ERRORS:
        return {"status": "Open-Meteo ist gerade nicht verfügbar."}


def _weather_day(location: str, forecast: dict[str, Any]) -> dict[str, Any]:
    daily = forecast["daily"]
    today = dt.date.fromisoformat(daily["time"][0])
    hourly = forecast["hourly"]
    hours = []
    daylight_icons = []
    for stamp, temp, code, is_day, gusts in zip(
        hourly["time"], hourly["temperature_2m"], hourly["weather_code"],
        hourly["is_day"], hourly["wind_gusts_10m"], strict=True,
    ):
        time = dt.datetime.fromisoformat(stamp)
        if time.date() != today:
            continue
        condition, icon = _weather_condition(code, bool(is_day), gusts)
        hours.append({"time": f"{time:%H:%M}", "temp": f"{_number(temp):.0f}" if temp is not None else None,
                      "condition": condition, "icon": icon})
        if is_day and icon:
            daylight_icons.append(icon)
    if daylight_icons:
        icon = Counter(daylight_icons).most_common(1)[0][0]
        condition = _DAILY_CONDITIONS[icon]
    else:
        condition, icon = _weather_condition(daily["weather_code"][0], False, None)
    return {"location": location, "low": f"{_number(daily['temperature_2m_min'][0]):.0f}",
            "high": f"{_number(daily['temperature_2m_max'][0]):.0f}", "condition": condition,
            "icon": icon, "hours": hours}


def _weather_condition(code: int | None, is_day: bool, gusts: float | None) -> tuple[str, str]:
    condition, icon = _WEATHER_CONDITIONS.get(code, ("Wetterlage unbekannt", ""))
    if not is_day and icon == "sun":
        condition, icon = "Klar", "moon"
    elif not is_day and icon == "partly-cloudy":
        icon = "partly-cloudy-night"
    if icon != "storm" and gusts is not None and _number(gusts) >= _STORM_GUST_KMH:
        return (f"{condition}, stürmische Böen" if icon else "Stürmische Böen"), "wind"
    return condition, icon


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
