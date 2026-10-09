import logging
import threading
import unittest

from backend.events import EventBus


class EventBusTest(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.received = []

    def test_publish_reaches_all_subscribers(self):
        self.bus.subscribe(lambda name, payload: self.received.append(("a", name, payload)))
        self.bus.subscribe(lambda name, payload: self.received.append(("b", name, payload)))
        self.bus.publish("ping", {"x": 1})
        self.assertEqual(self.received, [("a", "ping", {"x": 1}), ("b", "ping", {"x": 1})])

    def test_unsubscribe(self):
        unsubscribe = self.bus.subscribe(lambda name, payload: self.received.append(name))
        unsubscribe()
        unsubscribe()   # zweimal abmelden ist harmlos
        self.bus.publish("ping")
        self.assertEqual(self.received, [])

    def test_failing_handler_does_not_stop_others(self):
        def broken(name, payload):
            raise RuntimeError("kaputt")

        self.bus.subscribe(broken)
        self.bus.subscribe(lambda name, payload: self.received.append(name))
        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)
        self.bus.publish("ping")
        self.assertEqual(self.received, ["ping"])

    def test_publish_from_other_thread(self):
        self.bus.subscribe(lambda name, payload: self.received.append(name))
        thread = threading.Thread(target=self.bus.publish, args=("ping",))
        thread.start()
        thread.join()
        self.assertEqual(self.received, ["ping"])


if __name__ == "__main__":
    unittest.main()
