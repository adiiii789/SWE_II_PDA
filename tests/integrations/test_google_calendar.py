import datetime
import tempfile
import unittest
from pathlib import Path

from backend.integrations.google_calendar import GoogleCalendar, oauth_token
from backend.integrations.http import IntegrationError
from tests.integrations.fake_http import FakeHttp

START = datetime.datetime(2026, 10, 21, tzinfo=datetime.timezone.utc)


def item(id_, start, end, **extra):
    return {"id": id_, "summary": f"Termin {id_}", "start": start, "end": end, **extra}


class GoogleCalendarTest(unittest.TestCase):
    def test_events_with_time_only(self):
        http = FakeHttp({"/events": {"items": [
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
        _, _, params, headers = http.calls[0]
        self.assertEqual(headers, {"Authorization": "Bearer tok"})
        self.assertEqual(params["singleEvents"], "true")

    def test_event_without_title_or_location(self):
        http = FakeHttp({"/events": {"items": [{"start": {"dateTime": "2026-10-21T09:00:00+02:00"},
                                                 "end": {"dateTime": "2026-10-21T10:00:00+02:00"}}]}})
        event = GoogleCalendar(http, lambda interactive: "tok").events(START, START)[0]
        self.assertEqual((event.title, event.location), ("(ohne Titel)", ""))


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
