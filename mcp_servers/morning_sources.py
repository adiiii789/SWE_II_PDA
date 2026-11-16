"""Quellen des Morning Assistant für den MCP-Server (pda_server.py): Wetter und Börse.

  forecast(location, days)   Open-Meteo, ohne Key: Tiefst-/Höchstwert, Wetterlage, Stundenverlauf
  stock_quotes(symbols)      Alpha Vantage: Schlusskurse und Veränderung zum Vortag. Key
                             PDA_ALPHAVANTAGE_KEY in der .env (⚙ Einstellungen → Zugangsdaten).
                             Der kostenlose Key erlaubt nur 25 Anfragen am Tag - eine je Kürzel.

Beide liefern Daten (dict) oder werfen SourceError mit einem Satz für den Nutzer. Als Werkzeuge
nutzen sie das Sprachmodell (get_weather_forecast, get_stock_quotes, Text aus *_text) und das
Briefing (watch_morning_weather, watch_stock_quotes, JSON); die Darstellung im Briefing macht
backend/assistant/skills/morning.py. Eigener Prozess: importiert backend nicht.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from time import sleep
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from mailer import ENV_FILE, read_env_file

WEATHER_SEARCH = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_FORECAST = "https://api.open-meteo.com/v1/forecast"
ALPHA_VANTAGE = "https://www.alphavantage.co/query"
KEY_NAME = "PDA_ALPHAVANTAGE_KEY"
MAX_DAYS = 7
MAX_SYMBOLS = 5
TREND_SESSIONS = 7
TIMEOUT_S = 5
STOCK_REQUEST_GAP_S = 1.2       # Alpha Vantage: höchstens eine Anfrage pro Sekunde
STORM_GUST_KMH = 62             # Untergrenze von Beaufort 8
WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")   # nicht %a: das hängt vom System-Locale ab
_SOURCE_ERRORS = (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError)
_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9.\-]{0,11}")

WEATHER_CONDITIONS = {
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
DAILY_CONDITIONS = {
    "sun": "Überwiegend sonnig", "partly-cloudy": "Sonne und Wolken",
    "cloud": "Überwiegend bewölkt", "rain": "Überwiegend regnerisch",
    "fog": "Überwiegend neblig", "snow": "Schneefall",
    "storm": "Gewitter", "wind": "Stürmische Böen",
}


class SourceError(Exception):
    """Eine Quelle hat nichts Brauchbares geliefert; der Text ist für den Nutzer."""


# --- Wetter ----------------------------------------------------------------------------------
def forecast(location: str, days: int = 1) -> dict[str, Any]:
    """{"location", "days": [{"date", "low", "high", "condition", "icon",
    "hours": [{"time": "HH:MM", "temp", "condition", "icon"}]}]} - Ortszeit des Orts.
    location: Stadt, optional mit Länderkürzel ("Berlin,DE")."""
    location = " ".join(str(location or "").split())[:100]
    if not location:
        raise SourceError("Wetterort angeben, z. B. Berlin,DE.")
    days = max(1, min(MAX_DAYS, int(days)))
    try:
        name, _, country = location.rpartition(",")
        query = {"name": location}
        if name.strip() and re.fullmatch(r"[A-Za-z]{2}", country.strip()):
            query = {"name": name.strip(), "countryCode": country.strip().upper()}
        places = _get_json(WEATHER_SEARCH, count=1, language="de", **query).get("results")
        if not places:
            raise SourceError("Open-Meteo hat den Ort nicht gefunden.")
        place = places[0]
        data = _get_json(
            WEATHER_FORECAST, latitude=place["latitude"], longitude=place["longitude"],
            hourly="temperature_2m,weather_code,is_day,wind_gusts_10m",
            daily="temperature_2m_min,temperature_2m_max,weather_code",
            timezone="auto", forecast_days=days, wind_speed_unit="kmh",
        )
        return {"location": _text(place["name"]), "days": _forecast_days(data)}
    except _SOURCE_ERRORS:
        raise SourceError("Open-Meteo ist gerade nicht verfügbar.") from None


def _forecast_days(data: dict[str, Any]) -> list[dict[str, Any]]:
    daily, hourly = data["daily"], data["hourly"]
    hours_by_day: dict[str, list[dict[str, Any]]] = {}
    daylight: dict[str, list[str]] = {}
    for stamp, temp, code, is_day, gusts in zip(
        hourly["time"], hourly["temperature_2m"], hourly["weather_code"],
        hourly["is_day"], hourly["wind_gusts_10m"], strict=True,
    ):
        time = dt.datetime.fromisoformat(stamp)
        condition, icon = condition_of(code, bool(is_day), gusts)
        day = time.date().isoformat()
        hours_by_day.setdefault(day, []).append({"time": f"{time:%H:%M}", "condition": condition, "icon": icon,
                                                 "temp": _number(temp) if temp is not None else None})
        if is_day and icon:
            daylight.setdefault(day, []).append(icon)
    result = []
    for index, day in enumerate(daily["time"]):
        if daylight.get(day):
            icon = Counter(daylight[day]).most_common(1)[0][0]
            condition = DAILY_CONDITIONS[icon]
        else:
            condition, icon = condition_of(daily["weather_code"][index], False, None)
        result.append({"date": dt.date.fromisoformat(day).isoformat(), "low": _number(daily["temperature_2m_min"][index]),
                       "high": _number(daily["temperature_2m_max"][index]), "condition": condition, "icon": icon,
                       "hours": hours_by_day.get(day, [])})
    if not result:
        raise ValueError("Keine Tage in der Vorhersage")
    return result


def condition_of(code: int | None, is_day: bool, gusts: float | None) -> tuple[str, str]:
    """WMO-Wettercode → (Text, Symbol); nachts Mond statt Sonne, starke Böen als "wind"."""
    condition, icon = WEATHER_CONDITIONS.get(code, ("Wetterlage unbekannt", ""))
    if not is_day and icon == "sun":
        condition, icon = "Klar", "moon"
    elif not is_day and icon == "partly-cloudy":
        icon = "partly-cloudy-night"
    if icon != "storm" and gusts is not None and _number(gusts) >= STORM_GUST_KMH:
        return (f"{condition}, stürmische Böen" if icon else "Stürmische Böen"), "wind"
    return condition, icon


def forecast_text(data: dict[str, Any]) -> str:
    """Kurzfassung fürs Sprachmodell; beim ersten Tag zusätzlich alle drei Stunden."""
    lines = [f"Wetter für {data['location']} (Open-Meteo):"]
    for index, day in enumerate(data["days"]):
        date = dt.date.fromisoformat(day["date"])
        lines.append(f"{WEEKDAYS[date.weekday()]} {date:%d.%m.}: {day['low']:.0f} bis {day['high']:.0f} °C, {day['condition']}")
        if index == 0 and day["hours"]:
            lines.append("  " + "; ".join(f"{hour['time']} {hour['temp']:.0f} °C {hour['condition']}"
                                          for hour in day["hours"][::3] if hour["temp"] is not None))
    return "\n".join(lines)


# --- Börse -----------------------------------------------------------------------------------
def stock_quotes(symbols: str | Iterable[str], until: dt.date | None = None,
                 environ: Mapping[str, str] = os.environ, env_file: Path = ENV_FILE,
                 wait: Callable[[float], None] = sleep) -> dict[str, Any]:
    """{"quotes": [{"symbol", "day", "close", "previous_close", "change_percent", "closes"} oder
    {"symbol", "error"}]} - je Kürzel der letzte Schlusskurs bis einschließlich until (Standard: heute)
    und die Schlusskurse der letzten TREND_SESSIONS Handelstage, älteste zuerst."""
    if isinstance(symbols, str):
        symbols = symbols.split(",")
    wanted = list(dict.fromkeys(symbol.strip().upper() for symbol in symbols if symbol.strip()))
    if not wanted:
        raise SourceError("Aktienkürzel angeben, z. B. AAPL, MSFT.")
    invalid = [symbol for symbol in wanted if not _SYMBOL.fullmatch(symbol)]
    if invalid:
        raise SourceError(f"Ungültiges Aktienkürzel: {_text(invalid[0])}")
    key = alpha_vantage_key(environ, env_file)
    if not key:
        raise SourceError("Alpha-Vantage-Schlüssel hinterlegen (⚙ Einstellungen → Zugangsdaten).")
    until = until or dt.date.today()
    quotes = []
    for symbol in wanted[:MAX_SYMBOLS]:
        if quotes:
            wait(STOCK_REQUEST_GAP_S)
        quotes.append(_quote(symbol, until.isoformat(), key))
    return {"quotes": quotes}


def alpha_vantage_key(environ: Mapping[str, str] = os.environ, env_file: Path = ENV_FILE) -> str:
    """Wie backend/api_keys.py: eine nicht leere Umgebungsvariable, sonst die .env."""
    return environ.get(KEY_NAME, "").strip() or read_env_file(env_file).get(KEY_NAME, "")


def _quote(symbol: str, until: str, key: str) -> dict[str, Any]:
    try:
        data = _get_json(ALPHA_VANTAGE, function="TIME_SERIES_DAILY", symbol=symbol, outputsize="compact", apikey=key)
        if "Time Series (Daily)" not in data:   # z. B. {"Information": "... rate limit ..."}
            return {"symbol": symbol, "error": "keine Kursdaten (Kürzel unbekannt oder Tageslimit erreicht)"}
        series = data["Time Series (Daily)"]
        days = sorted((day for day in series if day <= until), reverse=True)[:TREND_SESSIONS]
        last, previous = days[:2]
        close, previous_close = _number(series[last]["4. close"]), _number(series[previous]["4. close"])
        if previous_close <= 0 or close <= 0:
            raise ValueError("Ungültiger Schlusskurs")
        closes = []
        for day in reversed(days):
            try:
                value = _number(series[day]["4. close"])
            except _SOURCE_ERRORS:
                continue
            if value > 0:
                closes.append(value)
        return {"symbol": symbol, "day": last, "close": close, "previous_close": previous_close,
                "change_percent": round((close / previous_close - 1) * 100, 2), "closes": closes}
    except _SOURCE_ERRORS:
        return {"symbol": symbol, "error": "keine Kursdaten verfügbar"}


def quotes_text(data: dict[str, Any]) -> str:
    """Kurzfassung fürs Sprachmodell."""
    lines = ["Schlusskurse (Alpha Vantage):"]
    for quote in data["quotes"]:
        if "close" not in quote:
            lines.append(f"{quote['symbol']}: {quote['error']}")
            continue
        day = dt.date.fromisoformat(quote["day"])
        lines.append(f"{quote['symbol']}: {quote['close']:.2f} am {day:%d.%m.%Y}, "
                     f"{quote['change_percent']:+.2f} % zum vorherigen Handelstag")
    return "\n".join(lines)


def _get_json(url: str, **params: Any) -> Any:
    with urlopen(f"{url}?{urlencode(params)}", timeout=TIMEOUT_S) as response:
        return json.load(response)


def _number(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Keine endliche Zahl")
    return number


def _text(value: Any) -> str:
    """Externe Texte auf eine kurze Zeile begrenzen."""
    return " ".join(str(value or "").split())[:100]
