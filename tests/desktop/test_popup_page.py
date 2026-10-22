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
RECORD = "document.getElementById('record-button').click()"
RECORD_LABEL = "document.getElementById('record-button').textContent"
ESCAPE = "document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape'}))"


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

    def _patch_speech(self):
        """Attrappen statt Mikrofon und Lautsprecher; das Frontend hält beides für verfügbar."""
        speech_input, speech_output = mock.Mock(), mock.Mock()
        for name, value in (("_speech_input", speech_input), ("_speech_output", speech_output)):
            patcher = mock.patch.object(api, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        run_js(self.page, "speech = {input: true, output: true}")
        return speech_input, speech_output

    def test_voice_message_is_sent_and_reply_spoken(self):
        speech_input, speech_output = self._patch_speech()
        speech_input.stop.return_value = "system"
        count = len(run_js(self.page, MESSAGES))
        run_js(self.page, RECORD)
        self.assertTrue(wait_until(lambda: speech_input.start.called))
        self.assertEqual(run_js(self.page, RECORD_LABEL), "⏹")

        run_js(self.page, RECORD)   # zweiter Klick: beenden, erkennen, senden
        self.assertTrue(wait_until(lambda: len(run_js(self.page, MESSAGES)) >= count + 2))
        self.assertEqual(run_js(self.page, MESSAGES)[-2:],
                         ["message user:system", "message assistant:Hier sind die Systeminfos."])
        self.assertTrue(wait_until(lambda: speech_output.speak.called))
        speech_output.speak.assert_called_once_with("Hier sind die Systeminfos.")
        self.assertTrue(wait_until(lambda: run_js(self.page, RECORD_LABEL) == "🎤"))

    def test_escape_cancels_recording(self):
        speech_input, _speech_output = self._patch_speech()
        count = len(run_js(self.page, MESSAGES))
        run_js(self.page, RECORD)
        self.assertTrue(wait_until(lambda: speech_input.start.called))
        run_js(self.page, ESCAPE)
        self.assertTrue(wait_until(lambda: speech_input.cancel.called))
        self.assertEqual(run_js(self.page, RECORD_LABEL), "🎤")
        speech_input.stop.assert_not_called()
        self.assertEqual(len(run_js(self.page, MESSAGES)), count)

    def test_iframe_is_sandboxed_without_same_origin(self):
        self.assertEqual(run_js(self.page, IFRAME_SANDBOX), "allow-scripts")

    def test_reply_markdown_and_formulas_are_rendered(self):
        html = run_js(self.page, "renderMarkdown(%r)" % "## Titel\n\n**fett**, `code` und $\\frac{1}{2}$\n\n- a\n- b")
        self.assertIn("<h2>Titel</h2>", html)
        self.assertIn("<strong>fett</strong>", html)
        self.assertIn("<code>code</code>", html)
        self.assertIn('class="katex"', html)
        self.assertIn("<li>a</li>", html)

    def test_dollar_amounts_and_code_stay_text(self):
        html = run_js(self.page, "renderMarkdown(%r)" % "5 $ und 10 $, `echo $HOME`")
        self.assertNotIn("katex", html)
        self.assertIn("<code>echo $HOME</code>", html)

    def test_reply_html_is_sanitized(self):
        html = run_js(self.page, "renderMarkdown(%r)" % (
            '<img src=x onerror="alert(1)"> <script>alert(2)</script> [x](javascript:alert(3)) '
            '![bild](https://example.com/p.png) $\\href{javascript:alert(4)}{a}$'))
        for forbidden in ("<img", "<script", "onerror", "javascript:"):
            self.assertNotIn(forbidden, html)

    def test_many_long_messages_are_not_squeezed_and_scroll(self):
        run_js(self.page, "scrollToBottom(); onChatScroll()")
        run_js(self.page, "for (let i = 0; i < 40; i++) addMessage('Zeile\n'.repeat(8) + '`x`', 'assistant')")
        heights = run_js(self.page, "Array.from(document.querySelectorAll('.message.assistant')).slice(-40)"
                                    ".map(e => e.offsetHeight)")
        self.assertTrue(all(h >= 8 * 14 for h in heights), heights)
        self.assertTrue(run_js(self.page, "isNearBottom()"))
        self.assertTrue(run_js(self.page, "document.getElementById('scroll-down-button').hidden"))

    def test_scrolled_up_reader_is_not_pulled_down(self):
        run_js(self.page, "for (let i = 0; i < 30; i++) addMessage('Nachricht ' + i, 'assistant')")
        run_js(self.page, "chatHistory.scrollTop = 0; onChatScroll()")
        run_js(self.page, "addMessage('neu', 'assistant')")
        self.assertEqual(run_js(self.page, "chatHistory.scrollTop"), 0)
        self.assertFalse(run_js(self.page, "document.getElementById('scroll-down-button').hidden"))
        run_js(self.page, "document.getElementById('scroll-down-button').click()")
        self.assertTrue(run_js(self.page, "isNearBottom()"))

    def test_long_reply_is_shown_from_its_start(self):
        run_js(self.page, "scrollToBottom(); showReply({text: 'Anfang\n\n' + 'Absatz\n\n'.repeat(200)})")
        visible = run_js(self.page, """(() => { const m = Array.from(document.querySelectorAll('.message')).pop();
          return m.offsetTop >= chatHistory.scrollTop && m.offsetTop < chatHistory.scrollTop + 10; })()""")
        self.assertTrue(visible)

    def test_chat_maximize_hides_view(self):
        frame_display = "getComputedStyle(document.getElementById('view-frame')).display"
        run_js(self.page, "document.getElementById('chat-max-button').click()")
        self.assertEqual(run_js(self.page, frame_display), "none")
        run_js(self.page, "document.getElementById('chat-max-button').click()")
        self.assertNotEqual(run_js(self.page, frame_display), "none")


if __name__ == "__main__":
    unittest.main()
