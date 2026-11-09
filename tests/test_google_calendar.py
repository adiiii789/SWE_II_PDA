"""mcp_servers/google_calendar.py: Termine lesen und erstellen, Anmeldung - ohne echtes Google."""
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend import config

sys.path.insert(0, str(config.ROOT_DIR / "mcp_servers"))
import google_calendar as gc  # noqa: E402

PRIMARY = {"id": "ich@example.com", "summary": "ich@example.com", "primary": True, "selected": True}
WORK = {"id": "arbeit", "summary": "Arbeit", "summaryOverride": "Büro", "selected": True}
HIDDEN = {"id": "versteckt", "summary": "Versteckt"}


def timed(title, start, end, **fields):
    return {"summary": title, "start": {"dateTime": start}, "end": {"dateTime": end}, **fields}


class FakeRequest:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error

    def execute(self):
        if self.error:
            raise self.error
        return self.result


class FakeService:
    """Baut die Aufrufkette service.events().list(...).execute() nach."""

    def __init__(self, calendars=(PRIMARY,), events=None, stored=None):
        self.calendar_items = list(calendars)
        self.by_calendar = events or {}
        self.stored = stored
        self.list_calls = []
        self.inserted = []
        self.notified = []
        self.patched = []
        self.deleted = []

    def calendarList(self):
        return mock.Mock(list=lambda: FakeRequest({"items": self.calendar_items}))

    def calendars(self):
        return mock.Mock(get=lambda calendarId: FakeRequest({"timeZone": "Europe/Berlin"}))

    def events(self):
        return mock.Mock(list=self._list, insert=self._insert, get=self._get, patch=self._patch, delete=self._delete)

    def _list(self, **arguments):
        self.list_calls.append(arguments)
        events = self.by_calendar.get(arguments["calendarId"], [])
        return FakeRequest({"items": [{"id": f"e{i}", **event} for i, event in enumerate(events)]})

    def _insert(self, calendarId, body, sendUpdates=None):
        self.inserted.append((calendarId, body))
        self.notified.append(sendUpdates)
        return FakeRequest({**body, "id": "neu", "htmlLink": "https://calendar.example/1"})

    def _get(self, calendarId, eventId):
        return FakeRequest(self.stored)

    def _patch(self, calendarId, eventId, body, sendUpdates):
        self.patched.append((calendarId, eventId, body))
        self.notified.append(sendUpdates)
        return FakeRequest({**self.stored, **body})

    def _delete(self, calendarId, eventId, sendUpdates):
        self.deleted.append((calendarId, eventId))
        self.notified.append(sendUpdates)
        return FakeRequest("")


class WatchedEventsTest(unittest.TestCase):
    def test_data_of_visible_calendars(self):
        service = FakeService([PRIMARY, WORK, HIDDEN], {
            "ich@example.com": [timed("Arzt", "2026-11-10T16:00:00+01:00", "2026-11-10T17:00:00+01:00", location="Praxis",
                                      description="<b>Karte</b> mitbringen", transparency="transparent",
                                      attendees=[{"self": True, "responseStatus": "needsAction"}])],
            "arbeit": [{"summary": "Messe", "start": {"date": "2026-11-11"}, "end": {"date": "2026-11-12"},
                        "recurringEventId": "serie"}],
            "versteckt": [timed("Geheim", "2026-11-10T08:00:00", "2026-11-10T08:30:00")],
        })
        first, second = gc.watched_events(service, 3)
        self.assertEqual(first, {"id": gc.make_ref("ich@example.com", "e0"), "series": gc.make_ref("ich@example.com", "e0"),
                                 "title": "Arzt", "start": "2026-11-10T16:00:00+01:00", "end": "2026-11-10T17:00:00+01:00",
                                 "all_day": False, "location": "Praxis", "description": "Karte mitbringen",
                                 "calendar": "ich@example.com", "response": "needsAction", "free": True})
        self.assertEqual((second["all_day"], second["start"], second["calendar"], second["response"], second["free"]),
                         (True, "2026-11-11", "Büro", "", False))
        self.assertEqual(second["series"], gc.make_ref("arbeit", "serie"))

    def test_period_is_limited(self):
        service = FakeService()
        gc.watched_events(service, 9999)
        call = service.list_calls[0]
        self.assertTrue(call["timeMin"].startswith(dt.date.today().isoformat()))
        self.assertEqual(call["singleEvents"], True)


class ListEventsTest(unittest.TestCase):
    def test_sorted_across_visible_calendars(self):
        service = FakeService([PRIMARY, WORK, HIDDEN], {
            "ich@example.com": [timed("Später", "2026-11-10T16:00:00", "2026-11-10T17:00:00")],
            "arbeit": [timed("Früher", "2026-11-10T09:00:00", "2026-11-10T09:30:00", location="Raum 1")],
            "versteckt": [timed("Geheim", "2026-11-10T08:00:00", "2026-11-10T08:30:00")],
        })
        text = gc.list_events(service, "2026-11-10", days=2)
        self.assertNotIn("Geheim", text)
        self.assertLess(text.index("Früher"), text.index("Später"))
        self.assertIn("Di 10.11.2026", text)
        self.assertIn("Ort: Raum 1 | Kalender: Büro", text)
        self.assertNotIn("Kalender: ich@example.com", text)
        self.assertIn("Termine von Di 10.11.2026 bis Mi 11.11.2026", text)

    def test_period_and_search_reach_google(self):
        service = FakeService()
        gc.list_events(service, "2026-11-10", days=2, query="  Zahnarzt ", limit=5)
        call = service.list_calls[0]
        self.assertTrue(call["timeMin"].startswith("2026-11-10T00:00:00"))
        self.assertTrue(call["timeMax"].startswith("2026-11-12T00:00:00"))
        self.assertEqual((call["q"], call["maxResults"], call["singleEvents"]), ("Zahnarzt", 6, True))

    def test_empty_start_means_today(self):
        service = FakeService()
        gc.list_events(service)
        self.assertTrue(service.list_calls[0]["timeMin"].startswith(dt.date.today().isoformat()))

    def test_bounds(self):
        service = FakeService()
        gc.list_events(service, "2026-01-01", days=9999, limit=9999)
        call = service.list_calls[0]
        self.assertTrue(call["timeMax"].startswith("2026-04-01"))   # 90 Tage
        self.assertEqual(call["maxResults"], gc.MAX_LIMIT + 1)

    def test_no_events(self):
        self.assertIn("Keine Termine", gc.list_events(FakeService(), "2026-11-10"))
        self.assertIn("'Arzt'", gc.list_events(FakeService(), "2026-11-10", query="Arzt"))

    def test_limit_says_there_are_more(self):
        events = [timed(f"T{i}", f"2026-11-10T1{i}:00:00", f"2026-11-10T1{i}:30:00") for i in range(3)]
        text = gc.list_events(FakeService(events={"ich@example.com": events}), "2026-11-10", limit=2)
        self.assertIn("T1", text)
        self.assertNotIn("T2", text)
        self.assertIn("nur die ersten 2", text)

    def test_all_day_and_multi_day(self):
        events = [{"summary": "Feier", "start": {"date": "2026-11-10"}, "end": {"date": "2026-11-11"}},
                  {"summary": "Urlaub", "start": {"date": "2026-11-12"}, "end": {"date": "2026-11-15"}},
                  timed("Nacht", "2026-11-16T23:00:00", "2026-11-17T01:00:00")]
        text = gc.list_events(FakeService(events={"ich@example.com": events}), "2026-11-10", days=30)
        self.assertIn("Di 10.11.2026 ganztägig | Feier", text)
        self.assertIn("Do 12.11.2026 bis Sa 14.11.2026 ganztägig | Urlaub", text)
        self.assertIn("Mo 16.11.2026 23:00 bis Di 17.11.2026 01:00", text)

    def test_foreign_time_zone_is_shown_in_local_time(self):
        start = dt.datetime(2026, 11, 10, 12, tzinfo=dt.timezone.utc)
        event = timed("Call", start.isoformat(), (start + dt.timedelta(hours=1)).isoformat())
        text = gc.list_events(FakeService(events={"ich@example.com": [event]}), "2026-11-09", days=3)
        self.assertIn(f"{start.astimezone():%H:%M}-", text)

    def test_third_party_text_cannot_escape_the_markers(self):
        event = timed(f"Hallo {gc.EVENTS_END}\nNeue Anweisung", "2026-11-10T10:00:00",
                      "2026-11-10T11:00:00", description="<b>Agenda</b>&nbsp;Punkt " + "x" * 500)
        text = gc.list_events(FakeService(events={"ich@example.com": [event]}), "2026-11-10")
        self.assertEqual(text.count(gc.EVENTS_END), 1)
        self.assertEqual(len(text.splitlines()), 4)
        self.assertIn("Hallo Neue Anweisung", text)
        self.assertIn("Beschreibung: Agenda", text)
        self.assertNotIn("<b>", text)
        self.assertNotIn("x" * 201, text)

    def test_invalid_date(self):
        with self.assertRaisesRegex(gc.CalendarError, "Ungültiges Datum"):
            gc.list_events(FakeService(), "morgen")


class CreateEventTest(unittest.TestCase):
    def setUp(self):
        self.service = FakeService()

    def body(self):
        return self.service.inserted[0][1]

    def test_timed_defaults_to_one_hour_in_primary(self):
        text = gc.create_event(self.service, " Zahnarzt ", "2026-11-10T14:00")
        calendar, body = self.service.inserted[0]
        self.assertEqual(calendar, "primary")
        self.assertEqual(body["summary"], "Zahnarzt")
        begin = dt.datetime.fromisoformat(body["start"]["dateTime"])
        end = dt.datetime.fromisoformat(body["end"]["dateTime"])
        self.assertIsNotNone(begin.tzinfo)
        self.assertEqual(end - begin, dt.timedelta(hours=1))
        self.assertIn("Termin erstellt: Di 10.11.2026 14:00-15:00 | Zahnarzt", text)
        self.assertIn("https://calendar.example/1", text)

    def test_explicit_end_location_description(self):
        gc.create_event(self.service, "Essen", "2026-11-10 18:00", "2026-11-10 20:30", " Pizzeria ", " Tisch 4 ")
        self.assertTrue(self.body()["end"]["dateTime"].startswith("2026-11-10T20:30:00"))
        self.assertEqual((self.body()["location"], self.body()["description"]), ("Pizzeria", "Tisch 4"))

    def test_all_day_end_is_exclusive_at_google(self):
        text = gc.create_event(self.service, "Urlaub", "2026-11-10", "2026-11-12")
        self.assertEqual(self.body()["start"], {"date": "2026-11-10"})
        self.assertEqual(self.body()["end"], {"date": "2026-11-13"})
        self.assertIn("Di 10.11.2026 bis Do 12.11.2026 ganztägig", text)

    def test_single_all_day(self):
        gc.create_event(self.service, "Feier", "2026-11-10")
        self.assertEqual(self.body()["end"], {"date": "2026-11-11"})

    def test_without_guests_nobody_is_invited(self):
        gc.create_event(self.service, "Essen", "2026-11-10T18:00")
        self.assertNotIn("attendees", self.body())
        self.assertEqual(self.service.notified, [None])

    def test_guests_are_invited(self):
        text = gc.create_event(self.service, "Essen", "2026-11-10T18:00", guests=("anna@example.com",))
        self.assertEqual(self.body()["attendees"], [{"email": "anna@example.com"}])
        self.assertEqual(self.service.notified, ["all"])
        self.assertIn("Eingeladen: anna@example.com", text)

    def test_result_has_an_id(self):
        self.assertIn("ID: primary::neu", gc.create_event(self.service, "Essen", "2026-11-10"))

    def test_weekly_series_gets_a_named_time_zone(self):
        gc.create_event(self.service, "Sport", "2026-11-09T09:00", recurrence="freq=weekly;byday=mo;count=4")
        self.assertEqual(self.body()["recurrence"], ["RRULE:FREQ=WEEKLY;BYDAY=MO;COUNT=4"])
        self.assertEqual((self.body()["start"]["timeZone"], self.body()["end"]["timeZone"]),
                         ("Europe/Berlin", "Europe/Berlin"))

    def test_all_day_series_needs_no_time_zone(self):
        gc.create_event(self.service, "Müll", "2026-11-09", recurrence="RRULE:FREQ=MONTHLY")
        self.assertEqual(self.body()["recurrence"], ["RRULE:FREQ=MONTHLY"])
        self.assertNotIn("timeZone", self.body()["start"])

    def test_invalid_recurrence(self):
        for rule in ("jede Woche", "FREQ=HOURLY", "FREQ=WEEKLY\nATTENDEE:x"):
            with self.subTest(rule=rule), self.assertRaisesRegex(gc.CalendarError, "Ungültige Wiederholung"):
                gc.create_event(self.service, "X", "2026-11-09", recurrence=rule)
        self.assertEqual(self.service.inserted, [])

    def test_reminders(self):
        gc.create_event(self.service, "X", "2026-11-09", reminder_minutes=[30, 1440])
        self.assertEqual(self.body()["reminders"], {"useDefault": False, "overrides": [
            {"method": "popup", "minutes": 30}, {"method": "popup", "minutes": 1440}]})

    def test_invalid_reminders(self):
        for minutes, message in (([1] * 6, "Höchstens 5"), ([-1], "zwischen"), ([40321], "zwischen")):
            with self.subTest(minutes=minutes), self.assertRaisesRegex(gc.CalendarError, message):
                gc.create_event(self.service, "X", "2026-11-09", reminder_minutes=minutes)

    def test_other_calendar_by_name(self):
        service = FakeService([PRIMARY, {**WORK, "accessRole": "owner"}])
        gc.create_event(service, "X", "2026-11-09", calendar=" büro ")
        self.assertEqual(service.inserted[0][0], "arbeit")

    def test_read_only_calendar_is_refused(self):
        service = FakeService([{**PRIMARY, "accessRole": "owner"}, {**WORK, "accessRole": "reader"}])
        with self.assertRaisesRegex(gc.CalendarError, "Kein beschreibbarer Kalender.*ich@example.com"):
            gc.create_event(service, "X", "2026-11-09", calendar="Büro")
        self.assertEqual(service.inserted, [])

    def test_invalid_input_creates_nothing(self):
        cases = [("", "2026-11-10T14:00", "", "Titel"),
                 ("X", "bald", "", "Ungültige Zeit"),
                 ("X", "2026-13-01", "", "Ungültiges Datum"),
                 ("X", "2026-11-10T14:00", "2026-11-10T13:00", "nach dem Beginn"),
                 ("X", "2026-11-10T14:00", "2026-11-10", "nach dem Beginn"),
                 ("X", "2026-11-10", "2026-11-09", "vor dem Beginn")]
        for title, start, end, message in cases:
            with self.subTest(start=start, end=end), self.assertRaisesRegex(gc.CalendarError, message):
                gc.create_event(self.service, title, start, end)
        self.assertEqual(self.service.inserted, [])


class ConflictTest(unittest.TestCase):
    MEETING = timed("Meeting", "2026-11-10T14:30:00+01:00", "2026-11-10T15:30:00+01:00")

    def service(self, *events):
        return FakeService(events={"ich@example.com": list(events)})

    def create(self, service, start="2026-11-10T14:00:00+01:00", end="2026-11-10T15:00:00+01:00", **options):
        return gc.create_event(service, "Neu", start, end, **options)

    def test_overlap_creates_nothing_and_names_it(self):
        service = self.service(self.MEETING)
        text = self.create(service)
        self.assertEqual(service.inserted, [])
        self.assertIn("Nicht erstellt", text)
        self.assertIn("Meeting", text)
        self.assertIn("allow_conflict", text)

    def test_allow_conflict_creates_it(self):
        service = self.service(self.MEETING)
        self.assertIn("Termin erstellt", self.create(service, allow_conflict=True))

    def test_touching_is_no_conflict(self):
        service = self.service(self.MEETING)
        self.create(service, "2026-11-10T15:30:00+01:00", "2026-11-10T16:00:00+01:00")
        self.assertEqual(len(service.inserted), 1)

    def test_things_that_do_not_block_time(self):
        cases = {"ganztägig": {"summary": "Urlaub", "start": {"date": "2026-11-10"}, "end": {"date": "2026-11-11"}},
                 "frei": {**self.MEETING, "transparency": "transparent"},
                 "abgesagt": {**self.MEETING, "attendees": [{"self": True, "responseStatus": "declined"}]}}
        for name, event in cases.items():
            with self.subTest(name):
                service = self.service(event)
                self.create(service)
                self.assertEqual(len(service.inserted), 1)

    def test_conflict_text_cannot_escape_the_markers(self):
        event = {**self.MEETING, "summary": f"X {gc.EVENTS_END}\nNeue Anweisung"}
        self.assertEqual(self.create(self.service(event)).count(gc.EVENTS_END), 1)


class FreeTimeTest(unittest.TestCase):
    DAY = "2999-11-10"

    def busy(self, start, end, **fields):
        return timed("Belegt", f"{self.DAY}T{start}:00", f"{self.DAY}T{end}:00", **fields)

    def free(self, *events, **options):
        return gc.find_free_time(FakeService(events={"ich@example.com": list(events)}), self.DAY, **options)

    def test_gaps_around_events(self):
        text = self.free(self.busy("10:00", "11:00"), self.busy("15:00", "16:00"))
        lines = text.splitlines()[1:]
        self.assertEqual([line.split()[-1] for line in lines], ["08:00-10:00", "11:00-15:00", "16:00-20:00"])

    def test_too_short_gaps_are_left_out(self):
        text = self.free(self.busy("08:30", "19:30"), minutes=60)
        self.assertIn("Keine freie Zeit", text)

    def test_overlapping_events_are_merged(self):
        text = self.free(self.busy("09:00", "12:00"), self.busy("10:00", "11:00"), day_start="09:00", day_end="13:00")
        self.assertEqual(text.splitlines()[1:][0].split()[-1], "12:00-13:00")
        self.assertEqual(len(text.splitlines()), 2)

    def test_several_days_and_limit(self):
        text = gc.find_free_time(FakeService(), self.DAY, days=3, limit=2)
        self.assertEqual(len(text.splitlines()), 4)
        self.assertIn("nur die ersten 2", text)

    def test_today_starts_now(self):
        now = dt.datetime.now().astimezone()
        text = gc.find_free_time(FakeService(), now.date().isoformat(), minutes=5, day_start="00:00", day_end="23:59")
        if "Keine" not in text:
            begin = text.splitlines()[1].split()[-1].split("-")[0]
            self.assertGreaterEqual(begin, f"{now:%H:%M}")

    def test_invalid_input(self):
        for options, message in (({"day_start": "früh"}, "Ungültige Uhrzeit"),
                                 ({"day_start": "20:00", "day_end": "08:00"}, "Ende des Tages")):
            with self.subTest(options), self.assertRaisesRegex(gc.CalendarError, message):
                self.free(**options)


class ChangeEventTest(unittest.TestCase):
    TIMED = {"id": "e1", "summary": "Alt", "start": {"dateTime": "2026-11-10T14:00:00+01:00"},
             "end": {"dateTime": "2026-11-10T15:30:00+01:00"}}
    ALL_DAY = {"id": "e1", "summary": "Reise", "start": {"date": "2026-11-10"}, "end": {"date": "2026-11-13"}}
    INSTANCE = {**TIMED, "id": "e1_2026", "recurringEventId": "stamm"}

    def service(self, event=TIMED):
        return FakeService(stored=event)

    def body(self, service):
        return service.patched[0][2]

    def test_only_given_fields_change(self):
        service = self.service()
        text = gc.update_event(service, "kal::e1", title=" Neu ")
        self.assertEqual(service.patched, [("kal", "e1", {"summary": "Neu"})])
        self.assertIn("Termin geändert", text)

    def test_moving_keeps_the_duration(self):
        service = self.service()
        gc.update_event(service, "kal::e1", start="2026-11-12T09:00")
        begin = dt.datetime.fromisoformat(self.body(service)["start"]["dateTime"])
        end = dt.datetime.fromisoformat(self.body(service)["end"]["dateTime"])
        self.assertEqual(end - begin, dt.timedelta(minutes=90))

    def test_new_end_keeps_the_start(self):
        service = self.service()
        gc.update_event(service, "kal::e1", end="2026-11-10T16:00:00+01:00")
        begin = dt.datetime.fromisoformat(self.body(service)["start"]["dateTime"])
        self.assertEqual(begin, dt.datetime.fromisoformat("2026-11-10T14:00:00+01:00"))

    def test_moving_all_day_keeps_the_days(self):
        service = self.service(self.ALL_DAY)
        gc.update_event(service, "kal::e1", start="2026-12-01")
        self.assertEqual(self.body(service)["end"], {"date": "2026-12-04"})

    def test_timed_to_all_day_uses_one_day(self):
        service = self.service()
        gc.update_event(service, "kal::e1", start="2026-12-01")
        self.assertEqual(self.body(service)["end"], {"date": "2026-12-02"})

    def test_can_clear_and_set_reminders(self):
        service = self.service()
        gc.update_event(service, "kal::e1", location="NONE", description="none", reminder_minutes=[10])
        body = self.body(service)
        self.assertEqual((body["location"], body["description"]), (None, None))
        self.assertEqual(body["reminders"]["overrides"], [{"method": "popup", "minutes": 10}])

    def test_nothing_to_change(self):
        with self.assertRaisesRegex(gc.CalendarError, "nichts zum Ändern"):
            gc.update_event(self.service(), "kal::e1")

    def test_series_changes_the_master_but_not_its_time(self):
        service = self.service(self.INSTANCE)
        self.assertEqual(gc.update_event(service, "kal::e1_2026", title="Neu", series=True), "Ganze Serie geändert: Neu")
        self.assertEqual(service.patched[0][1], "stamm")
        with self.assertRaisesRegex(gc.CalendarError, "ganzen Serie"):
            gc.update_event(service, "kal::e1_2026", start="2026-12-01T09:00", series=True)

    def test_guests_are_told_about_changes_only_if_there_are_any(self):
        alone, invited = self.service(), self.service({**self.TIMED, "attendees": [{"email": "a@example.com"}]})
        gc.update_event(alone, "kal::e1", title="Neu")
        gc.update_event(invited, "kal::e1", title="Neu")
        self.assertEqual((alone.notified, invited.notified), (["none"], ["all"]))

    def test_delete_single_date_of_a_series(self):
        service = self.service(self.INSTANCE)
        self.assertIn("Termin gelöscht", gc.delete_event(service, "kal::e1_2026"))
        self.assertEqual(service.deleted, [("kal", "e1_2026")])

    def test_delete_whole_series(self):
        service = self.service(self.INSTANCE)
        self.assertEqual(gc.delete_event(service, "kal::e1_2026", series=True), "Ganze Serie gelöscht: Alt")
        self.assertEqual(service.deleted, [("kal", "stamm")])

    def test_master_id_without_series_flag_is_refused(self):
        service = self.service({**self.TIMED, "recurrence": ["RRULE:FREQ=DAILY"]})
        with self.assertRaisesRegex(gc.CalendarError, "ganze Serie"):
            gc.delete_event(service, "kal::e1")
        self.assertEqual(service.deleted, [])

    def test_invalid_id(self):
        for action in (gc.update_event, gc.delete_event):
            with self.subTest(action=action.__name__), self.assertRaisesRegex(gc.CalendarError, "Ungültige Termin-ID"):
                action(self.service(), "e1")


class InvitationTest(unittest.TestCase):
    PEOPLE = [{"email": "chef@example.com", "organizer": True, "responseStatus": "accepted"},
              {"email": "ich@example.com", "self": True, "responseStatus": "needsAction"}]
    EVENT = {**ChangeEventTest.TIMED, "attendees": PEOPLE}

    def test_answer_changes_only_own_status_and_tells_organizer(self):
        service = FakeService(stored=self.EVENT)
        self.assertIn("Einladung zugesagt", gc.respond_to_event(service, "kal::e1", "accepted"))
        people = service.patched[0][2]["attendees"]
        self.assertEqual([person["responseStatus"] for person in people], ["accepted", "accepted"])
        self.assertEqual(people[0]["email"], "chef@example.com")
        self.assertEqual(service.notified, ["all"])

    def test_event_without_invitation(self):
        with self.assertRaisesRegex(gc.CalendarError, "keine Einladung"):
            gc.respond_to_event(FakeService(stored=ChangeEventTest.TIMED), "kal::e1", "declined")

    def test_invalid_answer(self):
        with self.assertRaisesRegex(gc.CalendarError, "Ungültige Antwort"):
            gc.respond_to_event(FakeService(stored=self.EVENT), "kal::e1", "vielleicht")

    def test_overview_shows_series_invitation_and_id(self):
        event = timed("Runde", "2026-11-10T10:00:00", "2026-11-10T11:00:00", recurringEventId="s", attendees=self.PEOPLE)
        text = gc.list_events(FakeService(events={"ich@example.com": [event]}), "2026-11-10")
        self.assertIn("Serientermin | Einladung: noch offen | ID: ich@example.com::e0", text)


class GoogleErrorsTest(unittest.TestCase):
    def test_http_error(self):
        from googleapiclient.errors import HttpError
        response = mock.Mock(status=403, reason="Calendar API has not been used")
        error = HttpError(response, b"{}")
        with self.assertRaisesRegex(gc.CalendarError, "Fehler 403"):
            gc._execute(FakeRequest(error=error))

    def test_network_error(self):
        with self.assertRaisesRegex(gc.CalendarError, "nicht erreichbar"):
            gc._execute(FakeRequest(error=TimeoutError("zu langsam")))

    def test_revoked_login(self):
        from google.auth.exceptions import RefreshError
        with self.assertRaisesRegex(gc.CalendarError, "anmelden"):
            gc._execute(FakeRequest(error=RefreshError("invalid_grant")))


class SetupTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.token = self.dir / gc.TOKEN_FILE

    def write_token(self, expiry="2000-01-01T00:00:00Z"):
        self.token.write_text(json.dumps({"token": "alt", "refresh_token": "r", "client_id": "c",
                                          "client_secret": "s", "expiry": expiry}), encoding="utf-8")

    def test_connect_without_login(self):
        with self.assertRaisesRegex(gc.CalendarError, "nicht eingerichtet.*google_calendar.py"):
            gc.connect(self.dir)

    def test_connect_with_broken_token(self):
        self.token.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(gc.CalendarError, "ungültig"):
            gc.connect(self.dir)

    def test_connect_refreshes_and_saves(self):
        from google.oauth2.credentials import Credentials
        self.write_token()

        def refresh(credentials, _request):
            credentials.token = "neu"
            credentials.expiry = dt.datetime(2999, 1, 1)
        with mock.patch.object(Credentials, "refresh", refresh), \
                mock.patch("googleapiclient.discovery.build", return_value="dienst") as build:
            self.assertEqual(gc.connect(self.dir), "dienst")
        self.assertEqual(build.call_args.args, ("calendar", "v3"))
        self.assertEqual(json.loads(self.token.read_text(encoding="utf-8"))["token"], "neu")

    def test_connect_with_expired_login(self):
        from google.auth.exceptions import RefreshError
        from google.oauth2.credentials import Credentials
        self.write_token()
        with mock.patch.object(Credentials, "refresh", side_effect=RefreshError("invalid_grant")), \
                self.assertRaisesRegex(gc.CalendarError, "abgelaufen"):
            gc.connect(self.dir)

    def test_login_needs_client_file(self):
        with self.assertRaisesRegex(gc.CalendarError, "credentials.json fehlt"):
            gc.login(self.dir)

    def test_login_saves_token(self):
        (self.dir / gc.CLIENT_FILE).write_text("{}", encoding="utf-8")
        flow = mock.Mock()
        flow.run_local_server.return_value.to_json.return_value = '{"token": "t"}'
        with mock.patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file",
                        return_value=flow) as create:
            self.assertIn("eingerichtet", gc.login(self.dir))
        self.assertEqual(create.call_args.args[1], gc.SCOPES)
        self.assertEqual(flow.run_local_server.call_args.kwargs["access_type"], "offline")
        self.assertEqual(self.token.read_text(encoding="utf-8"), '{"token": "t"}')

    def test_login_with_wrong_client_file(self):
        (self.dir / gc.CLIENT_FILE).write_text('{"falsch": 1}', encoding="utf-8")
        with self.assertRaisesRegex(gc.CalendarError, "Desktop-App"):
            gc.login(self.dir)

    def test_main_installs_client_file(self):
        source = self.dir / "client_secret_123.json"
        source.write_text("inhalt", encoding="utf-8")
        target = self.dir / "ziel"
        with mock.patch.object(gc, "GOOGLE_DIR", target), mock.patch.object(gc, "login", return_value="ok"), \
                mock.patch("builtins.print"):
            self.assertEqual(gc.main([str(source)]), 0)
        self.assertEqual((target / gc.CLIENT_FILE).read_text(encoding="utf-8"), "inhalt")

    def test_main_reports_errors(self):
        with mock.patch("builtins.print") as output:
            self.assertEqual(gc.main([str(self.dir / "fehlt.json")]), 1)
        self.assertIn("nicht gefunden", str(output.call_args.args[0]))


if __name__ == "__main__":
    unittest.main()
