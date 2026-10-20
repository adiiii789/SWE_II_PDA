"""mcp_servers/mailer.py: Einstellungen, Freigabeliste und Versand - ohne echten SMTP-Server."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend import config

sys.path.insert(0, str(config.ROOT_DIR / "mcp_servers"))
import mailer  # noqa: E402

ENV = {"PDA_SMTP_HOST": "smtp.example.com", "PDA_SMTP_USER": "ich@example.com",
       "PDA_SMTP_PASSWORD": "geheim", "PDA_MAIL_RECIPIENTS": "max@example.com, Anna@Example.com"}
NO_FILE = Path("gibt/es/nicht/.env")


class SettingsTest(unittest.TestCase):
    def test_from_environment(self):
        settings = mailer.MailSettings.load(ENV, NO_FILE)
        self.assertEqual(settings.port, 587)
        self.assertEqual(settings.sender, "ich@example.com")
        self.assertEqual(settings.recipients, ("max@example.com", "Anna@Example.com"))

    def test_from_env_file_environment_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text('# Kommentar\n\nPDA_SMTP_HOST="datei.example.com"\nPDA_SMTP_PORT=465\n'
                            "PDA_SMTP_USER=datei@example.com\nPDA_SMTP_PASSWORD=x\n"
                            "PDA_MAIL_RECIPIENTS=a@example.com\nKEIN_GLEICHHEITSZEICHEN\n", encoding="utf-8")
            settings = mailer.MailSettings.load({"PDA_SMTP_USER": "env@example.com", "PATH": "x"}, path)
        self.assertEqual((settings.host, settings.port, settings.user), ("datei.example.com", 465, "env@example.com"))

    def test_missing_settings(self):
        with self.assertRaisesRegex(mailer.MailError, "PDA_SMTP_PASSWORD, PDA_MAIL_RECIPIENTS"):
            mailer.MailSettings.load({"PDA_SMTP_HOST": "h", "PDA_SMTP_USER": "u"}, NO_FILE)


class SendTest(unittest.TestCase):
    def setUp(self):
        self.settings = mailer.MailSettings.load(ENV, NO_FILE)

    def _send(self, to="", subject="Hallo", body="Text", port=None):
        settings = self.settings if port is None else mailer.MailSettings(**{**self.settings.__dict__, "port": port})
        with mock.patch("smtplib.SMTP") as smtp, mock.patch("smtplib.SMTP_SSL") as smtp_ssl:
            result = mailer.send_email(settings, to, subject, body)
        return result, smtp.return_value.__enter__.return_value, smtp_ssl.return_value.__enter__.return_value

    def test_default_recipient_with_starttls(self):
        result, smtp, _ = self._send(body="Ich komme später.")
        self.assertEqual(result, "E-Mail an max@example.com gesendet (Betreff: Hallo)")
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with("ich@example.com", "geheim")
        message = smtp.send_message.call_args.args[0]
        self.assertEqual((message["From"], message["To"], message["Subject"]),
                         ("ich@example.com", "max@example.com", "Hallo"))
        self.assertIn("Ich komme später.", message.get_content())

    def test_ascii_hostname_for_ehlo(self):
        # Rechnernamen mit Umlaut (z. B. "Gergö-PC") dürfen nicht im EHLO landen.
        with mock.patch("smtplib.SMTP") as smtp:
            mailer.send_email(self.settings, "", "Hi", "Text")
        smtp.assert_called_once_with("smtp.example.com", 587, local_hostname="localhost", timeout=30)

    def test_allowed_recipient_case_insensitive(self):
        result, smtp, _ = self._send(to="anna@example.com")
        self.assertIn("anna@example.com", result)

    def test_ssl_port(self):
        _, smtp, smtp_ssl = self._send(port=465)
        smtp_ssl.send_message.assert_called_once()
        smtp.send_message.assert_not_called()

    def test_foreign_recipient_is_refused(self):
        with mock.patch("smtplib.SMTP") as smtp:
            with self.assertRaisesRegex(mailer.MailError, "kein freigegebener Empfänger"):
                mailer.send_email(self.settings, "fremd@evil.example", "Hi", "Text")
        smtp.assert_not_called()

    def test_empty_or_too_long(self):
        with self.assertRaisesRegex(mailer.MailError, "nicht leer"):
            mailer.send_email(self.settings, "", " ", "Text")
        with self.assertRaisesRegex(mailer.MailError, "zu lang"):
            mailer.send_email(self.settings, "", "Hi", "x" * (mailer.MAX_BODY_CHARS + 1))

    def test_smtp_error(self):
        with mock.patch("smtplib.SMTP", side_effect=OSError("Verbindung abgelehnt")):
            with self.assertRaisesRegex(mailer.MailError, "Versand fehlgeschlagen: Verbindung abgelehnt"):
                mailer.send_email(self.settings, "", "Hi", "Text")


if __name__ == "__main__":
    unittest.main()
