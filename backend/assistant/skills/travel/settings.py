"""Einstellungen des Reise-Assistenten im Popup (⚙ Einstellungen → Reise).

Jedes Feld heißt wie das Feld in TravelSettings (planner.py), Standardwerte kommen von dort.
Gespeichert wird unter TRAVEL_KEY ("travel_settings"), die Heimatadresse wie bisher unter
"travel_home_address" (die kennt auch das Sprachmodell). Aufbau des Formulars wie bei den
proaktiven Meldungen (backend/proactive_settings.py), das Popup zeigt es gleich an.
Neue Einstellung: Feld in TravelSettings und ein Setting hier in einer Gruppe eintragen.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

from backend.assistant.settings import TRAVEL_KEY, Choice, Setting, _cleaned
from backend.assistant.skills.travel.planner import BIKE, CAR, FOOT, HOME_ADDRESS, TAXI, TRAIN, TravelSettings
from backend.preferences import PreferenceStore

HOME = "home_address"     # Formularfeld für HOME_ADDRESS
_DEFAULTS = asdict(TravelSettings())


def _setting(key: str, label: str, kind: str = "", **options: Any) -> Setting:
    default = _DEFAULTS[key]
    kind = kind or ("bool" if isinstance(default, bool) else "number")
    return Setting(key, label, kind, default, **options)


@dataclass(frozen=True)
class Group:
    id: str
    title: str
    description: str
    settings: tuple[Setting, ...]
    needs: str = ""       # ohne diesen Dienst "gerade nicht verfügbar" (siehe TravelSettingsForm)


GROUPS: tuple[Group, ...] = (
    Group("general", "Allgemein", "Woher du startest, was verglichen wird und was dir wichtig ist", (
        Setting(HOME, "Heimatadresse", "text", "", help="z. B. \"Königstraße 1, 70173 Stuttgart\""),
        Setting("modes", "Diese Verkehrsmittel vergleichen", "multi", list(_DEFAULTS["modes"]), (
            Choice(TRAIN, "Bus und Bahn"), Choice(BIKE, "Fahrrad"), Choice(FOOT, "Zu Fuß"),
            Choice(CAR, "Auto"), Choice(TAXI, "Taxi"),
        ), help="Ohne Auto z. B. einfach abwählen - nichts gewählt: alle"),
        _setting("prefer_free", "Kostenlose Verkehrsmittel zuerst",
                 help="Zu Fuß, Fahrrad und mit Deutschlandticket auch Bus und Bahn stehen vor allen anderen - "
                      "Rad und zu Fuß nicht bei Regen, Schnee oder Kälte"),
        _setting("free_max_extra_minutes", "… aber nur, wenn höchstens so viele Minuten länger", minimum=0,
                 maximum=240, help="Verglichen mit dem schnellsten kostenpflichtigen Weg; 0 = immer"),
        _setting("value_of_time", "Zeitwert in € pro Stunde", minimum=0, maximum=200,
                 help="Kosten = Preis + Reisezeit × Zeitwert. Höher = schnellere Verkehrsmittel gewinnen"),
        _setting("buffer_minutes", "So viele Minuten vor Terminbeginn ankommen", minimum=0, maximum=60),
    ), needs="ors"),
    Group("transit", "Bus und Bahn", "Verbindungen von der VVS-Auskunft (im VVS-Gebiet, mit Echtzeit und Preis) "
          "und Transitous (deutschlandweit) - beide ohne Key", (
        _setting("deutschlandticket", "Ich habe ein Deutschlandticket",
                 help="Bus, Tram und Nahverkehrszüge kosten dann nichts - zählen also als kostenlos"),
        Setting("train_transfers", "Umstiege", "choice", str(_DEFAULTS["train_transfers"]), (
            Choice("0", "Nur direkt"),
            Choice("1", "Höchstens einer"),
            Choice("2", "Bis zu zwei"),
            Choice("3", "Bis zu drei"),
        )),
        _setting("transfer_minutes", "Mindestens … Minuten zum Umsteigen", minimum=1, maximum=30),
        _setting("station_walk_minutes", "Zur Haltestelle höchstens … Minuten zu Fuß", minimum=5, maximum=60,
                 help="Weiter weg sucht die Auskunft eine Haltestelle näher dran oder einen Bus dorthin"),
    ), needs="ors"),
    Group("car", "Auto und Taxi", "Fahrzeit von openrouteservice (ohne Stau), Spritpreis von Tankerkönig", (
        Setting("fuel", "Kraftstoff", "choice", _DEFAULTS["fuel"], (
            Choice("e5", "Super E5"), Choice("e10", "Super E10"), Choice("diesel", "Diesel"),
        )),
        _setting("consumption", "Verbrauch in l/100 km", minimum=1, maximum=30, step=0.1),
        _setting("fuel_price", "Spritpreis in €/l ohne Tankerkönig", minimum=0.5, maximum=5, step=0.01),
        _setting("car_time_factor", "Fahrzeit × (Stau-Aufschlag)", minimum=1, maximum=3, step=0.05),
        _setting("taxi_base", "Taxi Grundpreis in €", minimum=0, maximum=30, step=0.1),
        _setting("taxi_per_km", "Taxi € pro km", minimum=0, maximum=10, step=0.1),
        _setting("taxi_wait_minutes", "Warten aufs Taxi in Minuten", minimum=0, maximum=60),
    ), needs="ors"),
    Group("bike_walk", "Fahrrad und zu Fuß", "Weiter weg (Luftlinie) wird es nicht vorgeschlagen", (
        _setting("max_bike_km", "Fahrrad bis … km", minimum=0, maximum=100, step=0.5),
        _setting("max_walk_km", "Zu Fuß bis … km", minimum=0, maximum=30, step=0.5),
    ), needs="ors"),
    Group("weather", "Wetter", "Fahrrad und zu Fuß zählen bei schlechtem Wetter schlechter (Open-Meteo, ohne Key)", (
        _setting("weather", "Wetter berücksichtigen"),
        _setting("rain_factor", "Bei Regen oder Schnee zählt Zeit draußen ×", minimum=1, maximum=5, step=0.1,
                 help="2 = eine Stunde Radfahren im Regen zählt wie zwei"),
        _setting("cold_below", "Kalt unter … °C", minimum=-20, maximum=25),
        _setting("cold_factor", "Bei Kälte zählt Zeit draußen ×", minimum=1, maximum=5, step=0.1),
        _setting("wind_above", "Windig über … km/h (nur Fahrrad)", minimum=10, maximum=120),
        _setting("wind_factor", "Bei Wind zählt Zeit auf dem Rad ×", minimum=1, maximum=5, step=0.1),
    )),
    Group("reminder", "Erinnerung und Heimweg", "Meldet sich von selbst, bevor du losmusst", (
        _setting("reminder", "Vor der Abfahrt erinnern"),
        _setting("reminder_minutes", "… Minuten vor der Abfahrt", minimum=0, maximum=120),
        Setting("reminder_display", "Wie melden", "choice", _DEFAULTS["reminder_display"], (
            Choice("popup", "Popup öffnen"),
            Choice("notice", "Systembenachrichtigung"),
            Choice("chat", "Nur still im Chat"),
        )),
        _setting("reminder_speak", "Erinnerung vorlesen"),
        _setting("home_trip", "Nach dem letzten Termin des Tages den Heimweg zeigen",
                 help="Auch die Erinnerung gilt dann für den Heimweg, z. B. 15 Minuten vor Terminende"),
        _setting("home_trip_hours", "Heimweg bis … Stunden nach dem letzten Termin", minimum=1, maximum=12),
    ), needs="ors"),
    Group("fares", "Preise schätzen", "Nur wenn die Auskunft keinen Preis kennt (außerhalb des VVS)", (
        _setting("rail_regional_per_km", "Nahverkehr € pro km", minimum=0, maximum=2, step=0.01),
        _setting("rail_long_distance_per_km", "Fernverkehr € pro km", minimum=0, maximum=2, step=0.01),
        _setting("rail_min_fare", "Mindestpreis Bus und Bahn in €", minimum=0, maximum=50, step=0.1),
        _setting("local_transit_fare", "Bus/Tram zum Bahnhof in € (nur Ersatzsuche über die DB-Tafeln)",
                 minimum=0, maximum=20, step=0.1),
    )),
)
_BY_ID = {group.id: group for group in GROUPS}
_CHOICE_NUMBERS = {"train_transfers"}   # als Auswahl gezeigt, in TravelSettings eine Zahl


class TravelSettingsForm:
    """Liest und schreibt die Reise-Einstellungen im PreferenceStore; hält selbst keinen Zustand.
    available(): {"ors": bool, "rail": bool} - welche Dienste eingerichtet sind."""

    def __init__(self, store: PreferenceStore, available: Callable[[], Mapping[str, bool]] = lambda: {}):
        self.store = store
        self.available = available

    def values(self, group_id: str) -> dict[str, Any]:
        current = asdict(TravelSettings.from_preferences(self.store))
        values = {}
        for setting in _BY_ID[group_id].settings:
            if setting.key == HOME:
                values[HOME] = self.store.get(HOME_ADDRESS) or ""
            elif setting.key in _CHOICE_NUMBERS:
                values[setting.key] = str(current[setting.key])
            else:
                value = current[setting.key]
                values[setting.key] = list(value) if isinstance(value, tuple) else value
        return values

    def form(self) -> list[dict[str, Any]]:
        services = self.available()
        return [{"id": group.id, "title": group.title, "description": group.description, "tools": [],
                 "available": not group.needs or services.get(group.needs, True),
                 "fields": [setting.to_dict() for setting in group.settings],
                 "values": self.values(group.id)} for group in GROUPS]

    def validated(self, changes: Mapping[str, Mapping[str, Any]] | None) -> dict[str, Any] | None:
        """Neuer Gesamtstand {feld: wert}; ValueError bei ungültigen Werten. Geschrieben wird erst mit
        store_validated."""
        if changes is None:
            return None
        result = dict(self.store.get(TRAVEL_KEY) or {})
        for group_id, values in changes.items():
            if group_id not in _BY_ID:
                raise ValueError(f"Unbekannter Bereich: {group_id!r}")
            for key, value in _cleaned(_BY_ID[group_id].settings, values).items():
                result[key] = int(value) if key in _CHOICE_NUMBERS else value
        return result

    def store_validated(self, validated: dict[str, Any] | None) -> None:
        if validated is None:
            return
        validated = dict(validated)
        if HOME in validated:
            home = validated.pop(HOME)
            if home != (self.store.get(HOME_ADDRESS) or ""):
                self.store.set(HOME_ADDRESS, home)
        self.store.set(TRAVEL_KEY, validated)

    def reset(self) -> None:
        """Alles auf Standard - die Heimatadresse bleibt."""
        self.store.set(TRAVEL_KEY, {})
