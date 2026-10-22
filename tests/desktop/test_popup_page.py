"""Ende-zu-Ende: echte Popup-Seite, echter Chat, gerenderte Ansicht im iframe wechselt."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.qt_helpers import qt_app, run_js, wait_until

from backend import api, presenter
from backend.assistant import AssistantReply
from backend.assistant.tools import Attachment
from backend.attachments import AttachmentStore
from backend.desktop.application import create_popup
from backend.views import TemplateView

SEND = """
  document.getElementById("message-input").value = %r;
  document.getElementById("input-form").requestSubmit();
"""
MESSAGES = "Array.from(document.querySelectorAll('.message')).map(e => e.className + ':' + e.textContent)"
ATTACHMENTS = """Array.from(document.querySelectorAll('.attachment')).map(row =>
  row.querySelector('.attachment-name').textContent + '|' + row.querySelector('.attachment-size').textContent
  + '|' + Array.from(row.querySelectorAll('button')).map(b => b.textContent).join(',')
  + (row.querySelector('.attachment-name b') ? '|HTML!' : ''))"""
CLICK = """Array.from(document.querySelectorAll('.attachment')).pop()
  .querySelectorAll('button').forEach(b => { if (b.textContent === %r) b.click(); });"""
IFRAME_HTML ="document.getElementById('view-frame').srcdoc"
IFRAME_SANDBOX = "document.getElementById('view-frame').getAttribute('sandbox')"


class PopupPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt_app()
        cls.popup = create_popup()
        cls.page = cls.popup.content.page()
        loaded = []
        cls.popup.content.loadFinished.connect(loaded.append)
        if not wait_until(lambda: loaded):
            raise TimeoutError("Popup-Seite nicht geladen")
        # Anfangszustand festhalten, bevor ein Test chattet (Seite wird geteilt).
        # Die Startansicht kommt asynchron vom Backend.
        if not wait_until(lambda: run_js(cls.page, IFRAME_HTML)):
            raise TimeoutError("Startansicht nicht gesetzt")
        cls.initial_html = run_js(cls.page, IFRAME_HTML)
        cls.initial_messages = run_js(cls.page, MESSAGES)

    @classmethod
    def tearDownClass(cls):
        cls.popup.content.close_bridge()
        cls.popup.content.deleteLater()
        qt_app().processEvents()

    def _send(self, text):
        count = len(run_js(self.page, MESSAGES))
        run_js(self.page, SEND % text)
        # Nutzernachricht + Antwort des Assistenten
        self.assertTrue(wait_until(lambda: len(run_js(self.page, MESSAGES)) >= count + 2))
        return run_js(self.page, MESSAGES)[-1]

    def test_starts_with_start_view_and_greeting(self):
        self.assertIn("Personal Digital Agent", self.initial_html)
        self.assertEqual(len(self.initial_messages), 1)
        self.assertIn("hilfe", self.initial_messages[0])

    def test_chat_command_switches_iframe_view(self):
        answer = self._send("system")
        self.assertEqual(answer, "message assistant:Hier sind die Systeminfos.")
        html = run_js(self.page, IFRAME_HTML)
        self.assertIn("<h2>System</h2>", html)
        self.assertIn("<td>Python</td>", html)

    def test_unknown_message_keeps_view(self):
        before = run_js(self.page, IFRAME_HTML)
        answer = self._send("blabla")
        self.assertIn("blabla", answer)
        self.assertEqual(run_js(self.page, IFRAME_HTML), before)

    def test_render_view_is_callable_from_javascript(self):
        script = "render_view({html: '<b>x</b>'}).then(h => window._rendered = h)"
        run_js(self.page, script)
        self.assertTrue(wait_until(lambda: run_js(self.page, "window._rendered") == "<b>x</b>"))

    def test_pushed_assistant_message_is_shown(self):
        # Autonomer Ablauf: Backend schickt eine Nachricht ohne Nutzereingabe.
        count = len(run_js(self.page, MESSAGES))
        presenter.push(AssistantReply("Guten Morgen!", TemplateView("default", {"title": "Briefing"})))
        self.assertTrue(wait_until(lambda: len(run_js(self.page, MESSAGES)) == count + 1))
        self.assertEqual(run_js(self.page, MESSAGES)[-1], "message assistant:Guten Morgen!")
        self.assertTrue(wait_until(lambda: "<h2>Briefing</h2>" in run_js(self.page, IFRAME_HTML)))

    def test_attachments_can_be_opened_and_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, downloads = Path(tmp) / "anhaenge", Path(tmp) / "Downloads"
            base.mkdir()
            (base / "plan.pdf").write_bytes(b"PDF")
            store = AttachmentStore(base, downloads, opener=mock.Mock())
            # Name wie aus einer fremden Mail: darf nicht als HTML im Chat landen
            reply = AssistantReply("Hier ist der Anhang", attachments=(
                Attachment("<b>plan</b>.pdf", (base / "plan.pdf").as_uri()),))
            with mock.patch.object(presenter, "attachment_store", return_value=store), \
                    mock.patch.object(api, "attachment_store", return_value=store):
                presenter.push(reply)
                self.assertTrue(wait_until(lambda: run_js(self.page, ATTACHMENTS)))
                self.assertEqual(run_js(self.page, ATTACHMENTS)[-1], "📎 <b>plan</b>.pdf|3 B|Öffnen,Speichern")

                run_js(self.page, CLICK % "Öffnen")
                self.assertTrue(wait_until(lambda: store.opener.called))
                store.opener.assert_called_once_with((base / "plan.pdf").resolve())

                run_js(self.page, CLICK % "Speichern")
                self.assertTrue(wait_until(lambda: "Gespeichert unter" in run_js(self.page, MESSAGES)[-1]))
                self.assertEqual((downloads / "plan.pdf").read_bytes(), b"PDF")

    def test_iframe_is_sandboxed_without_same_origin(self):
        self.assertEqual(run_js(self.page, IFRAME_SANDBOX), "allow-scripts")


if __name__ == "__main__":
    unittest.main()
