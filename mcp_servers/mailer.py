"""E-Mails per SMTP senden - nur an Empfänger, die der Nutzer vorher freigegeben hat.

Einstellungen kommen aus Umgebungsvariablen oder aus der Datei mcp_servers/.env
(Vorlage: .env.example; die .env steht in .gitignore, das Passwort landet so nicht im Repo):

  PDA_SMTP_HOST         z. B. smtp.gmail.com
  PDA_SMTP_PORT         587 (STARTTLS, Standard) oder 465 (SSL)
  PDA_SMTP_USER         Login, meist die eigene Adresse
  PDA_SMTP_PASSWORD     bei Gmail ein App-Passwort, nicht das normale Passwort
  PDA_MAIL_FROM         Absender (Standard: PDA_SMTP_USER)
  PDA_MAIL_RECIPIENTS   erlaubte Empfänger, durch Komma getrennt; der erste ist der Standard.
                        Mit Namen als Kontakt: Mama <mama@example.com>, "Müller, Anna" <anna@example.com>
                        Dann reicht beim Senden der Name ("Mama", "anna müller" oder "Anna").

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
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import getaddresses
from pathlib import Path

ENV_FILE = Path(__file__).with_name(".env")
MAX_BODY_CHARS = 20_000


class MailError(ValueError):
    """Mail nicht konfiguriert, Empfänger nicht erlaubt oder Versand fehlgeschlagen."""


@dataclass(frozen=True)
class Contact:
    name: str  # leer, wenn nur die Adresse eingetragen ist
    address: str

    def header(self) -> Address:
        return Address(display_name=self.name, addr_spec=self.address)

    def __str__(self) -> str:
        return str(self.header())


@dataclass(frozen=True)
class MailSettings:
    host: str
    port: int
    user: str
    password: str
    sender: str
    contacts: tuple[Contact, ...]

    @property
    def recipients(self) -> tuple[str, ...]:
        return tuple(contact.address for contact in self.contacts)

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
            contacts=parse_contacts(values["PDA_MAIL_RECIPIENTS"]),
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


def parse_contacts(text: str) -> tuple[Contact, ...]:
    """'Mama <mama@example.com>, max@example.com' -> Kontakte. Namen mit Komma in Anführungszeichen."""
    contacts = tuple(Contact(name.strip(), address.strip()) for name, address in getaddresses([text])
                     if "@" in address)
    if not contacts:
        raise MailError(f"PDA_MAIL_RECIPIENTS enthält keine gültige Adresse: {text!r}")
    return contacts


def find_contact(settings: MailSettings, to: str) -> Contact:
    """Empfänger über Adresse oder Namen finden - nur unter den freigegebenen Kontakten.

    to leer = Standardempfänger. Ein Name passt, wenn er vollständig übereinstimmt (ohne
    Groß-/Kleinschreibung, Reihenfolge egal: "Anna Müller" = "Müller, Anna") oder wenn alle
    angegebenen Wörter im Namen vorkommen ("Anna") und das nur auf einen Kontakt zutrifft.
    """
    to = to.strip()
    if not to:
        return settings.contacts[0]
    name, address = getaddresses([to])[0] if "@" in to else ("", "")
    if address:
        for contact in settings.contacts:
            if contact.address.lower() == address.lower():
                return contact
    else:
        wanted = _words(to)
        exact = [c for c in settings.contacts if c.name and _words(c.name) == wanted]
        partial = [c for c in settings.contacts if c.name and wanted and wanted <= _words(c.name)]
        matches = exact or partial
        if len(matches) == 1:
            return matches[0]
        if matches:
            raise MailError(f"{to!r} ist nicht eindeutig: {', '.join(map(str, matches))}. Bitte genauer angeben.")
    allowed = ", ".join(map(str, settings.contacts))
    raise MailError(f"{to!r} ist kein freigegebener Empfänger. Erlaubt: {allowed}")


def _words(name: str) -> frozenset[str]:
    return frozenset(name.replace(",", " ").casefold().split())


def send_email(settings: MailSettings, to: str, subject: str, body: str) -> str:
    """Mail senden. to = Adresse oder Name eines Kontakts, leer = Standardempfänger."""
    contact = find_contact(settings, to)
    if not subject.strip() or not body.strip():
        raise MailError("Betreff und Text dürfen nicht leer sein")
    if len(body) > MAX_BODY_CHARS:
        raise MailError(f"Text zu lang (höchstens {MAX_BODY_CHARS} Zeichen)")

    message = EmailMessage()
    message["From"] = settings.sender
    message["To"] = contact.header()
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
    return f"E-Mail an {contact} gesendet (Betreff: {subject.strip()})"
