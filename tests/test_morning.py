"""Morning Assistant über den Wächter und die Benachrichtigung, mit simulierten Quellen."""
import datetime as dt
import io
import json
from unittest import mock
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from backend import api, config, watcher as watcher_module
from backend.assistant.skills import morning
from backend.assistant.skills.morning_music import song_for
from backend.assistant.tools import ToolResult
from backend.events import ASSISTANT_MESSAGE, PROACTIVE_NOTICE
from backend.watcher import NOTIFIED
from tests.assistant.test_gemini_assistant import FIXED_NOW, FakeModel, make
from tests.test_watcher import Harness, event

MONDAY = dt.datetime(2026, 11, 9, 7)
OPTIONS = {"weather_location": "Berlin,DE", "stock_symbols": "aapl, MSFT, AAPL"}


def harness(now=MONDAY, **options):
    return Harness(now=now, morning={"enabled": True, **options},
                   mail={"enabled": False}, tasks={"enabled": False}, calendar={"enabled": False})


def test_at_seven_once_per_day_and_persisted_across_restart():
    watcher = harness(MONDAY.replace(hour=6, minute=59))
    assert watcher.check() == 0
    assert watcher.calls == []

    watcher.now = MONDAY
    assert watcher.check() == 1
    assert watcher.calls == [("watch_calendar_events", {"days": 1})]
    occasion, delivery = watcher.deliveries[0]
    assert occasion.title == "Guten Morgen"
    assert delivery == {"formulate": False, "speak": False, "display": "popup"}

    restarted = harness(MONDAY.replace(hour=9))
    restarted.state.set(NOTIFIED, watcher.state.get(NOTIFIED))
    assert restarted.check() == 0
    assert restarted.calls == []
    restarted.now += dt.timedelta(days=1)
    assert restarted.check() == 1


def test_calendar_today_and_clickable_song_reach_chat():
    watcher = harness(MONDAY.replace(hour=10))
    watcher.settings.store_validated(watcher.settings.validated({"general": {"speak": True}}))
    watcher.events = [
        event(title="Morgen", day="2026-11-10"),
        event(title="Teamrunde <privat>", clock="11:00"),
        event(title="Abgelehnt", response="declined"),
        event(title="Konferenz", day="2026-11-08", all_day=True, end="2026-11-10"),
    ]
    with mock.patch.object(api.events, "publish") as publish, mock.patch.object(api, "_speech_output") as speech:
        watcher.watcher.deliver = api._deliver_proactive
        assert watcher.check() == 1
    assert [call.args[0] for call in publish.call_args_list] == [ASSISTANT_MESSAGE, PROACTIVE_NOTICE]
    message = publish.call_args_list[0].args[1]
    assert message["proactive"] is True
    assert message["view_button"] == "Briefing anzeigen"
    assert "Teamrunde" not in message["text"]
    assert "[Auf Spotify anhören](https://open.spotify.com/track/" in message["text"]
    html = message["html"]
    assert html.index("Ganztägig") < html.index("Konferenz") < html.index("11:00 Uhr")
    assert "Teamrunde &lt;privat&gt;" in html
    assert "Uhr Morgen" not in html
    assert "Abgelehnt" not in html
    assert publish.call_args_list[1].args[1]["text"] == "Dein Tagesüberblick ist bereit."
    assert "11:00 Uhr Teamrunde" in speech.return_value.speak.call_args.args[0]


def test_selected_genre_changes_song_and_direct_spotify_link():
    options = {"weather_location": "", "stock_symbols": ""}
    pop = morning.compose(MONDAY, {**options, "music_genre": "pop"}, [])
    rock = morning.compose(MONDAY, {**options, "music_genre": "rock"}, [])
    assert pop.view.data["song"] != rock.view.data["song"]
    title, artist, url, cover = song_for(MONDAY.date(), "rock")
    assert rock.view.data["song"] == {"title": title, "artist": artist, "url": url, "cover": cover}
    assert cover.startswith("https://image-cdn-") and ".spotifycdn.com/image/" in cover
    html = api.renderer().render(rock.view)
    assert f'src="{cover}"' in html
    assert f'href="{url}"' in html
    assert rock.chat_text.endswith(f"({url})")
    assert song_for(MONDAY.date() + dt.timedelta(days=1), "rock")[2] != url


def test_manual_briefing_uses_calendar_without_sending_a_notification():
    model = FakeModel()
    tools = mock.Mock()
    calendar = [event(title="Teamrunde", day=FIXED_NOW.date().isoformat())]
    tools.call_tool.return_value = ToolResult(json.dumps(calendar))
    assistant = make(model, tools)
    with mock.patch.object(api, "_assistant", return_value=assistant), mock.patch.object(api.events, "publish") as publish:
        assert "morning briefing" in api.chat("hilfe")["html"]
        for _ in range(2):
            message = api.chat("  Morning Briefing  ")
            assert "Teamrunde" in message["html"]
            assert "https://open.spotify.com/track/" in message["text"]
            assert message["view_button"] == "Briefing anzeigen"
            assert "proactive" not in message
        publish.assert_not_called()
    assert tools.call_tool.call_args_list == [mock.call("watch_calendar_events", {"days": 1})] * 2
    assert model.calls == []


def test_watcher_checks_at_briefing_time_between_regular_checks():
    watcher = harness().watcher
    watcher.clock = mock.Mock(side_effect=[MONDAY - dt.timedelta(seconds=15), MONDAY])
    watcher.check = mock.Mock()
    watcher._stop = mock.Mock()
    watcher._stop.wait.side_effect = [False, False, True]
    with mock.patch.object(watcher_module.time, "monotonic", side_effect=[0, 20, 21, 35, 36]):
        watcher._run()
    assert watcher.check.call_count == 2


def test_weather_location_local_day_and_stock_previous_trading_day(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_DATA_DIR", tmp_path)
    wait = mock.Mock()
    monkeypatch.setattr(morning, "sleep", wait)
    for provider in ("openweather", "alphavantage"):
        (tmp_path / f"{provider}-api-key.txt").write_text("test-key\n", encoding="utf-8")
    requests = []

    def respond(url, *, timeout):
        request = urlsplit(url)
        params = parse_qs(request.query)
        requests.append(params)
        assert timeout > 0
        if request.path == "/geo/1.0/direct":
            data = [{"name": "Berlin", "lat": 52.52, "lon": 13.405}]
        elif request.path == "/data/2.5/forecast":
            start = dt.datetime(2026, 11, 9, 8, tzinfo=dt.timezone.utc)
            data = {"city": {"timezone": 3600}, "list": [
                {"dt": (start + dt.timedelta(hours=offset)).timestamp(), "main": {"temp": temperature},
                 "weather": [{"description": "bewölkt", "icon": "04d"}]}
                for offset, temperature in ((0, 6), (3, 11), (16, 99))
            ]}
        elif params["symbol"] == ["AAPL"]:
            data = {"Time Series (Daily)": {
                "2026-11-05": {"4. close": "100"},
                "2026-11-06": {"4. close": "102"},
                "2026-11-09": {"4. close": "300"},
            }}
        else:
            data = {"Information": "API limit"}
        return io.BytesIO(json.dumps(data).encode())

    monkeypatch.setattr(morning, "urlopen", respond)
    now = MONDAY.replace(tzinfo=dt.timezone.utc)
    view = morning.compose(now, OPTIONS, []).view
    assert view.data["weather"] == {"location": "Berlin", "low": "6", "high": "11",
                                   "condition": "bewölkt", "time": "12:00", "icon": "cloud"}
    assert view.data["stocks"]["quotes"] == [
        {"symbol": "AAPL", "close": "102,00", "change": "+2,00", "direction": "up", "day": "06.11.",
         "trend": {"points": "2.0,22.0 62.0,2.0", "last_y": "2.0", "sessions": 2}},
        {"symbol": "MSFT"},
    ]
    html = api.renderer().render(view)
    assert 'class="weather-icon cloud"' in html
    assert 'aria-label="Kursverlauf über 2 Handelstage"' in html
    assert requests[0]["q"] == ["Berlin,DE"]
    assert requests[1]["units"] == ["metric"]
    assert [request["symbol"] for request in requests[2:]] == [["AAPL"], ["MSFT"]]
    wait.assert_called_once_with(morning._STOCK_REQUEST_GAP_S)


def test_stock_trend_uses_seven_chronological_closes_ending_yesterday(monkeypatch):
    yesterday = MONDAY.date() - dt.timedelta(days=1)
    closes = {(yesterday - dt.timedelta(days=index)).isoformat(): {"4. close": str(100 - index)}
              for index in reversed(range(-1, 9))}
    monkeypatch.setattr(morning, "_get_json", mock.Mock(return_value={"Time Series (Daily)": closes}))
    quote = morning._stock("AAPL", yesterday.isoformat(), "test-key")
    assert quote["close"] == "100,00"
    assert quote["trend"]["sessions"] == 7
    points = quote["trend"]["points"].split()
    assert points[0] == "2.0,22.0" and points[-1] == "62.0,2.0"


def test_failed_sources_still_deliver_and_respect_quiet_time(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_DATA_DIR", tmp_path)
    (tmp_path / "openweather-api-key.txt").write_text("test-key", encoding="utf-8")
    monkeypatch.setattr(morning, "urlopen", mock.Mock(side_effect=TimeoutError))
    watcher = harness(MONDAY.replace(hour=6), time="06:00", **OPTIONS)
    watcher.errors["watch_calendar_events"] = "Google nicht erreichbar"
    assert watcher.check() == 0
    watcher.now = MONDAY
    assert watcher.check() == 1
    assert "Google Kalender ist gerade nicht verfügbar" in watcher.texts[0]
    assert "OpenWeather ist gerade nicht verfügbar" in watcher.texts[0]
    assert "Alpha-Vantage-Schlüssel hinterlegen" in watcher.texts[0]
    assert "Songvorschlag" in watcher.texts[0]


def test_rejected_weather_key_gets_specific_message(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "APP_DATA_DIR", tmp_path)
    (tmp_path / "openweather-api-key.txt").write_text("test-key", encoding="utf-8")
    error = HTTPError("https://example.test", 401, "Unauthorized", {}, io.BytesIO())
    monkeypatch.setattr(morning, "urlopen", mock.Mock(side_effect=error))
    assert "akzeptiert den hinterlegten Schlüssel derzeit nicht" in morning.compose(MONDAY, OPTIONS, []).fallback
