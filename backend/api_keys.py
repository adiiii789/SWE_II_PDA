"""API-Keys und Zugangsdaten: alle in der lokalen .env (config.ENV_FILE), verwaltbar im Popup
unter ⚙ Einstellungen → Zugangsdaten.

Gelesen wird bei jedem Zugriff (get) - ein neuer Key gilt ab dem nächsten Aufruf, ohne Neustart.
Eine (nicht leere) Umgebungsvariable hat Vorrang vor der Datei.

Sicherheit:
- Werte gehen nie zurück ans Frontend: Das Formular erfährt nur, ob ein Key gesetzt ist und woher
  (status). Wer die Popup-Seite sieht, kann einen Key ersetzen oder löschen, aber nicht auslesen.
- Schreiben lassen sich nur die Namen aus KEYS, ohne Zeilenumbrüche und Steuerzeichen. So lässt
  sich über das Formular nichts anderes in die .env schmuggeln (z. B. PDA_MAIL_RECIPIENTS, die
  Liste erlaubter Mail-Empfänger).
- Geschrieben wird atomar (Datei daneben, dann ersetzen); auf macOS/Linux nur für den Nutzer
  lesbar (0600). Die .env ist in .gitignore. Fehlermeldungen nennen nie den Wert.
- Ein Key aus einer Umgebungsvariablen lässt sich hier nicht ändern (die Datei würde nie gelten).

Früher lagen manche Keys als Textdatei im App-Datenordner (z. B. gemini-api-key.txt).
migrate_legacy_files() übernimmt sie beim Start in die .env und löscht die Datei danach.
"""
from __future__ import annotations

import logging
import os
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend import config

log = logging.getLogger(__name__)

MAX_LENGTH = 1024


@dataclass(frozen=True)
class Key:
    name: str            # Name in der .env bzw. Umgebungsvariable
    label: str
    group: str           # Überschrift im Formular
    help: str = ""
    legacy_file: str = ""   # früherer Ablageort: Textdatei im App-Datenordner


KEYS: tuple[Key, ...] = (
    Key("GEMINI_API_KEY", "Gemini API-Schlüssel", "Sprachmodell",
        "Google AI Studio → API-Schlüssel (https://aistudio.google.com/api-keys)", "gemini-api-key.txt"),
    Key("PDA_ORS_KEY", "openrouteservice", "Reise-Assistent",
        "Pflicht für Adressen und Routen (https://openrouteservice.org/dev/#/signup)"),
    Key("PDA_DB_CLIENT_ID", "DB API Marketplace: Client-ID", "Reise-Assistent",
        "Optional: Bahnhofstafeln als Rückfall (https://developers.deutschebahn.com)"),
    Key("PDA_DB_API_KEY", "DB API Marketplace: API-Key", "Reise-Assistent", "Gehört zur Client-ID"),
    Key("PDA_TANKERKOENIG_KEY", "Tankerkönig", "Reise-Assistent",
        "Optional: aktuelle Spritpreise (https://creativecommons.tankerkoenig.de)"),
    Key("PDA_ALPHAVANTAGE_KEY", "Alpha Vantage", "Morgenüberblick",
        "Für die Aktienkurse (https://www.alphavantage.co/support/#api-key)", "alphavantage-api-key.txt"),
    Key("PDA_SMTP_PASSWORD", "Mail-Passwort (Senden, SMTP)", "E-Mail",
        "Bei Gmail ein App-Passwort (https://myaccount.google.com/apppasswords)"),
    Key("PDA_IMAP_PASSWORD", "Mail-Passwort (Lesen, IMAP)", "E-Mail", "Leer = dasselbe wie beim Senden"),
)
_BY_NAME = {key.name: key for key in KEYS}


def get(name: str) -> str:
    """Wert eines Keys: Umgebungsvariable (wenn nicht leer), sonst die .env, sonst ""."""
    return _from_environment(name) or config.read_env_file(config.ENV_FILE).get(name, "")


def _from_environment(name: str) -> str:
    return os.environ.get(name, "").strip()


def status() -> list[dict[str, Any]]:
    """Fürs Formular - ohne Werte: [{"name", "label", "group", "help", "set", "source"}],
    source: "env" (Umgebungsvariable, hier nicht änderbar), "file" (.env) oder ""."""
    stored = config.read_env_file(config.ENV_FILE)
    rows = []
    for key in KEYS:
        source = "env" if _from_environment(key.name) else "file" if stored.get(key.name) else ""
        rows.append({"name": key.name, "label": key.label, "group": key.group, "help": key.help,
                     "set": bool(source), "source": source})
    return rows


def validated(changes: Mapping[str, Any] | None) -> dict[str, str]:
    """{Name: neuer Wert} prüfen; "" oder None = löschen. ValueError (ohne den Wert zu nennen)."""
    result: dict[str, str] = {}
    for name, value in (changes or {}).items():
        key = _BY_NAME.get(name)
        if key is None:
            raise ValueError(f"Unbekannter Zugang: {name!r}")
        if _from_environment(name):
            raise ValueError(f"{key.label}: kommt aus der Umgebungsvariablen {name} und lässt sich hier nicht ändern")
        result[name] = _clean(key, value)
    return result


def _clean(key: Key, value: Any) -> str:
    value = "" if value is None else value
    if not isinstance(value, str):
        raise ValueError(f"{key.label}: Text erwartet")
    value = value.strip()
    if len(value) > MAX_LENGTH:
        raise ValueError(f"{key.label}: zu lang")
    if not value.isprintable():   # auch Zeilenumbrüche - sonst ließe sich eine weitere Zeile einschleusen
        raise ValueError(f"{key.label}: enthält Zeilenumbrüche oder Steuerzeichen")
    if value and (value[0] in "\"'" or value[-1] in "\"'"):   # read_env_file würde sie abschneiden
        raise ValueError(f"{key.label}: darf nicht mit einem Anführungszeichen beginnen oder enden")
    return value


def store(values: Mapping[str, str], path: Path | None = None) -> None:
    """Geprüfte Werte (validated) in die .env schreiben; übrige Zeilen und Kommentare bleiben."""
    if values:
        _write(path or config.ENV_FILE, values)


def save(changes: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    store(validated(changes))
    return status()


def _write(path: Path, values: Mapping[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    pending = dict(values)
    output = []
    for line in lines:
        name = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
        if name in values:
            if name in pending:   # erste Zeile ersetzen, doppelte weglassen
                output.append(f"{name}={pending.pop(name)}")
            continue
        output.append(line)
    output.extend(f"{name}={value}" for name, value in pending.items())
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".env.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as file:
            file.write("\n".join(output) + "\n")
        if sys.platform != "win32":
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def migrate_legacy_files(app_data_dir: Path | None = None, path: Path | None = None) -> list[str]:
    """Keys aus den früheren Textdateien in die .env übernehmen und die Datei löschen. Steht der
    Key schon in der .env, bleibt die Datei unangetastet (sie wird nur nicht mehr gelesen).
    Gibt die Namen der übernommenen Keys zurück."""
    app_data_dir = app_data_dir or config.APP_DATA_DIR
    path = path or config.ENV_FILE
    moved = []
    for key in KEYS:
        legacy = app_data_dir / key.legacy_file if key.legacy_file else None
        if legacy is None or not legacy.is_file():
            continue
        if config.read_env_file(path).get(key.name):
            log.info("%s steht schon in %s - %s wird nicht mehr gelesen", key.name, path, legacy)
            continue
        try:
            value = _clean(key, legacy.read_text(encoding="utf-8"))
            if not value:
                continue
            _write(path, {key.name: value})
            if config.read_env_file(path).get(key.name) != value:
                raise OSError("Wert nach dem Schreiben nicht wiedergefunden")
        except (OSError, UnicodeError, ValueError) as error:
            log.warning("%s nicht in die .env übernommen: %s", legacy, error)
            continue
        legacy.unlink()
        moved.append(key.name)
        log.info("%s aus %s in %s übernommen", key.name, legacy, path)
    return moved
