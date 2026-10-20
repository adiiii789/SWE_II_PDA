"""E-Mails per SMTP senden - nur an Empfänger, die der Nutzer vorher freigegeben hat.

Einstellungen kommen aus Umgebungsvariablen oder aus der Datei mcp_servers/.env
(Vorlage: .env.example; die .env steht in .gitignore, das Passwort landet so nicht im Repo):

  PDA_SMTP_HOST         z. B. smtp.gmail.com
  PDA_SMTP_PORT         587 (STARTTLS, Standard) oder 465 (SSL)
  PDA_SMTP_USER         Login, meist die eigene Adresse
  PDA_SMTP_PASSWORD     bei Gmail ein App-Passwort, nicht das normale Passwort
  PDA_MAIL_FROM         Absender (Standard: PDA_SMTP_USER)
  PDA_MAIL_RECIPIENTS   erlaubte Empfänger, durch Komma getrennt; der erste ist der Standard

Warum eine Freigabeliste? Das Sprachmodell entscheidet selbst, wann es das
Werkzeug aufruft. Text aus Mails, Webseiten oder Tool-Ergebnissen könnte es dazu
bringen, an fremde Adressen zu schreiben. Die Liste begrenzt das auf Adressen, die
du selbst eingetragen hast. Seit der Assistent Mails lesen kann (inbox.py), landet
fremder Text regelmäßig beim Modell - die Liste ist dann der eigentliche Schutz.
"""
from __future__ import annotations

import os
import smtplib
from collections.abc import Mapping
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path

ENV_FILE = Path(__file__).with_name(".env")
MAX_BODY_CHARS = 20_000


class MailError(ValueError):
    """Mail nicht konfiguriert, Empfänger nicht erlaubt oder Versand fehlgeschlagen."""


@dataclass(frozen=True)
class MailSettings:
    host: str
    port: int
    user: str
    password: str
    sender: str
    recipients: tuple[str, ...]

    @classmethod
    def load(cls, environ: Mapping[str, str] = os.environ, env_file: Path = ENV_FILE) -> MailSettings:
        values = {**read_env_file(env_file), **{k: v for k, v in environ.items() if k.startswith("PDA_")}}
        missing = [key for key in ("PDA_SMTP_HOST", "PDA_SMTP_USER", "PDA_SMTP_PASSWORD", "PDA_MAIL_RECIPIENTS")
                   if not values.get(key)]
        if missing:
            raise MailError(f"Mailversand ist nicht eingerichtet, es fehlt: {', '.join(missing)} "
                            f"(Umgebungsvariablen oder {env_file})")
        return cls(
            host=values["PDA_SMTP_HOST"],
            port=int(values.get("PDA_SMTP_PORT") or 587),
            user=values["PDA_SMTP_USER"],
            password=values["PDA_SMTP_PASSWORD"],
            sender=values.get("PDA_MAIL_FROM") or values["PDA_SMTP_USER"],
            recipients=tuple(a.strip() for a in values["PDA_MAIL_RECIPIENTS"].split(",") if a.strip()),
        )


def read_env_file(path: Path) -> dict[str, str]:
    """KEY=VALUE pro Zeile; leere Zeilen und # Kommentare werden ignoriert."""
    if not path.exists():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def send_email(settings: MailSettings, to: str, subject: str, body: str) -> str:
    """Mail senden. to leer = Standardempfänger. Gibt eine Bestätigung zurück."""
    to = (to or settings.recipients[0]).strip()
    allowed = {address.lower() for address in settings.recipients}
    if to.lower() not in allowed:
        raise MailError(f"{to!r} ist kein freigegebener Empfänger. Erlaubt: {', '.join(settings.recipients)}")
    if not subject.strip() or not body.strip():
        raise MailError("Betreff und Text dürfen nicht leer sein")
    if len(body) > MAX_BODY_CHARS:
        raise MailError(f"Text zu lang (höchstens {MAX_BODY_CHARS} Zeichen)")

    message = EmailMessage()
    message["From"] = settings.sender
    message["To"] = to
    message["Subject"] = subject.strip()
    message.set_content(body)

    # smtplib stellt sich sonst mit dem Rechnernamen vor (EHLO). Enthält der Umlaute
    # (z. B. "Gergö-PC"), scheitert das, weil SMTP-Befehle nur ASCII erlauben.
    hostname = "localhost"
    try:
        if settings.port == 465:
            with smtplib.SMTP_SSL(settings.host, settings.port, local_hostname=hostname, timeout=30) as smtp:
                smtp.login(settings.user, settings.password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(settings.host, settings.port, local_hostname=hostname, timeout=30) as smtp:
                smtp.starttls()
                smtp.login(settings.user, settings.password)
                smtp.send_message(message)
    except (smtplib.SMTPException, OSError) as error:
        raise MailError(f"Versand fehlgeschlagen: {error}") from None
    return f"E-Mail an {to} gesendet (Betreff: {subject.strip()})"
