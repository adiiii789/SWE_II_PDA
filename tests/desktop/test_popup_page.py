"""Ende-zu-Ende: echte Popup-Seite, echter Chat, gerenderte Ansicht im iframe wechselt."""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from PyQt5.QtCore import QPoint, Qt

from tests.assistant.test_settings import MemoryStore
from tests.qt_helpers import qt_app, run_js, wait_until

from backend import api, presenter, proactive
from backend.assistant import AssistantReply
from backend.assistant.tools import Attachment
from backend.attachments import AttachmentStore
from backend.assistant.settings import AssistantSettings
from backend.desktop.application import create_popup
from backend.events import events
from backend.startup import Startup, Step
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
ALERT_THERE = "Boolean(document.getElementById('proactive-alert'))"
ALERT_OPEN = "Boolean(document.querySelector('#proactive-alert.open'))"
ALERT_TITLE = "document.querySelector('.alert-title').textContent"
ALERT_BODY = "document.querySelector('.alert-body').innerHTML"
ALERT_MORE_HIDDEN = "document.querySelector('.alert-more').hidden"
ALERT_CLICK = "document.getElementById('proactive-alert').click()"
LAST_VISIBILITY = "getComputedStyle(Array.from(document.querySelectorAll('.message')).pop()).visibility"


LOADER_THERE = "Boolean(document.getElementById('loading-screen'))"
LOADER_STEP = "document.getElementById('loading-step').textContent"
INPUT_DISABLED = "document.getElementById('message-input').disabled"
# Jede Szene bei Start, nach langer Zeit (Gameboy spielt bis zum Überlauf) und in allen Fortschritts-Zuständen
DRAW_ALL_SCENES = """(() => {
  const broken = [], canvas = document.createElement('canvas'); canvas.width = 576; canvas.height = 648;
  const c = canvas.getContext('2d'), labels = ['Eins', 'Zwei', 'Drei'];
  for (const id of LoadingScenes.ids) {
    try {
      const scene = LoadingScenes.get(id), state = scene.start ? scene.start(576, 648) : {};
      for (const [t, p, index] of [[0, 0, 0], [3.3, 0.5, 1], [47, 1, 3], [90, 1, 3], [130, 1, 3]]) {
        scene.draw(c, 576, 648, t, state, {progress: p, smooth: p, index, total: 3, labels, label: index < 3 ? labels[index] : ''});
      }
    } catch (error) { broken.push(id + ': ' + error.message); }
  }
  return broken;
})()"""


class LoadingScreenTest(unittest.TestCase):
    def setUp(self):
        qt_app()
        self.release = threading.Event()
        self.addCleanup(self.release.set)
        steps = [Step("Einstellungen", lambda: None), Step("Modell", self.release.wait, skippable=True)]
        patcher = mock.patch.object(api, "_startup", return_value=Startup(steps, events))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.popup = create_popup()
        self.page = self.popup.content.page()
        self.addCleanup(self._close)
        loaded = []
        self.popup.content.loadFinished.connect(loaded.append)
        self.assertTrue(wait_until(lambda: loaded, 40))
        self.popup.setAttribute(Qt.WA_DontShowOnScreen, True)
        self.popup.show_at(QPoint(1500, 900))
        self.assertTrue(wait_until(lambda: run_js(self.page, LOADER_STEP) == "Modell …"))

    def _close(self):
        self.popup.content.close_bridge()
        self.popup.content.deleteLater()
        qt_app().processEvents()

    def test_covers_page_until_backend_is_ready(self):
        self.assertTrue(run_js(self.page, INPUT_DISABLED))
        self.assertFalse(run_js(self.page, "LoadingScreen.ready"))
        self.assertEqual(run_js(self.page, "document.getElementById('model-select').options.length"), 0)
        self.release.set()
        self.assertTrue(wait_until(lambda: run_js(self.page, "LoadingScreen.ready")))
        self.assertTrue(wait_until(lambda: not run_js(self.page, LOADER_THERE)))
        self.assertFalse(run_js(self.page, INPUT_DISABLED))

    def test_skip_frees_input_while_model_is_still_loading(self):
        run_js(self.page, "document.getElementById('loading-skip').click()")
        self.assertTrue(wait_until(lambda: not run_js(self.page, LOADER_THERE)))
        self.assertFalse(run_js(self.page, INPUT_DISABLED))

    def test_every_design_has_a_scene_that_draws(self):
        self.assertEqual(run_js(self.page, DRAW_ALL_SCENES), [])
        themes = run_js(self.page, "THEMES.map(theme => theme.id)")
        self.assertEqual(sorted(run_js(self.page, "LoadingScenes.ids")), sorted(themes))


class PopupPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        qt_app()
        cls.popup = create_popup()
        cls.page = cls.popup.content.page()
        loaded = []
        cls.popup.content.loadFinished.connect(loaded.append)
        # Großzügig: Laufen vorher Tests mit eigenem Chromium (test_application), dauert das Laden länger.
        if not wait_until(lambda: loaded, 40):
            raise TimeoutError("Popup-Seite nicht geladen")
        if not wait_until(lambda: not run_js(cls.page, "LoadingScreen.visible"), 20):
            raise TimeoutError("Ladebildschirm nicht verschwunden")
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

    def test_proactive_message_is_marked_in_chat(self):
        # Der PDA meldet sich von selbst (Test-Makro) - ohne Sprachmodell mit dem Ersatztext.
        demo = proactive.OCCASIONS[proactive.DEMO]
        count = len(run_js(self.page, MESSAGES))
        with mock.patch.object(api.config, "PROACTIVE_SPEAK", False):
            api.proactive_message("demo")
        self.assertTrue(wait_until(lambda: len(run_js(self.page, MESSAGES)) == count + 1))
        last = run_js(self.page, MESSAGES)[-1]
        self.assertTrue(last.startswith(f"message assistant proactive:🔔 {demo.title} · "), last)
        self.assertTrue(last.endswith(demo.fallback), last)
        self.assertTrue(wait_until(lambda: f"<h2>{demo.title}</h2>" in run_js(self.page, IFRAME_HTML)))

    def test_proactive_alert_waits_until_popup_is_opened(self):
        run_js(self.page, "showReply({text: 'Hallo', proactive: true, title: 'Termin'})")
        self.assertFalse(run_js(self.page, ALERT_THERE))   # Popup zu: noch nichts zu sehen
        self.assertEqual(run_js(self.page, LAST_VISIBILITY), "hidden")

        run_js(self.page, "Object.defineProperty(document, 'hidden', {configurable: true, get: () => false})")
        self.addCleanup(run_js, self.page, "delete document.hidden")
        run_js(self.page, "document.dispatchEvent(new Event('visibilitychange'))")
        self.assertTrue(wait_until(lambda: run_js(self.page, ALERT_THERE)))
        run_js(self.page, ALERT_CLICK)
        self.assertTrue(wait_until(lambda: not run_js(self.page, ALERT_THERE)))
        self.assertEqual(run_js(self.page, LAST_VISIBILITY), "visible")

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
        # \\n: der Zeilenumbruch muss im JavaScript-String als Escape ankommen, sonst ist das Skript ungültig
        run_js(self.page, "scrollToBottom(); showReply({text: 'Anfang\\n\\n' + 'Absatz\\n\\n'.repeat(200)})")
        self.assertTrue(run_js(self.page, "Array.from(document.querySelectorAll('.message')).pop().textContent.startsWith('Anfang')"))
        visible = run_js(self.page, """(() => { const m = Array.from(document.querySelectorAll('.message')).pop();
          return m.offsetTop >= chatHistory.scrollTop && m.offsetTop < chatHistory.scrollTop + 10; })()""")
        self.assertTrue(visible)

    def test_chat_maximize_hides_view(self):
        frame_display = "getComputedStyle(document.getElementById('view-frame')).display"
        run_js(self.page, "document.getElementById('chat-max-button').click()")
        self.assertEqual(run_js(self.page, frame_display), "none")
        run_js(self.page, "document.getElementById('chat-max-button').click()")
        self.assertNotEqual(run_js(self.page, frame_display), "none")

    def test_chat_maximize_after_dragging_splitter_fills_height(self):
        # Nach dem Ziehen hat der Chat flex-grow < 1 - allein muss er trotzdem die ganze Höhe bekommen,
        # sonst rutscht er beim Ausblenden der Ansicht nach oben.
        chat_grow = "getComputedStyle(document.getElementById('chat-panel')).flexGrow"
        run_js(self.page, "setSplit(0.4)")
        try:
            run_js(self.page, "document.getElementById('chat-max-button').click()")
            self.assertEqual(run_js(self.page, chat_grow), "1")
            run_js(self.page, "document.getElementById('chat-max-button').click()")
            self.assertEqual(run_js(self.page, chat_grow), "0.6")   # Aufteilung gilt wieder
        finally:
            run_js(self.page, "setSplit(null)")


class ProactiveAlertTest(unittest.TestCase):
    """Große Einblendung (frontend/proactive_alert.js) - im geöffneten Popup, damit die Seite ihre echte
    Größe hat. Klick beendet jeweils die 10 Sekunden Lesezeit."""

    @classmethod
    def setUpClass(cls):
        PopupPageTest.setUpClass.__func__(cls)
        cls.popup.setAttribute(Qt.WA_DontShowOnScreen, True)
        cls.popup.show_at(QPoint(1500, 900))
        if not wait_until(lambda: not run_js(cls.page, "document.hidden") and run_js(cls.page, "innerHeight") > 300):
            raise TimeoutError("Popup nicht geöffnet")

    @classmethod
    def tearDownClass(cls):
        PopupPageTest.tearDownClass.__func__(cls)

    def js(self, script):
        return run_js(self.page, script)

    def wait_open(self):
        self.assertTrue(wait_until(lambda: self.js(ALERT_OPEN)))

    def dismiss(self):
        self.js(ALERT_CLICK)
        self.assertTrue(wait_until(lambda: not self.js(ALERT_THERE)))

    def test_shows_mark_then_message_then_lands_in_chat(self):
        self.js("showReply({text: '**Hallo** Welt', proactive: true, title: '<b>Termin</b>'})")
        count = len(self.js(MESSAGES))
        self.assertTrue(self.js(ALERT_THERE))
        self.assertEqual(self.js("document.querySelector('.alert-mark').textContent"), "!")
        self.assertFalse(self.js(ALERT_OPEN))    # erst nur das Ausrufezeichen
        self.assertEqual(self.js(LAST_VISIBILITY), "hidden")

        self.wait_open()
        self.assertEqual(self.js(ALERT_TITLE), "<b>Termin</b>")   # als Text, nicht als HTML
        self.assertIn("<strong>Hallo</strong>", self.js(ALERT_BODY))
        self.assertTrue(self.js(ALERT_MORE_HIDDEN))               # passt, also kein Verweis

        self.dismiss()
        self.assertEqual(len(self.js(MESSAGES)), count)           # die Nachricht bleibt im Chat
        self.assertEqual(self.js(LAST_VISIBILITY), "visible")

    def test_points_to_chat_when_text_does_not_fit(self):
        self.js("showReply({text: 'Absatz\\n\\n'.repeat(200), proactive: true, title: 'Lang'})")
        self.wait_open()
        self.assertFalse(self.js(ALERT_MORE_HIDDEN))
        self.dismiss()

    def test_works_without_animations_in_still_theme(self):
        # "Nachhaltig" schaltet alle Animationen ab - die Phasen müssen trotzdem durchlaufen.
        self.js("Appearance.applyTheme('eco', false)")
        self.addCleanup(self.js, "Appearance.applyTheme('night', false)")
        self.js("showReply({text: 'Hallo', proactive: true, title: 'Termin'})")
        mark = "getComputedStyle(document.querySelector('.alert-mark'))"
        self.assertEqual(self.js(f"{mark}.animationName"), "none")
        self.assertEqual(self.js(f"{mark}.opacity"), "1")
        self.wait_open()
        self.assertEqual(self.js(f"{mark}.opacity"), "0")
        self.assertEqual(self.js("getComputedStyle(document.querySelector('.alert-content')).opacity"), "1")
        self.dismiss()


class SettingsPanelTest(unittest.TestCase):
    """⚙ Einstellungen (frontend/settings.js) - Speicher im Arbeitsspeicher statt APPDATA."""

    @classmethod
    def setUpClass(cls):
        PopupPageTest.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        PopupPageTest.tearDownClass.__func__(cls)

    def setUp(self):
        self.store = MemoryStore()
        patcher = mock.patch.object(api, "_settings", return_value=AssistantSettings(self.store))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(run_js, self.page, "closeSettings()")

    def open(self):
        run_js(self.page, "document.getElementById('settings-button').click()")
        self.assertTrue(wait_until(lambda: run_js(self.page, "document.querySelectorAll('.setting').length") > 0))

    def js(self, script):
        return run_js(self.page, script)

    def test_panel_shows_answer_and_tool_settings(self):
        self.open()
        self.assertFalse(self.js("document.getElementById('settings-panel').hidden"))
        visible = "Array.from(document.querySelectorAll('.settings-section')).filter(s => !s.hidden).map(s => s.dataset.tab)"
        self.assertEqual(self.js(visible), ["answer"])
        self.assertEqual(self.js("document.querySelector('[data-key=length] select').value"), "kurz")
        self.js("document.querySelector('#settings-tabs [data-tab=tools]').click()")
        self.assertEqual(self.js(visible), ["tools"])
        groups = self.js("Array.from(document.querySelectorAll('.settings-group')).map(g => g.dataset.group)")
        self.assertEqual(groups[:2], ["mail", "basics"])
        mail_keys = self.js("Array.from(document.querySelectorAll('[data-group=mail] .setting')).map(r => r.dataset.key)")
        self.assertIn("fields", mail_keys)
        self.assertIn("max", mail_keys)

    def test_save_changes_and_confirm_in_chat(self):
        self.open()
        count = len(self.js(MESSAGES))
        self.js("""
          document.querySelector('[data-key=length] select').value = 'ausfuehrlich';
          document.querySelector('[data-group=mail] [data-key=max] input').value = '4';
          document.querySelector('[data-group=mail] [data-key=fields] input[value=preview]').click();
          document.querySelector('[data-group=basics] [data-key=enabled] input').click();
          document.getElementById('settings-save').click();""")
        self.assertTrue(wait_until(lambda: self.js("document.getElementById('settings-panel').hidden")))
        settings = AssistantSettings(self.store)
        self.assertEqual(settings.answer_values()["length"], "ausfuehrlich")
        self.assertEqual(settings.tool_values("list_emails")["max"], 4)
        self.assertEqual(settings.tool_values("list_emails")["fields"], ["sender", "subject", "date", "preview"])
        self.assertFalse(settings.tool_enabled("calculate"))
        self.assertTrue(wait_until(lambda: len(self.js(MESSAGES)) == count + 1))
        self.assertIn("Einstellungen gespeichert", self.js(MESSAGES)[-1])

    def test_invalid_value_keeps_panel_open_with_error(self):
        self.open()
        self.js("document.querySelector('[data-group=mail] [data-key=max] input').value = '500';"
                "document.getElementById('settings-save').click();")
        self.assertTrue(wait_until(lambda: "zwischen 1 und 50" in self.js("document.getElementById('settings-status').textContent")))
        self.assertFalse(self.js("document.getElementById('settings-panel').hidden"))
        self.assertEqual(self.store.values, {})

    def test_reset_needs_second_click(self):
        AssistantSettings(self.store).save(answer={"tone": "locker"})
        self.open()
        self.js("document.getElementById('settings-reset').click()")
        self.assertIn("Wirklich", self.js("document.getElementById('settings-reset').textContent"))
        self.assertEqual(AssistantSettings(self.store).answer_values()["tone"], "locker")
        self.js("document.getElementById('settings-reset').click()")
        self.assertTrue(wait_until(lambda: AssistantSettings(self.store).answer_values()["tone"] == "freundlich"))
        self.assertTrue(wait_until(lambda: self.js("document.querySelector('[data-key=tone] select').value") == "freundlich"))

    def test_disabled_group_is_greyed_and_escape_closes(self):
        self.open()
        self.js("document.querySelector('[data-group=mail] [data-key=enabled] input').click()")
        self.assertTrue(self.js("document.querySelector('[data-group=mail]').classList.contains('disabled')"))
        self.js("document.getElementById('settings-panel').dispatchEvent("
                "new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))")
        self.assertTrue(self.js("document.getElementById('settings-panel').hidden"))
        self.assertEqual(self.store.values, {})   # Schließen ohne Speichern


if __name__ == "__main__":
    unittest.main()
