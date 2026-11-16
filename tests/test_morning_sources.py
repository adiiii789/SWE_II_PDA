"""Quellen des Morning Assistant im MCP-Server (mcp_servers/morning_sources.py), mit simuliertem Netz."""
import datetime as dt
import io
import json
import sys
from unittest import mock
from urllib.parse import parse_qs, urlsplit

import pytest

from backend import config

sys.path.insert(0, str(config.ROOT_DIR / "mcp_servers"))   # wie beim Start als Skript
import morning_sources  # noqa: E402

DAY = dt.date(2026, 11, 9)


def open_meteo(url, *, timeout):
    """Berlin, 24 Stunden plus eine des nächsten Tags; morgens Mond, mittags Regen und Gewitter, eine Sturmböe."""
    request = urlsplit(url)
    assert timeout > 0
    if request.path == "/v1/search":
        data = {"results": [{"name": "Berlin", "latitude": 52.52, "longitude": 13.405}]}
    else:
        days = int(parse_qs(request.query)["forecast_days"][0])
        codes = [0] * 8 + [3] * 10 + [0] * 7
        codes[9], codes[13], codes[14], codes[15] = 0, 61, 95, 2
        gusts = [12] * 25
        gusts[16] = 71
        data = {
            "daily": {"time": ["2026-11-09", "2026-11-10"][:days], "temperature_2m_min": [6, 2][:days],
                      "temperature_2m_max": [11, 8][:days], "weather_code": [95, 71][:days]},
            "hourly": {
                "time": [f"2026-11-09T{hour:02d}:00" for hour in range(24)] + ["2026-11-10T00:00"],
                "temperature_2m": [6] * 12 + [11] * 12 + [3],
                "weather_code": codes, "is_day": [0] * 8 + [1] * 10 + [0] * 7, "wind_gusts_10m": gusts,
            },
        }
    return io.BytesIO(json.dumps(data).encode())


def test_forecast_per_day_with_local_hours(monkeypatch):
    requests = []
    monkeypatch.setattr(morning_sources, "urlopen", lambda url, timeout: requests.append(url) or open_meteo(url, timeout=timeout))
    data = morning_sources.forecast("Berlin,DE", days=2)
    assert data["location"] == "Berlin"
    today, tomorrow = data["days"]
    assert (today["date"], today["low"], today["high"]) == ("2026-11-09", 6, 11)
    assert (today["condition"], today["icon"]) == ("Überwiegend bewölkt", "cloud")   # häufigstes Symbol am Tag
    assert [today["hours"][hour]["icon"] for hour in (0, 9, 13, 14, 15, 16)] == [
        "moon", "sun", "rain", "storm", "partly-cloudy", "wind"]
    assert "stürmische Böen" in today["hours"][16]["condition"]
    assert len(today["hours"]) == 24
    assert (tomorrow["condition"], tomorrow["icon"]) == ("Schneefall", "snow")   # kein Tageslicht: Tagescode
    search, forecast = (parse_qs(urlsplit(url).query) for url in requests)
    assert search["name"] == ["Berlin"] and search["countryCode"] == ["DE"]
    assert forecast["timezone"] == ["auto"] and forecast["forecast_days"] == ["2"]
    text = morning_sources.forecast_text(data)
    assert text.splitlines()[:2] == ["Wetter für Berlin (Open-Meteo):", "Mo 09.11.: 6 bis 11 °C, Überwiegend bewölkt"]
    assert "00:00 6 °C Klar; 03:00 6 °C Klar" in text


def test_forecast_errors_are_sentences_for_the_user(monkeypatch):
    query = mock.Mock(return_value={})
    monkeypatch.setattr(morning_sources, "_get_json", query)
    with pytest.raises(morning_sources.SourceError, match="Ort nicht gefunden"):
        morning_sources.forecast("Unbekannt")
    query.assert_called_once_with(morning_sources.WEATHER_SEARCH, count=1, language="de", name="Unbekannt")
    with pytest.raises(morning_sources.SourceError, match="Wetterort angeben"):
        morning_sources.forecast("  ")
    assert query.call_count == 1   # ohne Ort keine Anfrage


def test_forecast_offline(monkeypatch):
    monkeypatch.setattr(morning_sources, "urlopen", mock.Mock(side_effect=TimeoutError))
    with pytest.raises(morning_sources.SourceError, match="Open-Meteo ist gerade nicht verfügbar"):
        morning_sources.forecast("Berlin")


def alpha_vantage(url, *, timeout):
    params = parse_qs(urlsplit(url).query)
    assert params["apikey"] == ["test-key"] and timeout > 0
    if params["symbol"] == ["AAPL"]:
        data = {"Time Series (Daily)": {"2026-11-05": {"4. close": "100"}, "2026-11-06": {"4. close": "102"},
                                        "2026-11-09": {"4. close": "300"}}}   # heute zählt nicht (until)
    else:
        data = {"Information": "API limit"}
    return io.BytesIO(json.dumps(data).encode())


def test_stock_quotes_until_a_day_with_gap_between_requests(monkeypatch):
    monkeypatch.setattr(morning_sources, "urlopen", alpha_vantage)
    wait = mock.Mock()
    data = morning_sources.stock_quotes("aapl, MSFT, AAPL", DAY - dt.timedelta(days=1),
                                        environ={"PDA_ALPHAVANTAGE_KEY": "test-key"}, wait=wait)
    assert data["quotes"] == [
        {"symbol": "AAPL", "day": "2026-11-06", "close": 102.0, "previous_close": 100.0, "change_percent": 2.0,
         "closes": [100.0, 102.0]},
        {"symbol": "MSFT", "error": "keine Kursdaten (Kürzel unbekannt oder Tageslimit erreicht)"},
    ]
    wait.assert_called_once_with(morning_sources.STOCK_REQUEST_GAP_S)
    assert morning_sources.quotes_text(data).splitlines() == [
        "Schlusskurse (Alpha Vantage):", "AAPL: 102.00 am 06.11.2026, +2.00 % zum vorherigen Handelstag",
        "MSFT: keine Kursdaten (Kürzel unbekannt oder Tageslimit erreicht)"]


def test_seven_chronological_closes(monkeypatch):
    until = DAY - dt.timedelta(days=1)
    series = {(until - dt.timedelta(days=index)).isoformat(): {"4. close": str(100 - index)}
              for index in range(-1, 9)}   # auch einer nach until
    monkeypatch.setattr(morning_sources, "_get_json", mock.Mock(return_value={"Time Series (Daily)": series}))
    quote = morning_sources._quote("AAPL", until.isoformat(), "test-key")
    assert quote["close"] == 100.0 and quote["day"] == until.isoformat()
    assert quote["closes"] == [94.0, 95.0, 96.0, 97.0, 98.0, 99.0, 100.0]


def test_key_from_env_file_and_checks(tmp_path):
    env = tmp_path / ".env"
    with pytest.raises(morning_sources.SourceError, match="Alpha-Vantage-Schlüssel hinterlegen"):
        morning_sources.stock_quotes("AAPL", environ={}, env_file=env)
    env.write_text("PDA_ALPHAVANTAGE_KEY=aus-datei\n", encoding="utf-8")
    assert morning_sources.alpha_vantage_key({}, env) == "aus-datei"
    assert morning_sources.alpha_vantage_key({"PDA_ALPHAVANTAGE_KEY": "x"}, env) == "x"
    assert morning_sources.alpha_vantage_key({"PDA_ALPHAVANTAGE_KEY": " "}, env) == "aus-datei"
    with pytest.raises(morning_sources.SourceError, match="Aktienkürzel angeben"):
        morning_sources.stock_quotes(" , ", environ={}, env_file=env)
    with pytest.raises(morning_sources.SourceError, match="Ungültiges Aktienkürzel"):
        morning_sources.stock_quotes("AAPL&function=X", environ={}, env_file=env)
