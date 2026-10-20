import tempfile
import unittest
from pathlib import Path

from backend import presenter
from backend.assistant import AssistantReply
from backend.assistant.tools import Attachment
from backend.attachments import AttachmentStore
from backend.events import ASSISTANT_MESSAGE, EventBus
from backend.views import HtmlView


class PresentTest(unittest.TestCase):
    def test_reply_with_view(self):
        self.assertEqual(presenter.present(AssistantReply("Hi", HtmlView("<b>x</b>"))),
                         {"text": "Hi", "html": "<b>x</b>", "attachments": []})

    def test_reply_without_view(self):
        self.assertEqual(presenter.present(AssistantReply("Hi")), {"text": "Hi", "html": None, "attachments": []})

    def test_attachments_are_registered_and_foreign_files_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "plan.pdf").write_bytes(b"PDF")
            store = AttachmentStore(base, base / "Downloads")
            reply = AssistantReply("Hier", attachments=(Attachment("plan.pdf", (base / "plan.pdf").as_uri()),
                                                        Attachment("hosts", "file:///C:/Windows/System32/hosts")))
            result = presenter.present(reply, store)
        self.assertEqual([entry["name"] for entry in result["attachments"]], ["plan.pdf"])


class PushTest(unittest.TestCase):
    def test_push_publishes_assistant_message(self):
        bus = EventBus()
        received = []
        bus.subscribe(lambda name, payload: received.append((name, payload)))
        presenter.push(AssistantReply("Guten Morgen!"), bus)
        self.assertEqual(received, [(ASSISTANT_MESSAGE, {"text": "Guten Morgen!", "html": None, "attachments": []})])


if __name__ == "__main__":
    unittest.main()
