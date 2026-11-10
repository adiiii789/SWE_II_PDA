"""Einstellungen der proaktiven Meldungen (eigener Bereich im Popup, ⚙ Einstellungen).

Wie die übrigen Einstellungen beschreibt sich jedes Feld selbst (Setting aus
backend/assistant/settings.py), das Popup baut sein Formular allein aus diesem Schema. Neue
Einstellung: Setting in einem der Bereiche eintragen und in backend/watcher.py auswerten.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from backend.assistant.settings import PROACTIVE_KEY, Choice, Setting, _cleaned, _merged
from backend.preferences import PreferenceStore

GENERAL = "general"
MAIL = "mail"
TASKS = "tasks"
CALENDAR = "calendar"

_WEEKDAYS = (Choice("0", "Mo"), Choice("1", "Di"), Choice("2", "Mi"), Choice("3", "Do"),
             Choice("4", "Fr"), Choice("5", "Sa"), Choice("6", "So"))

_GENERAL: tuple[Setting, ...] = (
    Setting("enabled", "Proaktive Meldungen nutzen", "bool", True, help="Aus: Der PDA meldet sich nicht von selbst"),
    Setting("interval", "Prüfen alle … Minuten", "number", 5, minimum=1, maximum=60,
            help="Kürzer heißt pünktlicher, aber öfter Anfragen an Postfach und Google"),
    Setting("display", "Wie melden", "choice", "popup", (
        Choice("popup", "Popup öffnen"),
        Choice("notice", "Windows-Benachrichtigung"),
        Choice("chat", "Nur still im Chat"),
    )),
    Setting("speak", "Meldungen vorlesen", "bool", False),
    Setting("formulate", "Vom Sprachmodell formulieren", "bool", True,
            help="Aus: kurzer fester Text, dafür sofort und ohne Sprachmodell"),
    Setting("style", "Länge der Meldung", "choice", "kurz", (
        Choice("kurz", "Kurz"),
        Choice("normal", "Normal"),
        Choice("ausfuehrlich", "Ausführlich"),
    )),
    Setting("wishes", "Eigene Wünsche an die Meldungen", "text", "",
            help="z. B. \"Sprich mich mit Namen an\" oder \"Nenne immer zuerst die Uhrzeit\""),
    Setting("bundle", "Mehreres zu einer Meldung zusammenfassen", "bool", True),
    Setting("max_per_hour", "Höchstens … Meldungen pro Stunde", "number", 6, minimum=1, maximum=60,
            help="Darüber wird nichts verworfen, die Meldung kommt später"),
    Setting("days", "An diesen Tagen", "multi", [choice.value for choice in _WEEKDAYS], _WEEKDAYS),
    Setting("quiet", "Ruhezeit", "bool", True, help="In dieser Zeit meldet sich der PDA nicht"),
    Setting("quiet_from", "Ruhezeit von", "time", "22:00"),
    Setting("quiet_to", "Ruhezeit bis", "time", "07:00"),
    Setting("catch_up", "Mails aus der Ruhezeit danach melden", "bool", True),
    Setting("report_problems", "Melden, wenn die Google-Anmeldung abläuft", "bool", True,
            help="Höchstens einmal am Tag, sonst blieben Erinnerungen unbemerkt aus"),
)

_MAIL: tuple[Setting, ...] = (
    Setting("enabled", "Bei neuen E-Mails melden", "bool", True),
    Setting("mode", "Welche Mails", "choice", "llm", (
        Choice("llm", "Sprachmodell entscheidet, was wichtig ist"),
        Choice("regeln", "Nur nach meinen Regeln unten"),
        Choice("alle", "Alle außer ausgeschlossene"),
    )),
    Setting("criteria", "Was ist für mich wichtig?", "text", "",
            help="Für das Sprachmodell, z. B. \"Uni, Rechnungen, Fristen, alles von meiner Familie\""),
    Setting("ignore_bulk", "Newsletter und Werbung auslassen", "bool", True,
            help="Erkannt an den Kopfzeilen, die Massenmails mitbringen"),
    Setting("only_unread", "Nur ungelesene Mails", "bool", True,
            help="Am Handy schon gelesene Mails werden nicht mehr gemeldet"),
    Setting("always_senders", "Immer melden von", "text", "", help="Absender oder Teile davon, durch Komma getrennt"),
    Setting("never_senders", "Nie melden von", "text", "", help="Absender oder Teile davon, durch Komma getrennt"),
    Setting("important_words", "Immer melden bei diesen Wörtern im Betreff", "text", "", help="Durch Komma getrennt"),
    Setting("ignore_words", "Nie melden bei diesen Wörtern im Betreff", "text", "", help="Durch Komma getrennt"),
    Setting("show", "In der Meldung nennen", "multi", ["absender", "betreff", "inhalt", "grund"], (
        Choice("absender", "Absender"),
        Choice("betreff", "Betreff"),
        Choice("inhalt", "Worum es geht"),
        Choice("grund", "Warum wichtig"),
    )),
    Setting("on_model_failure", "Wenn das Sprachmodell nicht antwortet", "choice", "melden", (
        Choice("melden", "Trotzdem melden (außer Newsletter)"),
        Choice("still", "Nicht melden"),
    )),
)

_TASKS: tuple[Setting, ...] = (
    Setting("enabled", "Bei Aufgaben melden", "bool", True),
    Setting("time_reminder", "An Uhrzeiten in Aufgaben erinnern", "bool", True,
            help="Erkennt z. B. \"ca um 18 Uhr\", \"18:30\", \"um 9\" oder \"8 Uhr abends\". Gilt am Fälligkeitstag"),
    Setting("search", "Uhrzeit suchen in", "choice", "beides", (
        Choice("notizen", "Nur in der Notiz"),
        Choice("beides", "Notiz und Titel"),
    )),
    Setting("lead", "… Minuten vorher erinnern", "number", 15, minimum=0, maximum=240),
    Setting("late", "Noch bis … Minuten danach nachholen", "number", 30, minimum=0, maximum=240,
            help="Falls der PC zur Uhrzeit aus war"),
    Setting("undated", "Auch Aufgaben ohne Datum (gilt dann täglich)", "bool", False),
    Setting("summary", "Täglich sagen, was heute fällig ist", "bool", False),
    Setting("summary_time", "Uhrzeit dafür", "time", "08:00"),
    Setting("overdue", "Dabei auch Überfälliges nennen", "bool", True),
    Setting("only_lists", "Nur diese Listen", "text", "", help="Durch Komma getrennt, leer = alle"),
    Setting("ignore_lists", "Diese Listen auslassen", "text", "", help="Durch Komma getrennt"),
)

_CALENDAR: tuple[Setting, ...] = (
    Setting("enabled", "Bei Terminen melden", "bool", True),
    Setting("lead", "Erste Erinnerung … Minuten vorher", "number", 30, minimum=0, maximum=1440),
    Setting("second_lead", "Zweite Erinnerung … Minuten vorher", "number", 5, minimum=0, maximum=1440, help="0 = keine"),
    Setting("late", "Noch bis … Minuten nach Beginn nachholen", "number", 5, minimum=0, maximum=120),
    Setting("all_day", "Ganztägige Termine melden", "bool", False),
    Setting("all_day_time", "Uhrzeit dafür", "time", "08:00"),
    Setting("invitations", "Neue Einladungen melden", "bool", True),
    Setting("skip_declined", "Abgesagte Termine auslassen", "bool", True),
    Setting("skip_unanswered", "Unbeantwortete Einladungen nicht als Termin melden", "bool", False),
    Setting("skip_free", "Termine auslassen, die als \"frei\" eingetragen sind", "bool", True),
    Setting("show", "In der Meldung nennen", "multi", ["ort"], (
        Choice("ort", "Ort"),
        Choice("beschreibung", "Beschreibung"),
        Choice("kalender", "Kalender"),
    )),
    Setting("only_calendars", "Nur diese Kalender", "text", "", help="Durch Komma getrennt, leer = alle eingeblendeten"),
    Setting("ignore_calendars", "Diese Kalender auslassen", "text", "", help="z. B. \"Geburtstage, Feiertage\""),
    Setting("ignore_words", "Termine mit diesen Wörtern im Titel auslassen", "text", "", help="Durch Komma getrennt"),
)


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    description: str
    settings: tuple[Setting, ...]


SECTIONS: tuple[Section, ...] = (
    Section(GENERAL, "Allgemein", "Wie und wann sich der PDA überhaupt meldet", _GENERAL),
    Section(MAIL, "E-Mail", "Neue Mails. Sie bleiben dabei ungelesen.", _MAIL),
    Section(TASKS, "Aufgaben", "Google Tasks kennt nur Tage, deshalb zählt eine Uhrzeit in der Notiz", _TASKS),
    Section(CALENDAR, "Kalender", "Erinnerungen an Termine und neue Einladungen", _CALENDAR),
)
_BY_ID = {section.id: section for section in SECTIONS}


class ProactiveSettings:
    """Liest und schreibt die Einstellungen im PreferenceStore; hält selbst keinen Zustand."""

    def __init__(self, store: PreferenceStore):
        self.store = store

    def values(self, section_id: str) -> dict[str, Any]:
        return _merged(_BY_ID[section_id].settings, (self.store.get(PROACTIVE_KEY) or {}).get(section_id, {}))

    def form(self) -> list[dict[str, Any]]:
        """Bereiche im selben Aufbau wie die Werkzeuggruppen, das Popup zeigt sie gleich an."""
        return [{"id": section.id, "title": section.title, "description": section.description, "tools": [],
                 "available": True, "fields": [setting.to_dict() for setting in section.settings],
                 "values": self.values(section.id)} for section in SECTIONS]

    def validated(self, changes: Mapping[str, Mapping[str, Any]] | None) -> dict[str, Any] | None:
        """Neuer Gesamtstand; ValueError bei ungültigen Werten. Geschrieben wird erst mit store_validated."""
        if changes is None:
            return None
        result = dict(self.store.get(PROACTIVE_KEY) or {})
        for section_id, values in changes.items():
            if section_id not in _BY_ID:
                raise ValueError(f"Unbekannter Bereich: {section_id!r}")
            result[section_id] = {**result.get(section_id, {}), **_cleaned(_BY_ID[section_id].settings, values)}
        return result

    def store_validated(self, validated: dict[str, Any] | None) -> None:
        if validated is not None:
            self.store.set(PROACTIVE_KEY, validated)

    def reset(self) -> None:
        self.store.set(PROACTIVE_KEY, {})
