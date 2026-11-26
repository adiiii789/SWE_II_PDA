import unittest

from backend.assistant.skills import Skill, start_triggers


class StartTriggersTest(unittest.TestCase):
    def test_starts_all_and_stops_all(self):
        events = []

        def start(name):
            def run():
                events.append(f"start {name}")
                return lambda: events.append(f"stop {name}")
            return run

        def broken():
            raise RuntimeError("kaputte Zugangsdaten")

        stop_all = start_triggers([Skill("a", "", start=start("a")), Skill("ohne", ""),
                                   Skill("kaputt", "", start=broken), Skill("leer", "", start=lambda: None),
                                   Skill("b", "", start=start("b"))])
        self.assertEqual(events, ["start a", "start b"])   # ein defekter Auslöser stoppt die anderen nicht
        stop_all()
        self.assertEqual(events[2:], ["stop a", "stop b"])


if __name__ == "__main__":
    unittest.main()
