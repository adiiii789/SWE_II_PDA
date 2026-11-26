"""Welche Stimme vorliest (Einstellungen → Stimme im Popup).

Zur Auswahl stehen die Thorsten-Stimmen von Piper, dazu "Standard" = config.PIPER_VOICE
(PDA_PIPER_VOICE). Die emotionale Stimme hat acht Sprecher in einer Datei; ein Eintrag ist
deshalb "Modell" oder "Modell:Sprecher". Noch nicht heruntergeladene Stimmen lädt
PiperSynthesizer (backend/speech.py) beim ersten Vorlesen - das Formular sagt, wie groß sie sind.

Neue Stimme: Eintrag in VOICES, Name wie im Katalog (python -m piper.download_voices).
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.assistant.settings import VOICE_KEY, Choice, Setting, _cleaned, _merged
from backend.preferences import PreferenceStore
from backend.speech import Voice

STANDARD = "standard"
SAMPLE_TEXT = "Hallo, so klinge ich. Soll ich dir deine Termine für heute vorlesen?"

_EMOTIONAL = "de_DE-thorsten_emotional-medium"


@dataclass(frozen=True)
class VoiceOption:
    value: str      # gespeicherter Wert: "Modell" oder "Modell:Sprecher"
    label: str
    size_mb: int    # Download beim ersten Gebrauch


VOICES: tuple[VoiceOption, ...] = (
    VoiceOption("de_DE-thorsten-low", "Thorsten - einfach", 63),
    VoiceOption("de_DE-thorsten-medium", "Thorsten - mittel", 63),
    VoiceOption("de_DE-thorsten-high", "Thorsten - beste Qualität", 114),
    *(VoiceOption(f"{_EMOTIONAL}:{speaker}", f"Thorsten emotional - {label}", 77) for speaker, label in (
        ("neutral", "neutral"),
        ("amused", "belustigt"),
        ("surprised", "überrascht"),
        ("sleepy", "müde"),
        ("whisper", "flüsternd"),
        ("angry", "wütend"),
        ("disgusted", "angewidert"),
        ("drunk", "betrunken"),
    )),
)

SPEEDS: dict[str, float] = {"langsam": 1.25, "normal": 1.0, "schnell": 0.85}   # Piper length_scale


def parse(value: str, default_model: str) -> tuple[str, str | None]:
    """Gespeicherter Wert -> (Modell, Sprecher oder None)."""
    model, _, speaker = (default_model if value == STANDARD else value).partition(":")
    return model, speaker or None


class VoiceSettings:
    """Liest und schreibt die Stimme im PreferenceStore; hält selbst keinen Zustand."""

    def __init__(self, store: PreferenceStore, voice_dir: Path, default_model: str):
        self.store = store
        self.voice_dir = voice_dir
        self.default_model = default_model

    def _settings(self) -> tuple[Setting, ...]:
        def label(option: VoiceOption) -> str:
            model, _ = parse(option.value, self.default_model)
            loaded = (self.voice_dir / f"{model}.onnx").exists()
            return option.label if loaded else f"{option.label} (lädt beim ersten Mal ≈ {option.size_mb} MB)"

        voices = (Choice(STANDARD, f"Standard ({self.default_model})"),
                  *(Choice(option.value, label(option)) for option in VOICES))
        return (
            Setting("voice", "Stimme", "choice", STANDARD, voices,
                    help="Gilt für Antworten und proaktive Meldungen. Nur mit Piper; sonst spricht die "
                         "Systemstimme."),
            Setting("speed", "Tempo", "choice", "normal", (
                Choice("langsam", "Langsam"),
                Choice("normal", "Normal"),
                Choice("schnell", "Schnell"),
            )),
        )

    def values(self) -> dict[str, Any]:
        return _merged(self._settings(), self.store.get(VOICE_KEY) or {})

    def form(self) -> dict[str, Any]:
        """Gleicher Aufbau wie der Bereich "answer" - das Popup zeigt ihn mit denselben Feldern."""
        return {"fields": [setting.to_dict() for setting in self._settings()], "values": self.values(),
                "sample": SAMPLE_TEXT}

    def validated(self, changes: Mapping[str, Any] | None) -> dict[str, Any] | None:
        """Neuer Stand; ValueError bei ungültigen Werten. Geschrieben wird erst mit store_validated."""
        if changes is None:
            return None
        return {**(self.store.get(VOICE_KEY) or {}), **_cleaned(self._settings(), changes)}

    def store_validated(self, validated: dict[str, Any] | None) -> None:
        if validated is not None:
            self.store.set(VOICE_KEY, validated)

    def reset(self) -> None:
        self.store.set(VOICE_KEY, {})

    def voice(self, values: Mapping[str, Any] | None = None) -> Voice:
        """Die eingestellte Stimme - oder die aus values (Probe vor dem Speichern, wird geprüft)."""
        chosen = self.values() if values is None else {**self.values(), **_cleaned(self._settings(), values)}
        model, speaker = parse(chosen["voice"], self.default_model)
        return Voice(model, speaker, SPEEDS[chosen["speed"]])
