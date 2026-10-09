import unittest

from backend import presenter
from backend.assistant import AssistantReply
from backend.events import ASSISTANT_MESSAGE, EventBus
from backend.views import HtmlView


class PresentTest(unittest.TestCase):
    def test_reply_with_view(self):
        self.assertEqual(presenter.present(AssistantReply("Hi", HtmlView("<b>x</b>"))),
                         {"text": "Hi", "html": "<b>x</b>"})

    def test_reply_without_view(self):
        self.assertEqual(presenter.present(AssistantReply("Hi")), {"text": "Hi", "html": None})


class PushTest(unittest.TestCase):
    def test_push_publishes_assistant_message(self):
        bus = EventBus()
        received = []
        bus.subscribe(lambda name, payload: received.append((name, payload)))
        presenter.push(AssistantReply("Guten Morgen!"), bus)
        self.assertEqual(received, [(ASSISTANT_MESSAGE, {"text": "Guten Morgen!", "html": None})])


if __name__ == "__main__":
    unittest.main()
