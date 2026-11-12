"""Bewertung der Verkehrsmittel - reine Rechenlogik, ohne Netzwerk.

Empfohlen wird das Verkehrsmittel mit den geringsten Kosten:
    Kosten = Preis + Reisezeit × Zeitwert × Wetterfaktor
Zeit zählt also mit: Bei 25 €/h ist eine 20 Minuten schnellere Fahrt 8,33 € wert. Der
Wetterfaktor gilt nur für Fahrrad und zu Fuß: Bei Regen zählt die Zeit draußen z. B. doppelt.

Kostenlose Verkehrsmittel (zu Fuß, Fahrrad, Bus und Bahn mit Deutschlandticket) stehen mit
prefer_free (Standard) vor allen anderen, untereinander nach Kosten - außer Rad/zu Fuß bei
schlechtem Wetter und, falls free_max_extra_minutes gesetzt ist, wenn sie so viel länger dauern
als das schnellste kostenpflichtige. Welche Verkehrsmittel verglichen werden: modes.

Einstellungen: im Popup unter ⚙ Einstellungen → Reise (gespeichert unter "travel_settings",
siehe settings.py). Von Hand gesetzte Werte "travel_<feld>" in preferences.json gelten weiter,
die Werte aus dem Popup haben Vorrang.
"""
from __future__ import annotations

import datetime
import math
from dataclasses import dataclass, field, fields, replace
from typing import Any

from backend.assistant.settings import TRAVEL_KEY
from backend.integrations import transit
from backend.integrations.db_timetables import Journey, TrainConnection
from backend.integrations.geo import Place
from backend.integrations.openrouteservice import Route
from backend.integrations.weather import Weather
from backend.preferences import PreferenceStore

PREFERENCE_PREFIX = "travel_"
HOME_ADDRESS = "travel_home_address"

CAR, TRAIN, TAXI, BIKE, FOOT = "car", "train", "taxi", "bike", "foot"
LABELS = {CAR: "Auto", TRAIN: "Bahn", TAXI: "Taxi", BIKE: "Fahrrad", FOOT: "Zu Fuß"}
OUTDOOR = frozenset({BIKE, FOOT})   # hier zählt das Wetter
WALK, TRANSIT, RAIL, BUS = "walk", "transit", "rail", "bus"   # Arten von Segmenten auf der Karte
VEHICLES = frozenset({RAIL, BUS})   # Segmente mit einer bestimmten Linie (Zug, Bus, Tram)
MAX_TRAIN_MESSAGES = 2              # Störungs-/Hinweistexte je Zug in der Wegbeschreibung


@dataclass(frozen=True)
class TravelSettings:
    modes: tuple[str, ...] = (TRAIN, BIKE, FOOT, CAR, TAXI)   # diese Verkehrsmittel vergleichen
    prefer_free: bool = True             # kostenlose Verkehrsmittel zuerst (siehe Modulbeschreibung)
    free_max_extra_minutes: int = 0      # … wenn höchstens so viel länger als das schnellste andere (0 = immer)
    value_of_time: float = 25.0          # €/h - was dir eine Stunde Reisezeit wert ist
    buffer_minutes: int = 5              # so viel früher als Terminbeginn ankommen
    deutschlandticket: bool = False      # Nahverkehr (RE, RB, S, Bus) kostet dann nichts
    fuel: str = "e5"                     # e5, e10 oder diesel
    consumption: float = 7.0             # l/100 km
    fuel_price: float = 1.80             # €/l, wenn Tankerkönig nichts liefert
    car_time_factor: float = 1.15        # ORS kennt keinen Stau: Fahrzeit × Faktor
    taxi_base: float = 4.50              # € Grundpreis
    taxi_per_km: float = 2.60            # €/km
    taxi_wait_minutes: int = 5           # bis das Taxi da ist
    max_walk_km: float = 5.0             # weiter wird zu Fuß nicht vorgeschlagen (Luftlinie)
    max_bike_km: float = 25.0            # dito Fahrrad
    station_walk_minutes: int = 20       # länger zum Bahnhof: Bus/Tram (geschätzt) statt zu Fuß
    local_transit_fare: float = 3.00     # € Bus/Tram zum Bahnhof ohne Deutschlandticket
    rail_regional_per_km: float = 0.20   # €/km Nahverkehr (Schätzung)
    rail_long_distance_per_km: float = 0.25   # €/km Fernverkehr, eher Flexpreis als Sparpreis
    rail_min_fare: float = 2.50          # €
    train_transfers: int = 2             # höchstens so viele Umstiege (0 = nur direkt, bis 3)
    transfer_minutes: int = 5            # Mindestzeit zum Umsteigen
    weather: bool = True                 # Wetter berücksichtigen (Open-Meteo)
    rain_factor: float = 2.0             # bei Regen/Schnee zählt Zeit auf Rad und zu Fuß so viel
    cold_below: int = 3                  # °C - darunter ist es kalt
    cold_factor: float = 1.3             # dann zählt Zeit draußen so viel
    wind_above: int = 35                 # km/h - darüber ist es windig (nur Fahrrad)
    wind_factor: float = 1.3
    reminder: bool = True                # vor der Abfahrt von selbst melden
    reminder_minutes: int = 15           # so lange vor der empfohlenen Abfahrt
    reminder_display: str = "popup"      # popup, notice oder chat (wie proaktive Meldungen)
    reminder_speak: bool = False
    home_trip: bool = True               # nach dem letzten Termin des Tages den Heimweg zeigen
    home_trip_hours: int = 3             # so lange nach dessen Ende

    @classmethod
    def from_preferences(cls, preferences: PreferenceStore) -> TravelSettings:
        """Standard, darüber von Hand gesetzte "travel_<feld>", darüber die Werte aus dem Popup."""
        stored = preferences.get(TRAVEL_KEY)
        stored = stored if isinstance(stored, dict) else {}
        values: dict[str, Any] = {}
        for f in fields(cls):
            for value in (preferences.get(PREFERENCE_PREFIX + f.name), stored.get(f.name)):
                cleaned = _typed(f.default, value)
                if cleaned is not None:
                    values[f.name] = cleaned
        return cls(**values)


def _typed(default: Any, value: Any) -> Any:
    """Wert im Typ des Standards; None, wenn er nicht passt (dann gilt der Standard)."""
    if value is None:
        return None
    if isinstance(default, bool):
        return bool(value)
    if isinstance(default, (int, float)) and isinstance(value, (int, float)) and not isinstance(value, bool):
        return type(default)(value)
    if isinstance(default, str) and isinstance(value, str):
        return value
    if isinstance(default, tuple) and isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value):
        return tuple(value)
    return None


@dataclass(frozen=True)
class Segment:
    """Ein Stück des Wegs für die Karte, z. B. der Fußweg zum Bahnhof oder ein Zug."""
    kind: str                                   # WALK, TRANSIT (Bus/Tram, geschätzt), RAIL oder BUS (auch Tram)
    points: tuple[tuple[float, float], ...]     # (Länge, Breite)
    label: str = ""                             # z. B. "ICE 513: Mannheim Hbf → Stuttgart Hbf"
    end: str = ""                               # wo es endet, z. B. "Stuttgart Hbf" (Markierung auf der Karte)


@dataclass(frozen=True)
class Stage:
    """Abschnitt einer Bahn/ÖPNV-Verbindung für die Ansicht (Zeitleiste wie in der DB- oder VVS-App)."""
    kind: str                            # WALK, TRANSIT (Bus/Tram, geschätzt), RAIL oder BUS
    origin: str                          # "Start", Haltestelle bzw. Bahnhof
    destination: str                     # … bzw. "Ziel"
    departure: datetime.datetime         # mit Echtzeit: Prognose
    arrival: datetime.datetime
    line: str = ""                       # z. B. "S1", "Bus 91"
    mode: str = ""                       # wie in transit.py, z. B. SUBURBAN, BUS - für Farbe und Symbol
    headsign: str = ""                   # Richtung
    platform: str = ""                   # Gleis/Steig der Abfahrt
    arrival_platform: str = ""
    departure_delay: int = 0             # Minuten
    arrival_delay: int = 0
    realtime: bool = False
    stops: tuple[tuple[str, datetime.datetime | None], ...] = ()   # Zwischenhalte
    messages: tuple[str, ...] = ()
    color: str = ""                      # Linienfarbe aus der Auskunft, sonst nach Verkehrsmittel
    text_color: str = ""
    long_distance: bool = False          # Fernverkehr (ICE, IC, Fernbus): Deutschlandticket gilt nicht

    @property
    def minutes(self) -> int:
        return _minutes((self.arrival - self.departure).total_seconds())


@dataclass(frozen=True)
class Option:
    mode: str
    duration_s: float
    price_eur: float
    distance_m: float = 0.0
    price_estimated: bool = False        # Schätzung statt echtem Preis (in der Ansicht mit ≈)
    detail: str = ""                     # z. B. "RE 4 ab Mannheim Hbf 08:12, Gleis 3"
    steps: tuple[str, ...] = ()
    geometry: tuple[tuple[float, float], ...] = field(default=(), repr=False)
    depart_at: datetime.datetime | None = None
    arrive_at: datetime.datetime | None = None
    weather_factor: float = 1.0          # > 1: Zeit zählt wegen des Wetters mehr
    weather_note: str = ""               # z. B. "Regen: Zeit zählt ×2"
    segments: tuple[Segment, ...] = field(default=(), repr=False)   # Bahn: Fußwege und Züge einzeln
    title: str = ""                      # statt LABELS[mode], z. B. "ÖPNV" für eine Verbindung mit Bus
    attribution: str = ""                # Quelle, die unter der Ansicht steht (z. B. Transitous)
    stages: tuple[Stage, ...] = field(default=(), repr=False)   # Bahn/ÖPNV: Etappen für die Zeitleiste

    @property
    def label(self) -> str:
        return self.title or LABELS[self.mode]

    @property
    def free(self) -> bool:
        return self.price_eur == 0

    def cost(self, settings: TravelSettings) -> float:
        return self.price_eur + self.duration_s / 3600 * settings.value_of_time * self.weather_factor


@dataclass(frozen=True)
class TripPlan:
    origin: Place
    destination: Place
    arrive_by: datetime.datetime | None  # Terminbeginn; None bei depart_after
    options: tuple[Option, ...]          # nach Kosten sortiert, die erste ist die Empfehlung
    settings: TravelSettings
    notes: tuple[str, ...] = ()          # z. B. "Bahn: keine Verbindung gefunden"
    weather: Weather | None = None       # am Start, zur Abfahrt
    depart_after: datetime.datetime | None = None   # Heimweg: frühestens dann los

    @property
    def recommended(self) -> Option | None:
        return self.options[0] if self.options else None


def car_option(route: Route, fuel_price: float, fuel_price_estimated: bool, settings: TravelSettings,
               arrive_by: datetime.datetime | None, depart_after: datetime.datetime | None = None) -> Option:
    liters = route.distance_m / 1000 * settings.consumption / 100
    return _door_to_door(CAR, route, route.duration_s * settings.car_time_factor, liters * fuel_price,
                         fuel_price_estimated, settings, arrive_by, depart_after,
                         f"Sprit {liters:.1f} l × {fuel_price:.2f} €/l".replace(".", ","))


def taxi_option(route: Route, settings: TravelSettings, arrive_by: datetime.datetime | None,
                depart_after: datetime.datetime | None = None) -> Option:
    price = settings.taxi_base + route.distance_m / 1000 * settings.taxi_per_km
    duration = route.duration_s * settings.car_time_factor + settings.taxi_wait_minutes * 60
    return _door_to_door(TAXI, route, duration, price, True, settings, arrive_by, depart_after,
                         f"inkl. {settings.taxi_wait_minutes} Min. Wartezeit")


def bike_option(route: Route, settings: TravelSettings, arrive_by: datetime.datetime | None,
                depart_after: datetime.datetime | None = None) -> Option:
    return _door_to_door(BIKE, route, route.duration_s, 0.0, False, settings, arrive_by, depart_after)


def walk_option(route: Route, settings: TravelSettings, arrive_by: datetime.datetime | None,
                depart_after: datetime.datetime | None = None) -> Option:
    return _door_to_door(FOOT, route, route.duration_s, 0.0, False, settings, arrive_by, depart_after)


@dataclass(frozen=True)
class Leg:
    """Weg zum oder vom Bahnhof."""
    duration_s: float
    price_eur: float = 0.0
    description: str = ""                # z. B. "12 Min. zu Fuß"
    kind: str = WALK                     # WALK oder TRANSIT
    geometry: tuple[tuple[float, float], ...] = field(default=(), repr=False)   # Fußweg; Bus/Tram: ()


def walk_or_transit_leg(walk: Route, car: Route | None, settings: TravelSettings) -> Leg:
    """Zu Fuß zum Bahnhof, wenn es kurz genug ist; sonst Bus/Tram, geschätzt aus der Autofahrzeit."""
    if walk.duration_s <= settings.station_walk_minutes * 60 or car is None:
        return Leg(walk.duration_s, 0.0, f"{_minutes(walk.duration_s)} Min. zu Fuß", WALK, walk.geometry)
    duration = car.duration_s * 2 + 5 * 60   # Umwege und Wartezeit
    price = 0.0 if settings.deutschlandticket else settings.local_transit_fare
    return Leg(duration, price, f"≈ {_minutes(duration)} Min. Bus/Tram", TRANSIT)


def train_option(connection: TrainConnection | Journey, access: Leg, egress: Leg, rail_distance_km: float,
                 settings: TravelSettings) -> Option:
    """Bahn von Tür zu Tür; connection ist ein Zug oder eine Verbindung mit Umstiegen."""
    if connection.long_distance:
        fare = max(settings.rail_min_fare, rail_distance_km * settings.rail_long_distance_per_km)
    elif settings.deutschlandticket:
        fare = 0.0
    else:
        fare = max(settings.rail_min_fare, rail_distance_km * settings.rail_regional_per_km)
    price = fare + access.price_eur + egress.price_eur
    depart_at = connection.departure - datetime.timedelta(seconds=access.duration_s)
    arrive_at = connection.arrival + datetime.timedelta(seconds=egress.duration_s)
    legs = connection.legs
    steps = [f"{access.description} zu {connection.origin.name}"]
    for index, leg in enumerate(legs):
        if index:
            wait = _minutes((leg.departure - legs[index - 1].arrival).total_seconds())
            steps.append(f"Umstieg in {leg.origin.name}: {wait} Min."
                         + (f", weiter von Gleis {leg.platform}" if leg.platform else ""))
        steps.append(f"{leg.train} ab {leg.origin.name} {_clock(leg.departure, leg.departure_delay)}"
                     f"{_platform(leg.platform)}, an {leg.destination.name} {_clock(leg.arrival, leg.arrival_delay)}")
        steps += [f"Hinweis zu {leg.train}: {message}" for message in leg.messages[:MAX_TRAIN_MESSAGES]]
    steps.append(f"{egress.description} zum Ziel")
    first = legs[0]
    detail = (f"{first.train} ab {first.origin.name} {_clock(first.departure, first.departure_delay)}"
              f"{_platform(first.platform)}")
    if len(legs) > 1:
        places = _enumeration([leg.origin.name for leg in legs[1:]])
        detail += f", Umstieg in {places}" if len(legs) == 2 else f", {len(legs) - 1} Umstiege: {places}"
    stages = [Stage(access.kind, "Start", connection.origin.name, depart_at, connection.departure,
                    line="Bus/Tram" if access.kind == TRANSIT else "")]
    stages += [Stage(RAIL, leg.origin.name, leg.destination.name, leg.departure, leg.arrival, leg.train,
                     _db_mode(leg), platform=leg.platform, arrival_platform=leg.arrival_platform,
                     departure_delay=leg.departure_delay, arrival_delay=leg.arrival_delay, realtime=leg.realtime,
                     messages=leg.messages, long_distance=leg.long_distance) for leg in legs]
    stages.append(Stage(egress.kind, connection.destination.name, "Ziel", connection.arrival, arrive_at,
                        line="Bus/Tram" if egress.kind == TRANSIT else ""))
    return Option(TRAIN, (arrive_at - depart_at).total_seconds(), price, rail_distance_km * 1000,
                  price_estimated=price > 0, detail=detail, steps=tuple(steps), depart_at=depart_at,
                  arrive_at=arrive_at, stages=tuple(stages))


def _db_mode(leg: TrainConnection) -> str:
    """Verkehrsmittel wie in transit.py für einen Zug aus den DB-Tafeln."""
    if leg.long_distance:
        return "LONG_DISTANCE"
    return "SUBURBAN" if leg.train.startswith("S") and leg.train[1:].strip()[:1].isdigit() else "REGIONAL_RAIL"


def transit_option(journey: transit.Journey, settings: TravelSettings) -> Option:
    """Bahn/ÖPNV von Tür zu Tür (VVS oder Transitous): Fußwege, Busse, Trams und Züge schon enthalten.
    Preis: der echte Einzelfahrschein, wenn die Auskunft ihn kennt (VVS), sonst geschätzt wie bei
    train_option aus der Länge der gefahrenen Strecken. Mit Deutschlandticket ohne Fernverkehr: 0 €."""
    rides = journey.rides
    ride_km = sum(leg.distance_km for leg in rides)
    estimated = journey.fare_eur is None
    if settings.deutschlandticket and not journey.long_distance:
        fare, estimated = 0.0, False
    elif not estimated:
        fare = journey.fare_eur
    elif journey.long_distance:
        fare = max(settings.rail_min_fare, ride_km * settings.rail_long_distance_per_km)
    else:
        fare = max(settings.rail_min_fare, ride_km * settings.rail_regional_per_km)
    steps, segments, previous, walked = [], [], None, False
    stages = tuple(Stage(WALK if leg.walking else RAIL if leg.rail else BUS, leg.origin, leg.destination,
                         leg.departure, leg.arrival, leg.line, leg.mode, leg.headsign, leg.platform,
                         leg.arrival_platform, leg.departure_delay, leg.arrival_delay, leg.realtime, leg.stops,
                         leg.messages, leg.color, leg.text_color, leg.long_distance) for leg in journey.legs)
    for index, leg in enumerate(journey.legs):
        last = index == len(journey.legs) - 1
        if leg.walking:
            walked = previous is not None and not last   # Fußweg beim Umsteigen, z. B. zu einer anderen Haltestelle
            text = (f"{'Umstieg: ' if walked else ''}{_minutes((leg.arrival - leg.departure).total_seconds())} Min. "
                    f"zu Fuß {'zum Ziel' if last else f'zu {leg.destination}'}")
            steps.append(text)
            segments.append(Segment(WALK, leg.geometry, text, "" if last else leg.destination))
            continue
        if previous is not None and not walked:
            wait = _minutes((leg.departure - previous.arrival).total_seconds())
            steps.append(f"Umstieg in {leg.origin}: {wait} Min." + (f", weiter von {_stand(leg)} {leg.platform}"
                                                                     if leg.platform else ""))
        walked = False
        direction = f" Richtung {leg.headsign}" if leg.headsign else ""
        steps.append(f"{leg.line}{direction} ab {leg.origin} {_clock(leg.departure, leg.departure_delay)}"
                     f"{f', {_stand(leg)} {leg.platform}' if leg.platform else ''}, "
                     f"an {leg.destination} {_clock(leg.arrival, leg.arrival_delay)}")
        steps += [f"Hinweis zu {leg.line}: {message}" for message in leg.messages[:MAX_TRAIN_MESSAGES]]
        segments.append(Segment(RAIL if leg.rail else BUS, leg.geometry,
                                f"{leg.line}: {leg.origin} → {leg.destination}", leg.destination))
        previous = leg
    first = rides[0]
    detail = (f"{first.line} ab {first.origin} {_clock(first.departure, first.departure_delay)}"
              f"{f', {_stand(first)} {first.platform}' if first.platform else ''}")
    if len(rides) > 1:
        places = _enumeration([leg.origin for leg in rides[1:]])
        detail += f", Umstieg in {places}" if len(rides) == 2 else f", {len(rides) - 1} Umstiege: {places}"
    geometry = [point for segment in segments for point in segment.points]
    return Option(TRAIN, (journey.arrival - journey.departure).total_seconds(), fare, ride_km * 1000,
                  price_estimated=estimated, detail=detail, steps=tuple(steps),
                  geometry=tuple(p for i, p in enumerate(geometry) if i == 0 or p != geometry[i - 1]),
                  depart_at=journey.departure, arrive_at=journey.arrival, segments=tuple(segments),
                  title="Bahn" if all(leg.rail for leg in rides) else "ÖPNV", attribution=journey.attribution,
                  stages=stages)


def _enumeration(names: list[str]) -> str:
    """["A", "B", "C"] → "A, B und C" (Namen dürfen selbst Kommas enthalten)."""
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} und {names[-1]}"


def _stand(leg: transit.Leg) -> str:
    return "Gleis" if leg.rail else "Steig"


def apply_weather(options: list[Option], weather: Weather | None, settings: TravelSettings) -> list[Option]:
    """Fahrrad und zu Fuß bei Regen, Kälte und (nur Rad) Wind schlechter bewerten."""
    if weather is None or not settings.weather:
        return options
    result = []
    for option in options:
        factor, reasons = 1.0, []
        if option.mode in OUTDOOR:
            if weather.wet:
                factor *= settings.rain_factor
                reasons.append("Regen" if weather.temperature_c > 1 else "Niederschlag")
            if weather.temperature_c < settings.cold_below:
                factor *= settings.cold_factor
                reasons.append("Kälte")
            if option.mode == BIKE and weather.wind_kmh > settings.wind_above:
                factor *= settings.wind_factor
                reasons.append("Wind")
        if factor > 1:
            option = replace(option, weather_factor=factor,
                             weather_note=f"{', '.join(reasons)}: Zeit zählt ×{factor:.1f}".replace(".", ","))
        result.append(option)
    return result


def rank(options: list[Option], settings: TravelSettings,
         arrive_by: datetime.datetime | None = None) -> tuple[Option, ...]:
    """Nach Kosten; mit prefer_free die bevorzugten kostenlosen zuerst (siehe preferred_free). Mit
    arrive_by (Terminbeginn) vorher alle, die rechtzeitig ankommen."""
    preferred = preferred_free(options, settings)
    return tuple(sorted(options, key=lambda option: (minutes_late(option, arrive_by) > 0, option not in preferred,
                                                     option.cost(settings))))


def minutes_late(option: Option, arrive_by: datetime.datetime | None) -> int:
    """So viele Minuten kommt das Verkehrsmittel nach arrive_by an (0 = rechtzeitig oder ohne Termin)."""
    if arrive_by is None or option.arrive_at is None or option.arrive_at <= arrive_by:
        return 0
    return math.ceil((option.arrive_at - arrive_by).total_seconds() / 60)


def preferred_free(options: list[Option] | tuple[Option, ...], settings: TravelSettings) -> list[Option]:
    """Kostenlose Verkehrsmittel, die vor die anderen kommen: nicht Rad/zu Fuß bei schlechtem Wetter
    und höchstens free_max_extra_minutes länger als das schnellste kostenpflichtige (0 = egal)."""
    if not settings.prefer_free:
        return []
    fastest_paid = min((o.duration_s for o in options if not o.free), default=None)
    limit = settings.free_max_extra_minutes * 60
    return [o for o in options if o.free and o.weather_factor <= 1
            and not (limit and fastest_paid is not None and o.duration_s > fastest_paid + limit)]


def _door_to_door(mode: str, route: Route, duration_s: float, price: float, estimated: bool,
                  settings: TravelSettings, arrive_by: datetime.datetime | None,
                  depart_after: datetime.datetime | None = None, detail: str = "") -> Option:
    """Mit arrive_by: rechtzeitig (Puffer) ankommen. Mit depart_after: dann losfahren."""
    if depart_after is not None:
        depart_at = depart_after
        arrive_at = depart_after + datetime.timedelta(seconds=duration_s)
    else:
        arrive_at = arrive_by - datetime.timedelta(minutes=settings.buffer_minutes)
        depart_at = arrive_at - datetime.timedelta(seconds=duration_s)
    return Option(mode, duration_s, price, route.distance_m, estimated, detail,
                  tuple(step.instruction for step in route.steps if step.instruction), route.geometry,
                  depart_at, arrive_at)


def _clock(moment: datetime.datetime, delay_minutes: int) -> str:
    """Zeit mit Verspätung wie auf der Anzeigetafel: "09:37 (+5)" - die Zeit ist schon die Prognose."""
    return f"{moment:%H:%M}" + (f" (+{delay_minutes})" if delay_minutes > 0 else "")


def _platform(platform: str) -> str:
    return f", Gleis {platform}" if platform else ""


def _minutes(seconds: float) -> int:
    return max(1, round(seconds / 60))
