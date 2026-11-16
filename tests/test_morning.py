"""Morning Assistant über den Wächter und die Benachrichtigung, mit simulierten Quellen."""
import datetime as dt
import io
import json
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from backend import api, watcher as watcher_module
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


def mcp_tools(monkeypatch, events=()):
    """call_tool wie im Wächter, aber mit den echten Quellen aus mcp_servers/morning_sources.py
    (wie pda_server.py: watch_morning_weather, watch_stock_quotes) und simuliertem Netz."""
    from tests.test_morning_sources import alpha_vantage, morning_sources, open_meteo

    monkeypatch.setattr(morning_sources, "urlopen", lambda url, timeout: (
        alpha_vantage if "alphavantage" in url else open_meteo)(url, timeout=timeout))
    monkeypatch.setenv("PDA_ALPHAVANTAGE_KEY", "test-key")
    calls = []

    def call_tool(name, arguments):
        calls.append((name, arguments))
        try:
            if name == "watch_morning_weather":
                return ToolResult(json.dumps(morning_sources.forecast(arguments["location"], 1)))
            if name == "watch_stock_quotes":
                until = dt.date.fromisoformat(arguments["until"])
                return ToolResult(json.dumps(morning_sources.stock_quotes(arguments["symbols"], until, wait=mock.Mock())))
        except morning_sources.SourceError as error:
            return ToolResult(str(error), is_error=True)
        return ToolResult(json.dumps(list(events)))

    return call_tool, calls


def test_weather_location_local_day_and_stock_previous_trading_day(monkeypatch):
    call_tool, calls = mcp_tools(monkeypatch)
    now = MONDAY.replace(tzinfo=dt.timezone.utc)
    view = morning.prepare(now, OPTIONS, call_tool).view
    weather = view.data["weather"]
    assert (weather["location"], weather["low"], weather["high"]) == ("Berlin", "6", "11")
    assert (weather["condition"], weather["icon"]) == ("Überwiegend bewölkt", "cloud")
    hours = weather["hours"]
    assert [hour["time"] for hour in hours] == [f"{hour:02d}:00" for hour in range(24)]
    assert [hours[hour]["icon"] for hour in (0, 9, 13, 14, 15, 16)] == [
        "moon", "sun", "rain", "storm", "partly-cloudy", "wind",
    ]
    assert hours[16]["temp"] == "11" and "stürmische Böen" in hours[16]["condition"]
    assert view.data["stocks"]["quotes"] == [
        {"symbol": "AAPL", "close": "102,00", "change": "+2,00", "direction": "up", "day": "06.11.",
         "trend": {"points": "2.0,22.0 62.0,2.0", "last_y": "2.0", "sessions": 2}},
        {"symbol": "MSFT"},
    ]
    html = api.renderer().render(view)
    assert 'class="weather-icon cloud"' in html
    assert "Stundenverlauf" in html and 'href="https://open-meteo.com/"' in html
    assert 'aria-label="Kursverlauf über 2 Handelstage"' in html
    assert calls == [("watch_calendar_events", {"days": 1}),
                     ("watch_morning_weather", {"location": "Berlin,DE"}),
                     ("watch_stock_quotes", {"symbols": "aapl, MSFT, AAPL", "until": "2026-11-08"})]   # bis gestern


def test_stock_trend_from_seven_closes():
    trend = morning._stock_trend([94, 95, 96, 97, 98, 99, 100])
    assert trend["sessions"] == 7
    points = trend["points"].split()
    assert points[0] == "2.0,22.0" and points[-1] == "62.0,2.0"


def test_failed_sources_still_deliver_and_respect_quiet_time():
    watcher = harness(MONDAY.replace(hour=6), time="06:00", **OPTIONS)
    watcher.errors["watch_calendar_events"] = "Google nicht erreichbar"
    watcher.errors["watch_morning_weather"] = "Open-Meteo ist gerade nicht verfügbar."
    watcher.errors["watch_stock_quotes"] = "Alpha-Vantage-Schlüssel hinterlegen (⚙ Einstellungen → Zugangsdaten)."
    assert watcher.check() == 0
    watcher.now = MONDAY
    assert watcher.check() == 1
    assert "Google Kalender ist gerade nicht verfügbar" in watcher.texts[0]
    assert "Open-Meteo ist gerade nicht verfügbar" in watcher.texts[0]
    assert "Alpha-Vantage-Schlüssel hinterlegen" in watcher.texts[0]
    assert "Songvorschlag" in watcher.texts[0]


def test_without_tools_or_with_odd_answers_the_briefing_still_comes(monkeypatch):
    plain = morning.prepare(MONDAY, OPTIONS)                         # nur feste Befehle, kein MCP
    assert plain.view.data["weather"]["status"] == "Open-Meteo ist gerade nicht verfügbar."
    assert plain.view.data["stocks"]["status"] == "Börsendaten sind gerade nicht verfügbar."
    odd = morning.prepare(MONDAY, OPTIONS, lambda name, arguments: ToolResult("[]"))   # falsches Format
    assert odd.view.data["weather"]["status"] == "Open-Meteo ist gerade nicht verfügbar."
    assert odd.view.data["stocks"]["status"] == "Börsendaten sind gerade nicht verfügbar."
    assert odd.view.data["calendar"]["status"] == "Heute stehen keine Termine an."
    call_tool, _ = mcp_tools(monkeypatch)
    unknown = morning.prepare(MONDAY, {**OPTIONS, "weather_location": "Unbekannt,XX"}, call_tool)
    assert unknown.view.data["weather"]["location"] == "Berlin"     # die Attrappe findet immer Berlin
    gone = morning.prepare(MONDAY, OPTIONS, lambda name, arguments: ToolResult("Ort weg", is_error=True))
    assert gone.view.data["weather"] == {"status": "Ort weg", "location": "Berlin,DE"}
