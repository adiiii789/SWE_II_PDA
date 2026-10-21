"""Werkzeuge, Ansicht, Erinnerung und der Befehl "reise"."""
import datetime
import threading
import unittest
from unittest import mock

from backend import config
from backend.assistant.skills import travel
from backend.assistant.skills.travel import view
from backend.assistant.skills.travel.planner import Option, TravelSettings, TripPlan
from backend.assistant.skills.travel.reminder import TravelReminder
from backend.assistant.skills.travel.tools import TravelTools
from backend.assistant.tools import ToolProvider, UnknownToolError
from backend.integrations.http import IntegrationError
from backend.rendering import ViewRenderer
from tests.assistant.travel.fakes import HOME, NOW, UNI, FakeCalendar, FakeRail, event, make_service


def render(template_view):
    return ViewRenderer(config.TEMPLATE_DIR, config.FRONTEND_DIR).render(template_view)


class TravelToolsTest(unittest.TestCase):
    def setUp(self):
        self.service = make_service(calendar=FakeCalendar(event()), rail=FakeRail())
        self.tools = TravelTools(lambda: self.service)

    def test_is_tool_provider(self):
        self.assertIsInstance(self.tools, ToolProvider)
        self.assertEqual([s.name for s in self.tools.list_tools()],
                         ["plan_trip_to_next_appointment", "plan_trip", "set_home_address"])

    def test_next_appointment(self):
        result = self.tools.call_tool("plan_trip_to_next_appointment", {})
        self.assertFalse(result.is_error)
        self.assertIn("Vorlesung", result.content)
        self.assertIn("Los um", result.content)
        self.assertEqual(result.view.template, "travel")
        self.assertIn("<!DOCTYPE html>", render(result.view))

    def test_no_appointment(self):
        self.service.calendar = FakeCalendar()
        self.assertIn("kein Termin", self.tools.call_tool("plan_trip_to_next_appointment", {}).content)

    def test_plan_trip_with_time(self):
        result = self.tools.call_tool("plan_trip", {"destination": "Universität", "arrive_by": "2026-10-21T14:00"})
        self.assertFalse(result.is_error, result.content)
        self.assertEqual(result.view.data["arrive_by"], "Mi 21.10. 14:00 Uhr")

    def test_plan_trip_defaults(self):
        result = self.tools.call_tool("plan_trip", {"destination": "Universität", "origin": "Zuhause"})
        self.assertFalse(result.is_error, result.content)

    def test_invalid_time(self):
        result = self.tools.call_tool("plan_trip", {"destination": "Universität", "arrive_by": "morgen"})
        self.assertTrue(result.is_error)
        self.assertIn("Ungültige Zeit", result.content)

    def test_missing_home_asks_model_to_ask_user(self):
        self.service.preferences.set("travel_home_address", "")
        result = self.tools.call_tool("plan_trip", {"destination": "Universität"})
        self.assertTrue(result.is_error)
        self.assertIn("set_home_address", result.content)

    def test_set_home_address(self):
        result = self.tools.call_tool("set_home_address", {"address": "Universität"})
        self.assertEqual(result.content, "Heimatadresse gespeichert: Universität, Heidelberg")

    def test_service_error(self):
        result = self.tools.call_tool("set_home_address", {"address": "Atlantis"})
        self.assertTrue(result.is_error)

    def test_unknown_tool(self):
        with self.assertRaises(UnknownToolError):
            self.tools.call_tool("fly_me", {})


class ViewTest(unittest.TestCase):
    def plan(self, *options, notes=()):
        return TripPlan(HOME, UNI, NOW + datetime.timedelta(hours=2), options, TravelSettings(), notes)

    def test_summary_and_view(self):
        later = NOW + datetime.timedelta(days=365)   # nicht "spät dran", egal wann der Test läuft
        best = Option("train", 3900, 4.5, price_estimated=True, detail="RE 10 ab Mannheim Hbf 09:00",
                      steps=("zu Fuß", "RE 10"), depart_at=later, arrive_at=later)
        other = Option("bike", 600, 0.0, geometry=((8.46, 49.48), (8.5, 49.45), (8.67, 49.41)))
        plan = self.plan(best, other, notes=("Hinweis <b>",))

        text = view.summary(plan, "Vorlesung")
        self.assertIn("am besten mit Bahn (RE 10 ab Mannheim Hbf 09:00)", text)
        self.assertIn("1 Std. 5 Min., ≈ 4,50 €", text)
        self.assertIn("Alternativen: Fahrrad 10 Min./kostenlos", text)
        self.assertNotIn("spät", text)

        html = render(view.trip_view(plan, "Vorlesung"))
        self.assertIn("Weg zu: Vorlesung", html)
        self.assertIn("class=\"line straight\"", html)   # Bahn: Luftlinie
        self.assertIn("Hinweis &lt;b&gt;", html)          # Autoescaping

    def test_route_geometry_and_late(self):
        best = Option("car", 1500, 3.0, geometry=((8.46, 49.48), (8.67, 49.41)),
                      depart_at=NOW, arrive_at=NOW)   # NOW liegt in der Vergangenheit
        data = view.trip_view(self.plan(best)).data
        self.assertTrue(data["best"]["late"])
        self.assertFalse(data["map"]["straight"])
        self.assertEqual(data["title"], "Reiseplan")
        for x, y in (data["map"]["start"], data["map"]["end"]):
            self.assertTrue(0 <= x <= view.MAP_WIDTH and 0 <= y <= view.MAP_HEIGHT)
        self.assertIn("spät dran", view.summary(self.plan(best)))

    def test_no_options(self):
        plan = self.plan(notes=("Auto/Taxi: kaputt",))
        self.assertIn("keinen Weg", view.summary(plan))
        self.assertIn("Auto/Taxi: kaputt", render(view.trip_view(plan)))

    def test_formatting(self):
        self.assertEqual(view.duration(30), "1 Min.")
        self.assertEqual(view.duration(7260), "2 Std. 1 Min.")
        self.assertEqual(view.euro(3.456), "3,46 €")


class ReminderTest(unittest.TestCase):
    def setUp(self):
        self.service = make_service(calendar=FakeCalendar(event(start=NOW + datetime.timedelta(minutes=60))))
        self.pushed = []
        self.reminder = TravelReminder(self.service, self.pushed.append, lead_minutes=15, interval_s=60)

    def at(self, moment):
        self.service.test_clock["now"] = moment

    def test_reminds_once_shortly_before_departure(self):
        depart = self.service.next_trip().plan.recommended.depart_at
        self.at(depart - datetime.timedelta(minutes=20))
        self.assertFalse(self.reminder.check())
        self.at(depart - datetime.timedelta(minutes=10))
        self.assertTrue(self.reminder.check())
        self.assertFalse(self.reminder.check())   # nur einmal je Termin
        self.assertIn("In 10 Minuten solltest du los", self.pushed[0].text)
        self.assertEqual(self.pushed[0].view.template, "travel")
        self.assertEqual(self.service.calendar.calls[-1], False)   # nie interaktiv anmelden

    def test_already_late(self):
        depart = self.service.next_trip().plan.recommended.depart_at
        self.at(depart + datetime.timedelta(minutes=2))
        self.assertTrue(self.reminder.check())
        self.assertTrue(self.pushed[0].text.startswith("Jetzt"))

    def test_errors_are_quiet(self):
        self.service.calendar = None   # nicht eingerichtet
        self.assertFalse(self.reminder.check())
        self.service.calendar = mock.Mock(events=mock.Mock(side_effect=IntegrationError("offline")))
        self.assertFalse(self.reminder.check())
        self.service.calendar = FakeCalendar()   # kein Termin
        self.assertFalse(self.reminder.check())

    def test_thread_survives_errors_and_stops(self):
        checked = threading.Event()

        def failing_check():
            checked.set()
            raise RuntimeError("kaputt")

        self.reminder.check = failing_check
        stop = self.reminder.start()
        self.assertTrue(checked.wait(2))
        stop()


class SkillTest(unittest.TestCase):
    def test_reise_command_without_key_explains_setup(self):
        reply = travel.next_trip_reply()   # Tests laufen ohne PDA_ORS_KEY (tests/conftest.py)
        self.assertIn("PDA_ORS_KEY", reply.text)
        self.assertEqual(reply.view.template, "default")

    def test_reise_command_with_service(self):
        service = make_service(calendar=FakeCalendar(event()))
        with mock.patch.object(travel, "service", lambda: service):
            self.assertEqual(travel.next_trip_reply().view.template, "travel")
            service.calendar = FakeCalendar()
            self.assertIn("kein Termin", travel.next_trip_reply().text)
            service.calendar = FakeCalendar(event())
            service.preferences.set("travel_home_address", "")
            service._trips.clear()
            self.assertIn("travel_home_address", travel.next_trip_reply().text)

    def test_no_reminder_without_key(self):
        self.assertIsNone(travel.SKILL.start())

    def test_reminder_starts_with_key(self):
        with mock.patch.object(config, "ORS_KEY", "key"), \
                mock.patch.object(travel, "service", lambda: make_service()), \
                mock.patch("backend.assistant.skills.travel.reminder.TravelReminder.start", return_value="stop"):
            self.assertEqual(travel.SKILL.start(), "stop")

    def test_real_service_wiring(self):
        service = travel.service()
        self.assertIsNone(service.ors)    # ohne Keys
        self.assertIsNone(service.rail)
        self.assertIsNone(service.fuel)
        self.assertIsNotNone(service.calendar)


if __name__ == "__main__":
    unittest.main()
