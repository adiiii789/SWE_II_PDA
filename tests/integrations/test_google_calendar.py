import datetime
import tempfile
import unittest
from pathlib import Path

from backend.integrations.google_calendar import GoogleCalendar, oauth_token
from backend.integrations.http import IntegrationError
from tests.integrations.fake_http import FakeHttp

START = datetime.datetime(2026, 10, 21, tzinfo=datetime.timezone.utc)
ONLY_PRIMARY = {"/calendarList": {"items": [{"id": "ich@example.com", "primary": True, "selected": True}]}}


def item(id_, start, end, **extra):
    return {"id": id_, "summary": f"Termin {id_}", "start": start, "end": end, **extra}


class GoogleCalendarTest(unittest.TestCase):
    def test_events_with_time_only(self):
        http = FakeHttp({**ONLY_PRIMARY, "/events": {"items": [
            item("a", {"dateTime": "2026-10-21T09:00:00+02:00"}, {"dateTime": "2026-10-21T10:00:00+02:00"},
                 location="Uni Mannheim", updated="2026-10-01T00:00:00Z"),
            item("b", {"date": "2026-10-21"}, {"date": "2026-10-22"}),   # ganztägig
            item("c", {"dateTime": "2026-10-21T11:00:00+02:00"}, {"dateTime": "2026-10-21T12:00:00+02:00"},
                 status="cancelled"),
        ]}})
        tokens = []
        calendar = GoogleCalendar(http, lambda interactive: tokens.append(interactive) or "tok")
        events = calendar.events(START, START + datetime.timedelta(days=1), interactive=False)

        self.assertEqual([e.id for e in events], ["a"])
        self.assertEqual(events[0].location, "Uni Mannheim")
        self.assertEqual(events[0].start.hour, 9)
        self.assertEqual(tokens, [False])
        _, url, params, headers = http.calls[1]
        self.assertIn("/calendars/ich%40example.com/events", url)
        self.assertEqual(headers, {"Authorization": "Bearer tok"})
        self.assertEqual(params["singleEvents"], "true")

    def test_event_without_title_or_location(self):
        http = FakeHttp({**ONLY_PRIMARY, "/events": {"items": [{"start": {"dateTime": "2026-10-21T09:00:00+02:00"},
                                                 "end": {"dateTime": "2026-10-21T10:00:00+02:00"}}]}})
        event = GoogleCalendar(http, lambda interactive: "tok").events(START, START)[0]
        self.assertEqual((event.title, event.location), ("(ohne Titel)", ""))


    def test_all_visible_calendars(self):
        # Termine stehen oft in einem abonnierten Kalender (z. B. Vorlesungsplan), nicht im Hauptkalender
        http = FakeHttp({
            "/calendarList": {"items": [{"id": "ich@example.com", "primary": True, "selected": True},
                                        {"id": "vorlesungen#ics@group.calendar.google.com", "selected": True},
                                        {"id": "feiertage", "selected": False}]},
            "/calendars/vorlesungen%23ics%40group.calendar.google.com/events": {"items": [
                item("v1", {"dateTime": "2026-10-21T08:00:00+02:00"}, {"dateTime": "2026-10-21T09:30:00+02:00"},
                     location="DHBW", iCalUID="uid-1"),
                item("v2", {"dateTime": "2026-10-21T14:00:00+02:00"}, {"dateTime": "2026-10-21T15:00:00+02:00"},
                     iCalUID="uid-2")]},
            "/calendars/ich%40example.com/events": {"items": [
                item("e1", {"dateTime": "2026-10-21T11:00:00+02:00"}, {"dateTime": "2026-10-21T12:00:00+02:00"}),
                item("copy", {"dateTime": "2026-10-21T14:00:00+02:00"}, {"dateTime": "2026-10-21T15:00:00+02:00"},
                     iCalUID="uid-2")]},   # dieselbe Einladung auch im Hauptkalender
        })
        calendar = GoogleCalendar(http, lambda interactive: "tok")
        events = calendar.events(START, START + datetime.timedelta(days=1))
        self.assertEqual([e.start.hour for e in events], [8, 11, 14])          # zusammen sortiert, ohne Dublette
        self.assertEqual(events[0].location, "DHBW")
        self.assertFalse(any("/calendars/feiertage/" in call[1] for call in http.calls))   # nicht angehakt
        calendar.events(START, START + datetime.timedelta(days=1))
        self.assertEqual(sum("/calendarList" in call[1] for call in http.calls), 1)   # Liste wiederverwendet

    def test_unreadable_calendar_is_skipped_and_list_falls_back_to_primary(self):
        http = FakeHttp({
            "/calendarList": {"items": [{"id": "a", "primary": True}, {"id": "b", "selected": True}]},
            "/calendars/b/events": IntegrationError("403"),
            "/calendars/a/events": {"items": [item("x", {"dateTime": "2026-10-21T09:00:00+02:00"},
                                                   {"dateTime": "2026-10-21T10:00:00+02:00"})]}})
        self.assertEqual([e.id for e in GoogleCalendar(http, lambda i: "tok").events(START, START)], ["x"])
        everything_down = FakeHttp({"/calendarList": IntegrationError("offline"), "/events": IntegrationError("offline")})
        with self.assertRaises(IntegrationError):
            GoogleCalendar(everything_down, lambda i: "tok").events(START, START)
        self.assertIn("/calendars/primary/events", everything_down.calls[1][1])   # ohne Liste: Hauptkalender


class OAuthTokenTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def test_background_call_never_opens_browser(self):
        with self.assertRaisesRegex(IntegrationError, "nicht angemeldet"):
            oauth_token(self.dir)(interactive=False)

    def test_missing_credentials_file(self):
        with self.assertRaisesRegex(IntegrationError, "credentials.json"):
            oauth_token(self.dir)()


if __name__ == "__main__":
    unittest.main()
