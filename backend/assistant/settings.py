"""Einstellungen, die der Nutzer im Popup festlegt (⚙ Einstellungen) - und wie sie wirken.

Zwei Bereiche:
  Antworten   Wünsche an das Sprachmodell: Länge, Tiefe, Darstellung, Ton, Anrede, Sprache …
  Werkzeuge   je Werkzeuggruppe: nutzen ja/nein, wie ausführlich im Chat, Tabelle oben,
              eigene Darstellungswünsche - E-Mail zusätzlich: welche Angaben, wie viel Inhalt …

Jede Einstellung (Setting) beschreibt sich selbst: Art des Eingabefelds, erlaubte Werte,
Standardwert und den Satz, den das Sprachmodell daraus bekommt. Das Popup baut sein Formular
allein aus diesem Schema (api.get_settings) - neue Einstellungen brauchen kein neues Frontend.

Werkzeuge: Bekannte Gruppen stehen in TOOL_GROUPS (z. B. alle Mail-Werkzeuge zusammen, mit
Zusatzfeldern). Jedes andere Werkzeug - auch jedes künftige, z. B. von einem neuen MCP-Server -
bekommt automatisch eine eigene Gruppe mit den Grundeinstellungen (TOOL_SETTINGS). Für eigene
Zusatzfelder eine ToolGroup in TOOL_GROUPS eintragen.

Gespeichert wird im PreferenceStore (backend/preferences.py) unter ANSWER_KEY und TOOLS_KEY.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from backend.preferences import PreferenceStore

ANSWER_KEY = "answer_settings"
TOOLS_KEY = "tool_settings"
SETTINGS_KEYS = (ANSWER_KEY, TOOLS_KEY)   # nicht als "Bekanntes über den Nutzer" ans Modell

MAX_TEXT_CHARS = 1000                     # Freitext - schützt das Kontextfenster

Kind = Literal["choice", "multi", "bool", "number", "text"]


@dataclass(frozen=True)
class Choice:
    value: str
    label: str
    instruction: str = ""   # Satz fürs Modell; leer = nichts dazu sagen


@dataclass(frozen=True)
class Setting:
    """Eine Einstellung. `instruction` ist eine Vorlage für bool/number/text/multi:
    {value} = Wert, {labels} = gewählte Einträge (multi), {group} = Name der Werkzeuggruppe."""

    key: str
    label: str
    kind: Kind
    default: Any
    choices: tuple[Choice, ...] = ()
    help: str = ""
    instruction: str = ""
    instruction_off: str = ""    # nur bool: Satz, wenn ausgeschaltet
    minimum: int = 0             # nur number
    maximum: int = 100

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"key": self.key, "label": self.label, "kind": self.kind,
                                "default": self.default, "help": self.help}
        if self.choices:
            data["choices"] = [{"value": c.value, "label": c.label} for c in self.choices]
        if self.kind == "number":
            data["minimum"], data["maximum"] = self.minimum, self.maximum
        return data

    def clean(self, value: Any) -> Any:
        """Wert prüfen und vereinheitlichen; ValueError, wenn er nicht passt."""
        values = {choice.value for choice in self.choices}
        if self.kind == "choice":
            if value not in values:
                raise ValueError(f"{self.label}: {value!r} ist keine erlaubte Auswahl")
            return value
        if self.kind == "multi":
            if not isinstance(value, list) or not set(value) <= values:
                raise ValueError(f"{self.label}: ungültige Auswahl {value!r}")
            return [choice.value for choice in self.choices if choice.value in value]   # feste Reihenfolge
        if self.kind == "bool":
            if not isinstance(value, bool):
                raise ValueError(f"{self.label}: ja oder nein erwartet")
            return value
        if self.kind == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value):
                raise ValueError(f"{self.label}: ganze Zahl erwartet")
            if not self.minimum <= value <= self.maximum:
                raise ValueError(f"{self.label}: zwischen {self.minimum} und {self.maximum}")
            return int(value)
        if not isinstance(value, str):
            raise ValueError(f"{self.label}: Text erwartet")
        return value.strip()[:MAX_TEXT_CHARS]

    def instruction_for(self, value: Any, group: str = "") -> str:
        if self.kind == "choice":
            return next((c.instruction for c in self.choices if c.value == value), "").format(group=group)
        if self.kind == "bool":
            return (self.instruction if value else self.instruction_off).format(group=group)
        if self.kind == "multi":
            labels = ", ".join(c.label for c in self.choices if c.value in value)
            return self.instruction.format(labels=labels, group=group) if labels else ""
        if self.kind == "text" and not value:
            return ""
        return self.instruction.format(value=value, group=group)


# --- Antworten ------------------------------------------------------------------------
ANSWER_SETTINGS: tuple[Setting, ...] = (
    Setting("length", "Antwortlänge", "choice", "kurz", (
        Choice("kurz", "Kurz", "Antworte kurz: wenige Sätze, nur das Wichtigste."),
        Choice("mittel", "Mittel", "Antworte in mittlerer Länge, etwa ein Absatz."),
        Choice("ausfuehrlich", "Ausführlich", "Antworte ausführlich und vollständig."),
    )),
    Setting("depth", "Tiefe", "choice", "normal", (
        Choice("ueberblick", "Überblick", "Bleib beim Überblick und lass Details und Fachbegriffe weg."),
        Choice("normal", "Normal"),
        Choice("detail", "Ins Detail", "Geh in die Tiefe: Hintergründe, Begründungen und Fachbegriffe sind erwünscht."),
    )),
    Setting("format", "Darstellung", "choice", "automatisch", (
        Choice("automatisch", "Passend zum Inhalt",
               "Wähle die Darstellung passend zum Inhalt; Markdown (Listen, Tabellen, Formeln) ist möglich."),
        Choice("fliesstext", "Fließtext", "Schreib Fließtext ohne Listen, Tabellen und Überschriften."),
        Choice("stichpunkte", "Stichpunkte", "Gliedere Antworten in knappe Stichpunkte."),
        Choice("strukturiert", "Strukturiert",
               "Gliedere längere Antworten mit Überschriften, Listen und - wo sich Daten vergleichen - Tabellen."),
    )),
    Setting("tone", "Ton", "choice", "freundlich", (
        Choice("freundlich", "Freundlich", "Sei freundlich."),
        Choice("sachlich", "Sachlich", "Bleib sachlich und neutral, ohne Floskeln."),
        Choice("locker", "Locker", "Schreib locker und umgangssprachlich."),
    )),
    Setting("address", "Anrede", "choice", "du", (
        Choice("du", "Du", "Duze den Nutzer."),
        Choice("sie", "Sie", "Sieze den Nutzer."),
    )),
    Setting("language", "Sprache", "choice", "deutsch", (
        Choice("deutsch", "Deutsch", "Antworte immer auf Deutsch."),
        Choice("englisch", "Englisch", "Antworte immer auf Englisch."),
        Choice("wie_nutzer", "Wie der Nutzer schreibt", "Antworte in der Sprache, in der der Nutzer schreibt."),
    )),
    Setting("emojis", "Emojis erlaubt", "bool", False,
            instruction="Emojis sind erlaubt, aber sparsam.", instruction_off="Verwende niemals Emojis."),
    Setting("follow_up", "Rückfragen statt Raten", "bool", True,
            help="Bei fehlenden Angaben kurz nachfragen, statt etwas anzunehmen",
            instruction="Fehlt dir eine Angabe, frag kurz nach, statt zu raten.",
            instruction_off="Frag möglichst nicht nach, sondern triff sinnvolle Annahmen und nenne sie."),
    Setting("extra", "Weitere Wünsche", "text", "",
            help="z. B. \"Nenne bei Zahlen immer die Quelle\" oder \"Erkläre wie für Einsteiger\"",
            instruction="Weitere Wünsche des Nutzers: {value}"),
)

# --- Werkzeuge ------------------------------------------------------------------------
TOOL_SETTINGS: tuple[Setting, ...] = (
    Setting("enabled", "Nutzen", "bool", True,
            help="Aus: Das Sprachmodell bekommt diese Werkzeuge nicht angeboten"),
    Setting("detail", "Ergebnis im Chat", "choice", "normal", (
        Choice("kurz", "Nur das Wichtigste",
               "Gib Ergebnisse von {group} nur knapp wieder: das Wichtigste in ein, zwei Sätzen."),
        Choice("normal", "Normal"),
        Choice("vollstaendig", "Möglichst vollständig", "Gib Ergebnisse von {group} möglichst vollständig wieder."),
    )),
    Setting("view", "Tabelle oben", "choice", "kurz", (
        Choice("aus", "Nicht anzeigen"),
        Choice("kurz", "Gekürzt"),
        Choice("voll", "Vollständig"),
    ), help="Aufrufe und Ergebnisse als Tabelle im Anzeigebereich über dem Chat"),
    Setting("notes", "Darstellung - eigene Wünsche", "text", "",
            help="z. B. \"als Tabelle\", \"Uhrzeit immer mit Sekunden\", \"nur Ergebnis, keine Rechenwege\"",
            instruction="Darstellung von {group}: {value}"),
)
VIEW_LIMITS = {"kurz": 300, "voll": 8000}   # Zeichen pro Ergebnis in der Tabelle; "aus" = keine Zeile


@dataclass(frozen=True)
class ToolGroup:
    """Werkzeuge, die zusammen eingestellt werden, ggf. mit Zusatzfeldern (`extra`)."""

    id: str
    title: str
    tools: tuple[str, ...]
    description: str = ""
    extra: tuple[Setting, ...] = ()

    @property
    def settings(self) -> tuple[Setting, ...]:
        return (*TOOL_SETTINGS, *self.extra)


MAIL_SETTINGS: tuple[Setting, ...] = (
    Setting("fields", "Angaben je Mail", "multi", ["sender", "subject", "date"], (
        Choice("sender", "Absender"),
        Choice("subject", "Betreff"),
        Choice("date", "Datum"),
        Choice("preview", "Kurzvorschau des Inhalts"),
        Choice("attachments", "Anhänge"),
        Choice("unread", "gelesen/ungelesen"),
    ), instruction="Zeige bei jeder Mail: {labels} - andere Angaben nur auf Nachfrage."),
    Setting("content", "Inhalt einer Mail", "choice", "zusammenfassung", (
        Choice("kopf", "Nur Angaben, kein Text",
               "Gib vom Text einer Mail nichts wieder, außer der Nutzer fragt ausdrücklich danach."),
        Choice("zusammenfassung", "Zusammenfassung", "Fasse den Text einer Mail in ein bis zwei Sätzen zusammen."),
        Choice("wichtiges", "Wichtiges hervorheben",
               "Nenne aus dem Text einer Mail nur Fristen, Termine, Fragen an den Nutzer und Aufgaben."),
        Choice("volltext", "Volltext", "Gib den vollständigen Text einer Mail wieder."),
    )),
    Setting("layout", "Mehrere Mails als", "choice", "liste", (
        Choice("liste", "Liste", "Stelle mehrere Mails als Liste dar, eine Mail pro Punkt."),
        Choice("tabelle", "Tabelle", "Stelle mehrere Mails als Markdown-Tabelle dar, eine Mail pro Zeile."),
    )),
    Setting("max", "Höchstens so viele Mails", "number", 10, minimum=1, maximum=50,
            instruction="Liste höchstens {value} Mails auf, außer der Nutzer will ausdrücklich mehr."),
    Setting("confirm_send", "Vor dem Senden nachfragen", "bool", True,
            instruction="Zeig vor dem Senden einer Mail den Entwurf und sende erst nach Bestätigung des Nutzers."),
)

CALENDAR_SETTINGS: tuple[Setting, ...] = (
    Setting("confirm_create", "Vor dem Erstellen nachfragen", "bool", True,
            instruction="Nenne vor dem Erstellen eines Termins Titel, Datum und Uhrzeit "
                        "und erstelle ihn erst nach Bestätigung des Nutzers."),
)

TOOL_GROUPS: tuple[ToolGroup, ...] = (
    ToolGroup("mail", "E-Mail", ("list_emails", "read_email", "read_attachment", "send_email"),
              "Mails lesen, Anhänge öffnen und Mails senden", MAIL_SETTINGS),
    ToolGroup("calendar", "Google Kalender", ("list_calendar_events", "create_calendar_event"),
              "Termine lesen und neue Termine erstellen", CALENDAR_SETTINGS),
    ToolGroup("basics", "Uhrzeit und Rechnen", ("get_current_time", "calculate"),
              "Aktuelle Uhrzeit, Rechenaufgaben"),
)


class AssistantSettings:
    """Liest und schreibt die Einstellungen im PreferenceStore und übersetzt sie für den Assistenten.
    Hält selbst keinen Zustand - mehrere Instanzen auf demselben Store sehen dasselbe."""

    def __init__(self, store: PreferenceStore, groups: Iterable[ToolGroup] = TOOL_GROUPS):
        self.store = store
        self.groups = tuple(groups)

    # --- Werte -------------------------------------------------------------------------
    def answer_values(self) -> dict[str, Any]:
        return _merged(ANSWER_SETTINGS, self.store.get(ANSWER_KEY) or {})

    def group_of(self, tool: str) -> ToolGroup:
        """Gruppe eines Werkzeugs; unbekannte Werkzeuge bilden eine eigene Gruppe."""
        for group in self.groups:
            if tool in group.tools:
                return group
        return ToolGroup(f"tool:{tool}", tool, (tool,))

    def group_values(self, group: ToolGroup) -> dict[str, Any]:
        return _merged(group.settings, (self.store.get(TOOLS_KEY) or {}).get(group.id, {}))

    def tool_values(self, tool: str) -> dict[str, Any]:
        return self.group_values(self.group_of(tool))

    def tool_enabled(self, tool: str) -> bool:
        return self.tool_values(tool)["enabled"]

    def view_limit(self, tool: str) -> int | None:
        """Zeichen pro Ergebnis in der Tabelle oben; None = dieses Werkzeug nicht zeigen."""
        return VIEW_LIMITS.get(self.tool_values(tool)["view"])

    # --- fürs Sprachmodell ---------------------------------------------------------------
    def instructions(self, tools: Iterable[str] = ()) -> str:
        """Systemanweisung aus den Einstellungen; Werkzeuggruppen nur für angebotene Werkzeuge."""
        answer = self.answer_values()
        lines = [text for setting in ANSWER_SETTINGS if (text := setting.instruction_for(answer[setting.key]))]
        parts = ["Wünsche des Nutzers an deine Antworten:\n" + "\n".join(f"- {line}" for line in lines)]
        tool_lines = []
        for group in self._groups_for(tools):
            values = self.group_values(group)
            if not values["enabled"]:
                continue
            label = f"{group.title} ({', '.join(group.tools)})" if group.id.startswith("tool:") else group.title
            texts = [text for setting in group.settings
                     if (text := setting.instruction_for(values[setting.key], f'"{group.title}"'))]
            if texts:
                tool_lines.append(f"- {label}: " + " ".join(texts))
        if tool_lines:
            parts.append("Wünsche des Nutzers zur Darstellung von Werkzeug-Ergebnissen:\n" + "\n".join(tool_lines))
        return "\n\n".join(parts)

    # --- fürs Popup ----------------------------------------------------------------------
    def form(self, tools: Iterable[tuple[str, str]] = ()) -> dict[str, Any]:
        """Schema und Werte fürs Formular. tools: verfügbare Werkzeuge als (Name, Beschreibung)."""
        available = dict(tools)
        groups = list(self.groups) + [group for group in self._groups_for(available) if group not in self.groups]
        return {
            "answer": {"fields": [s.to_dict() for s in ANSWER_SETTINGS], "values": self.answer_values()},
            "tools": [{
                "id": group.id,
                "title": group.title,
                "description": group.description or available.get(group.tools[0], ""),
                "tools": list(group.tools),
                "available": any(tool in available for tool in group.tools),
                "fields": [s.to_dict() for s in group.settings],
                "values": self.group_values(group),
            } for group in groups],
        }

    def save(self, answer: Mapping[str, Any] | None = None, tools: Mapping[str, Mapping[str, Any]] | None = None) -> None:
        """Geänderte Werte prüfen und speichern - erst alles prüfen, dann schreiben (alles oder nichts)."""
        new_answer = None
        if answer is not None:
            new_answer = {**(self.store.get(ANSWER_KEY) or {}), **_cleaned(ANSWER_SETTINGS, answer)}
        new_tools = None
        if tools is not None:
            new_tools = dict(self.store.get(TOOLS_KEY) or {})
            for group_id, values in tools.items():
                group = self._group_by_id(group_id)
                new_tools[group_id] = {**new_tools.get(group_id, {}), **_cleaned(group.settings, values)}
        if new_answer is not None:
            self.store.set(ANSWER_KEY, new_answer)
        if new_tools is not None:
            self.store.set(TOOLS_KEY, new_tools)

    def reset(self) -> None:
        """Alle Einstellungen auf die Standardwerte."""
        self.store.set(ANSWER_KEY, {})
        self.store.set(TOOLS_KEY, {})

    # --- intern --------------------------------------------------------------------------
    def _groups_for(self, tools: Iterable[str]) -> list[ToolGroup]:
        groups: dict[str, ToolGroup] = {}
        for tool in tools:
            group = self.group_of(tool)
            groups.setdefault(group.id, group)
        return list(groups.values())

    def _group_by_id(self, group_id: str) -> ToolGroup:
        for group in self.groups:
            if group.id == group_id:
                return group
        if group_id.startswith("tool:") and len(group_id) > len("tool:"):
            return self.group_of(group_id[len("tool:"):])
        raise ValueError(f"Unbekannte Werkzeuggruppe: {group_id!r}")


def _merged(settings: Iterable[Setting], stored: Mapping[str, Any]) -> dict[str, Any]:
    """Standardwerte, überschrieben von gespeicherten Werten - ungültige (z. B. nach einem Update) zählen nicht."""
    values = {}
    for setting in settings:
        try:
            values[setting.key] = setting.clean(stored[setting.key]) if setting.key in stored else setting.default
        except ValueError:
            values[setting.key] = setting.default
    return values


def _cleaned(settings: Iterable[Setting], values: Mapping[str, Any]) -> dict[str, Any]:
    known = {setting.key: setting for setting in settings}
    unknown = set(values) - set(known)
    if unknown:
        raise ValueError(f"Unbekannte Einstellung: {', '.join(sorted(unknown))}")
    return {key: known[key].clean(value) for key, value in values.items()}
