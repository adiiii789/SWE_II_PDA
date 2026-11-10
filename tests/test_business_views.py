import datetime as dt
import unittest
from unittest import mock

from backend import api, business_views as bv, config
from backend.assistant.tools import ToolResult
from backend.rendering import ViewRenderer
from backend.views import TemplateView

NOW = dt.datetime(2026, 11, 10, 9, 30)   # Dienstag


def event(title, start, end, **extra):
    return {"id": "c::" + title, "title": title, "start": start, "end": end, "all_day": False,
            "location": "", "calendar": "Privat", "primary": True, "color": "#039BE5", "invitation": "",
            "recurring": False, **extra}


def calendar(days=1, start="2026-11-10", events=(), **extra):
    return {"type": "calendar", "start": start, "days": days, "query": "", "events": list(events),
            "more": False, **extra}


def tasks(*items, **extra):
    return {"type": "tasks", "completed": False, "due_until": "", "query": "", "several_lists": False,
            "more": False, "tasks": list(items), **extra}


def task(title, due="", **extra):
    return {"id": "l1::" + title, "title": title, "notes": "", "due": due, "time": "", "list": "Meine",
            "depth": 0, "done": False, **extra}


class CalendarTest(unittest.TestCase):
    def component(self, **kwargs):
        return bv.components([calendar(**kwargs)], NOW)[0]

    def test_kind_by_number_of_days(self):
        self.assertEqual(self.component(days=1)["kind"], "day")
        self.assertEqual(self.component(days=7)["kind"], "week")
        self.assertEqual(self.component(days=30, start="2026-11-01")["kind"], "month")

    def test_day_title_names_today(self):
        self.assertEqual(self.component()["title"], "Heute · Dienstag, 10. November")

    def test_block_position_and_height(self):
        block = self.component(events=[event("Meeting", "2026-11-10T10:00", "2026-11-10T11:30")])["columns"][0]["blocks"][0]
        self.assertEqual((block["top"], block["height"]), (10 * bv.HOUR_PX, 1.5 * bv.HOUR_PX))
        self.assertEqual(block["time"], "10:00–11:30")
        self.assertEqual(block["tint"], "rgba(3, 155, 229, 0.18)")

    def test_overlapping_events_side_by_side(self):
        blocks = self.component(events=[event("A", "2026-11-10T10:00", "2026-11-10T12:00"),
                                        event("B", "2026-11-10T11:00", "2026-11-10T13:00"),
                                        event("C", "2026-11-10T14:00", "2026-11-10T15:00")])["columns"][0]["blocks"]
        self.assertEqual([(b["left"], b["width"]) for b in blocks], [(0, 50), (50, 50), (0, 100)])

    def test_short_event_keeps_minimum_height(self):
        block = self.component(events=[event("Kurz", "2026-11-10T10:00", "2026-11-10T10:05")])["columns"][0]["blocks"][0]
        self.assertEqual(block["height"], bv.MIN_EVENT_PX)
        self.assertTrue(block["compact"])

    def test_event_over_midnight_is_cut_per_day(self):
        columns = self.component(days=2, events=[event("Nacht", "2026-11-10T22:00", "2026-11-11T02:00")])["columns"]
        self.assertEqual(columns[0]["blocks"][0]["time"], "22:00–…")
        self.assertEqual(columns[1]["blocks"][0]["time"], "…–02:00")
        self.assertEqual(columns[1]["blocks"][0]["top"], 0)

    def test_all_day_events_in_strip_with_exclusive_end(self):
        part = self.component(days=3, events=[event("Urlaub", "2026-11-10", "2026-11-12", all_day=True)])
        self.assertTrue(part["has_all_day"])
        self.assertEqual([len(column["all_day"]) for column in part["columns"]], [1, 1, 0])
        self.assertEqual([len(column["blocks"]) for column in part["columns"]], [0, 0, 0])

    def test_now_line_only_today(self):
        part = self.component(days=2)
        self.assertEqual(part["columns"][0]["now"], 9.5 * bv.HOUR_PX)
        self.assertIsNone(part["columns"][1]["now"])

    def test_scroll_shows_first_event(self):
        part = self.component(start="2026-11-12", events=[event("Spät", "2026-11-12T15:00", "2026-11-12T16:00")])
        self.assertEqual(part["scroll"], round(14.5 * bv.HOUR_PX))

    def test_scroll_today_keeps_now_visible(self):
        later = self.component(events=[event("Später", "2026-11-10T15:00", "2026-11-10T16:00")])
        self.assertEqual(later["scroll"], round(8.5 * bv.HOUR_PX))     # eine Stunde vor jetzt
        early = self.component(events=[event("Früh", "2026-11-10T02:00", "2026-11-10T03:00")])
        self.assertEqual(early["scroll"], round(9.5 * bv.HOUR_PX - (bv.VISIBLE_PX - bv.HOUR_PX)))
        for part in (later, early):
            self.assertLessEqual(part["scroll"], part["columns"][0]["now"])
            self.assertGreaterEqual(part["scroll"] + bv.VISIBLE_PX, part["columns"][0]["now"])

    def test_month_grid_starts_monday_and_limits_events(self):
        many = [event(f"T{i}", "2026-11-10T08:00", "2026-11-10T09:00") for i in range(5)]
        part = self.component(days=30, start="2026-11-01", events=many)
        self.assertEqual(part["title"], "November 2026")
        first_week = part["weeks"][0]
        self.assertEqual(first_week[0]["day"], 26)   # Montag, 26. Oktober
        self.assertFalse(first_week[0]["in_range"])
        cell = next(cell for week in part["weeks"] for cell in week if cell["today"])
        self.assertEqual((len(cell["events"]), cell["more"]), (bv.MONTH_EVENTS_PER_DAY, 2))

    def test_invalid_color_falls_back(self):
        block = self.component(events=[event("X", "2026-11-10T10:00", "2026-11-10T11:00",
                                              color="red;background:url(x)")])["columns"][0]["blocks"][0]
        self.assertEqual(block["color"], bv.DEFAULT_COLOR)

    def test_declined_invitation_marked(self):
        block = self.component(events=[event("X", "2026-11-10T10:00", "2026-11-10T11:00",
                                              invitation="declined")])["columns"][0]["blocks"][0]
        self.assertTrue(block["declined"])
        self.assertIn("Abgesagt", block["details"])


class TasksTest(unittest.TestCase):
    def test_due_labels_and_states(self):
        part = bv.components([tasks(task("Alt", "2026-11-09"), task("Jetzt", "2026-11-10"),
                                    task("Bald", "2026-11-13"), task("Ohne"))], NOW)[0]
        self.assertEqual([(t["due"], t["due_state"]) for t in part["tasks"]],
                         [("Gestern", "overdue"), ("Heute", "today"), ("Fr 13.11.", ""), ("", "")])
        self.assertEqual(part["subtitle"], "4 offene Aufgaben")

    def test_list_name_only_with_several_lists(self):
        self.assertEqual(bv.components([tasks(task("A"))], NOW)[0]["tasks"][0]["list"], "")
        self.assertEqual(bv.components([tasks(task("A"), several_lists=True)], NOW)[0]["tasks"][0]["list"], "Meine")

    def test_completed_view(self):
        part = bv.components([tasks(task("A", "2026-11-01", done=True), completed=True)], NOW)[0]
        self.assertEqual(part["title"], "Erledigte Aufgaben")
        self.assertEqual(part["tasks"][0]["due_state"], "")


class MailsTest(unittest.TestCase):
    def test_dates_and_unread(self):
        data = {"type": "mails", "folder": "INBOX", "unread_only": False, "query": "", "mails": [
            {"uid": "5", "sender": "Anna", "address": "a@x.de", "subject": "Hi", "seen": False,
             "date": "2026-11-10T08:15+01:00"},
            {"uid": "4", "sender": "", "address": "b@x.de", "subject": "Alt", "seen": True,
             "date": "2026-11-09T08:15"},
            {"uid": "x1", "sender": "Böse", "address": "", "subject": "", "seen": True, "date": ""}]}
        part = bv.components([data], NOW)[0]
        self.assertEqual([m["uid"] for m in part["mails"]], ["5", "4"])   # ungültige UID fällt weg
        self.assertEqual(part["mails"][1]["sender"], "b@x.de")
        self.assertEqual(part["mails"][1]["date"], "Gestern")
        self.assertEqual(part["subtitle"], "2 Mails · 1 ungelesen")


class ComponentsTest(unittest.TestCase):
    def test_several_in_order_without_duplicates(self):
        parts = bv.components([calendar(), tasks(task("A")), calendar(), {"type": "unbekannt"}, None], NOW)
        self.assertEqual([part["kind"] for part in parts], ["day", "tasks"])

    def test_broken_data_is_skipped(self):
        self.assertEqual(bv.components([{"type": "calendar", "start": "kaputt", "days": 1}], NOW), [])


class DashboardTemplateTest(unittest.TestCase):
    def render(self, *data):
        parts = bv.components(data, NOW)
        return ViewRenderer(config.TEMPLATE_DIR, config.FRONTEND_DIR).render(
            TemplateView("dashboard", {"components": parts}))

    def test_all_kinds_render(self):
        html = self.render(calendar(events=[event("Zahnarzt", "2026-11-10T10:00", "2026-11-10T11:00")]),
                           calendar(days=7, start="2026-11-09"), calendar(days=30, start="2026-11-01"),
                           tasks(task("Steuer", "2026-11-10")),
                           {"type": "mails", "folder": "INBOX", "mails": [
                               {"uid": "3", "sender": "Anna", "subject": "Hallo", "seen": False, "date": ""}]})
        for needle in ("Zahnarzt", "card-week", "card-month", 'data-id="l1::Steuer"', 'data-uid="3"',
                       "--background", "postMessage"):
            self.assertIn(needle, html)

    def test_third_party_text_is_escaped(self):
        html = self.render(tasks(task("<img src=x onerror=alert(1)>")))
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;img src=x", html)


class CompleteTaskFromViewTest(unittest.TestCase):
    def call(self, *args, result=ToolResult("Erledigt")):
        tools = mock.Mock()
        tools.call_tool.return_value = result
        with mock.patch.object(api, "_assistant", return_value=mock.Mock(tools=tools)):
            return api.complete_task_from_view(*args), tools

    def test_calls_tool_without_model(self):
        answer, tools = self.call("l1::t1", False)
        self.assertEqual(answer, "Erledigt")
        tools.call_tool.assert_called_once_with("complete_task", {"task_id": "l1::t1", "done": False})

    def test_rejects_invalid_id(self):
        for bad in ("", "ohne-trenner", "a::b c", 5):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.call(bad)

    def test_tool_error_is_raised(self):
        with self.assertRaises(RuntimeError):
            self.call("l1::t1", result=ToolResult("nicht gefunden", is_error=True))

    def test_without_tools(self):
        with mock.patch.object(api, "_assistant", return_value=object()), self.assertRaises(RuntimeError):
            api.complete_task_from_view("l1::t1")


if __name__ == "__main__":
    unittest.main()
