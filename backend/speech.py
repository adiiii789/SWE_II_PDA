"""Sprachliche Ein- und Ausgabe - komplett lokal.

Sprache läuft in Python, nicht im Browser: Qt WebEngine bringt keine
Spracherkennung mit.

Spracheingabe (Speech-to-Text): Mikrofon über sounddevice aufnehmen, faster-whisper
macht daraus Text. Das Whisper-Modell wird beim ersten Gebrauch geladen.
Sprachausgabe (Text-to-Speech): Piper (neuronale Stimme, wird beim ersten Gebrauch
geladen); geht das nicht, eine installierte macOS-Stimme oder Windows-Stimme (SAPI).

Ablauf im Chat (frontend/popup.js über backend/api.py): Mikrofon-Knopf ->
start(), zweiter Klick -> stop() liefert den Text, Escape -> cancel(). Alle
Bridge-Aufrufe laufen nacheinander in einem Hintergrund-Thread - deshalb kehren
start() und speak() sofort zurück, sonst käme ein Abbruch erst danach an.

Fehlen die Pakete, liefern create_speech_input() / create_speech_output() None und
das Frontend blendet die Sprachfunktionen aus.
"""
from __future__ import annotations

import importlib.util
import logging
import re
import subprocess
import sys
import tempfile
import threading
import wave
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from backend import config

log = logging.getLogger(__name__)

WHISPER_SAMPLE_RATE = 16000     # erwartet faster-whisper
MIN_RECORDING_S = 0.3           # kürzer = versehentlicher Doppelklick, nichts erkennen


@runtime_checkable
class SpeechInput(Protocol):
    def start(self) -> None:
        """Aufnahme starten; kehrt sofort zurück."""
        ...

    def stop(self) -> str:
        """Aufnahme beenden und als Text zurückgeben (leer, wenn nichts erkannt wurde)."""
        ...

    def cancel(self) -> None:
        """Aufnahme verwerfen."""
        ...


@runtime_checkable
class SpeechOutput(Protocol):
    def speak(self, text: str, voice: Voice | None = None) -> None:
        """Text vorlesen; kehrt sofort zurück und unterbricht, was gerade gesprochen wird.
        voice: einmal eine andere Piper-Stimme (Probe in den Einstellungen), sonst die eingestellte."""
        ...

    def stop(self) -> None:
        """Vorlesen abbrechen."""
        ...


# --- Spracheingabe -------------------------------------------------------------

class Microphone:
    """Nimmt mono mit WHISPER_SAMPLE_RATE auf; die Aufnahme läuft im Audio-Thread von sounddevice."""

    def __init__(self, sample_rate: int = WHISPER_SAMPLE_RATE):
        self.sample_rate = sample_rate
        self._stream: Any = None
        self._chunks: list[Any] = []

    def start(self) -> None:
        import sounddevice as sd

        if self._stream is not None:
            return
        _require_microphone_access()
        self._chunks = []
        try:
            stream = sd.InputStream(samplerate=self.sample_rate, channels=1, dtype="float32",
                                    callback=self._on_audio)
            try:
                stream.start()
            except Exception:
                stream.close()
                raise
            self._stream = stream
        except sd.PortAudioError as exc:
            raise RuntimeError(f"Kein Mikrofon verfügbar: {exc}") from exc

    def stop(self) -> Any:
        """Aufnahme beenden; liefert die Samples als float32-Array (leer, wenn nicht aufgenommen wurde)."""
        import numpy as np

        stream, self._stream = self._stream, None
        if stream is not None:
            stream.stop()
            stream.close()
        chunks, self._chunks = self._chunks, []
        return np.concatenate(chunks)[:, 0] if chunks else np.zeros(0, dtype=np.float32)

    def _on_audio(self, data, frames, time, status) -> None:  # noqa: ARG002 (sounddevice-API)
        self._chunks.append(data.copy())


class WhisperTranscriber:
    """faster-whisper auf der CPU; das Modell wird einmal geladen (beim ersten Mal heruntergeladen)."""

    def __init__(self, model_size: str, language: str | None, download_dir: Path):
        self._model_size = model_size
        self._language = language
        self._download_dir = download_dir
        self._model: Any = None
        self._lock = threading.Lock()

    def preload(self) -> None:
        """Modell im Hintergrund laden, damit transcribe() nach der Aufnahme nicht darauf warten muss."""
        if self._model is None:
            threading.Thread(target=self._load, name="whisper-load", daemon=True).start()

    def transcribe(self, audio: Any) -> str:
        segments, _info = self._load().transcribe(audio, language=self._language, vad_filter=True)
        return " ".join(segment.text.strip() for segment in segments).strip()

    def _load(self) -> Any:
        with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel

                log.info("Lade Whisper-Modell %r …", self._model_size)
                self._model = WhisperModel(self._model_size, device="cpu", compute_type="int8",
                                           download_root=str(self._download_dir))
            return self._model


class VoiceInput:
    """SpeechInput aus Mikrofon und Transkription."""

    def __init__(self, microphone: Any, transcriber: Any):
        self._microphone = microphone
        self._transcriber = transcriber

    def start(self) -> None:
        self._microphone.start()
        self._transcriber.preload()

    def stop(self) -> str:
        audio = self._microphone.stop()
        if len(audio) < MIN_RECORDING_S * self._microphone.sample_rate:
            return ""
        return self._transcriber.transcribe(audio)

    def cancel(self) -> None:
        self._microphone.stop()


# --- Sprachausgabe -------------------------------------------------------------

@dataclass(frozen=True)
class Voice:
    """Welche Piper-Stimme spricht (Einstellungen → Stimme, backend/voice_settings.py).

    model: Name wie "de_DE-thorsten-medium"; speaker: Sprecher bei Stimmen mit mehreren
    (z. B. "neutral" bei de_DE-thorsten_emotional-medium), None = deren Standard;
    length_scale: Tempo, unter 1 schneller, über 1 langsamer."""

    model: str
    speaker: str | None = None
    length_scale: float = 1.0


class Synthesizer(Protocol):
    def synthesize(self, text: str, voice: Voice | None = None) -> tuple[Any, int]:
        """Text in Audio umwandeln: (int16-Samples mono, Abtastrate). voice gilt nur für Piper."""
        ...


class PiperSynthesizer:
    """Neuronale Stimme mit Piper; eine Stimme wird beim ersten Gebrauch heruntergeladen.

    Welche Stimme spricht, fragt er bei jedem Text neu ab (voice: feste Stimme oder eine Funktion,
    die die eingestellte liefert) - so gilt eine Änderung in den Einstellungen sofort."""

    def __init__(self, voice: Voice | str | Callable[[], Voice], voice_dir: Path):
        fixed = Voice(voice) if isinstance(voice, str) else voice
        self._current: Callable[[], Voice] = fixed if callable(fixed) else (lambda: fixed)
        self._voice_dir = voice_dir
        self._loaded: tuple[str, Any] | None = None   # (Modellname, PiperVoice) - nur eine im Speicher
        self._lock = threading.Lock()   # Vorlesen und Probe laufen je in einem eigenen Thread

    def synthesize(self, text: str, voice: Voice | None = None) -> tuple[Any, int]:
        import numpy as np
        from piper import SynthesisConfig

        choice = voice or self._current()
        with self._lock:
            piper_voice = self._load(choice.model)
        speaker_id = None
        if choice.speaker is not None:
            speaker_id = piper_voice.config.speaker_id_map.get(choice.speaker)
            if speaker_id is None:
                log.warning("Stimme %s kennt den Sprecher %r nicht", choice.model, choice.speaker)
        synthesis = SynthesisConfig(speaker_id=speaker_id, length_scale=choice.length_scale)
        chunks = [chunk.audio_int16_array for chunk in piper_voice.synthesize(text, synthesis)]
        audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.int16)
        return audio, piper_voice.config.sample_rate

    def _load(self, name: str) -> Any:
        if self._loaded is None or self._loaded[0] != name:
            from piper import PiperVoice

            model = self._voice_dir / f"{name}.onnx"
            if not model.exists():
                from piper.download_voices import download_voice

                log.info("Lade Piper-Stimme %r …", name)
                self._voice_dir.mkdir(parents=True, exist_ok=True)
                download_voice(name, self._voice_dir)
            self._loaded = (name, PiperVoice.load(model))
        return self._loaded[1]


class MacSynthesizer:
    """Installierte macOS-Stimme über say; kein zusätzlicher Download nötig."""

    def __init__(self, language: str | None, voice: str = ""):
        self._language = language
        self._voice = voice
        self._selected = bool(voice)

    def _select_voice(self) -> str:
        if not self._selected:
            voices = subprocess.run(["/usr/bin/say", "-v", "?"], capture_output=True, text=True,
                                    check=True, timeout=15).stdout
            for line in voices.splitlines():
                match = re.match(r"^(.+?)\s+([a-z]{2,3})[_-][A-Za-z_]+\s", line)
                if match and match[2] == self._language:
                    self._voice = match[1].strip()
                    break
            self._selected = True
        return self._voice

    def synthesize(self, text: str, voice: Voice | None = None) -> tuple[Any, int]:
        import numpy as np

        voice = self._select_voice()
        with tempfile.TemporaryDirectory(prefix="pda-speech-") as folder:
            output = Path(folder) / "speech.wav"
            command = ["/usr/bin/say", "--file-format=WAVE", "--data-format=LEI16@22050", "--channels=1",
                       "-o", str(output)]
            if voice:
                command += ["-v", voice]
            # Über stdin übergeben: Nachrichtentext kann keine Kommandozeilenoptionen einschleusen.
            subprocess.run(command, input=text, text=True, check=True, capture_output=True, timeout=120)
            with wave.open(str(output), "rb") as audio:
                return np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2").copy(), audio.getframerate()


class SapiSynthesizer:
    """Eingebaute Windows-Stimme; bevorzugt eine in SPEECH_LANGUAGE, sonst die Standardstimme."""

    _FORMAT_22KHZ_16BIT_MONO = 22   # SpeechAudioFormatType.SAFT22kHz16BitMono
    _SAMPLE_RATE = 22050
    _LANGUAGE_IDS = {"de": "407", "en": "409"}   # Windows-Sprachkennungen (hex)

    def __init__(self, language: str | None):
        self._language = language

    def synthesize(self, text: str, voice: Voice | None = None) -> tuple[Any, int]:
        import numpy as np
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()   # COM pro Thread; mehrfach aufrufen ist erlaubt
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        self._select_voice(voice)
        stream = win32com.client.Dispatch("SAPI.SpMemoryStream")
        stream.Format.Type = self._FORMAT_22KHZ_16BIT_MONO
        voice.AudioOutputStream = stream
        voice.Speak(text)
        return np.frombuffer(bytes(stream.GetData()), dtype=np.int16), self._SAMPLE_RATE

    def _select_voice(self, voice: Any) -> None:
        wanted = self._LANGUAGE_IDS.get(self._language or "")
        if wanted is None:
            return
        for token in voice.GetVoices():
            if wanted in token.GetAttribute("Language").lower().split(";"):
                voice.Voice = token
                return


class FallbackSynthesizer:
    """Nimmt den ersten Synthesizer, der funktioniert; ein fehlgeschlagener wird nicht erneut versucht."""

    def __init__(self, synthesizers: Sequence[Synthesizer]):
        self._synthesizers = list(synthesizers)

    def synthesize(self, text: str, voice: Voice | None = None) -> tuple[Any, int]:
        while self._synthesizers:
            synthesizer = self._synthesizers[0]
            try:
                return synthesizer.synthesize(text, voice)
            except Exception:  # noqa: BLE001  # z. B. Stimme nicht ladbar - nächsten versuchen
                log.exception("%s geht nicht, nehme den nächsten", type(synthesizer).__name__)
                self._synthesizers.pop(0)
        raise RuntimeError("Keine Sprachausgabe verfügbar")


class AudioPlayer:
    """Spielt über das Standard-Ausgabegerät; play() kehrt sofort zurück, wait() wartet aufs Ende."""

    def play(self, audio: Any, sample_rate: int) -> None:
        import sounddevice as sd

        sd.play(audio, sample_rate)

    def wait(self) -> None:
        """Bis das Abspielen fertig oder per stop() abgebrochen ist."""
        import sounddevice as sd

        sd.wait()

    def stop(self) -> None:
        import sounddevice as sd

        sd.stop()


class VoiceOutput:
    """SpeechOutput: erzeugt das Audio in einem eigenen Thread und spielt es ab.

    on_change(speaking) meldet, ob gerade vorgelesen wird: True, sobald ein Text angenommen ist (die
    Stimme rechnet noch oder spielt), False, wenn er fertig, abgebrochen oder fehlgeschlagen ist -
    das Popup zeigt damit den Knopf zum Unterbrechen (frontend/popup.js)."""

    def __init__(self, synthesizer: Synthesizer, player: Any, on_change: Callable[[bool], None] | None = None):
        self._synthesizer = synthesizer
        self._player = player
        self._on_change = on_change
        self._generation = 0          # stop()/speak() machen ältere, noch laufende Aufträge ungültig
        self._speaking = False
        self._lock = threading.Lock()

    def speak(self, text: str, voice: Voice | None = None) -> None:
        text = speakable(text)
        with self._lock:
            self._generation += 1
            generation = self._generation
            self._report(bool(text))
        self._player.stop()
        if text:
            threading.Thread(target=self._speak, args=(text, generation, voice), name="speech-out",
                             daemon=True).start()

    def stop(self) -> None:
        with self._lock:
            self._generation += 1
            self._report(False)
        self._player.stop()

    def _speak(self, text: str, generation: int, voice: Voice | None) -> None:
        try:
            audio, sample_rate = self._synthesizer.synthesize(text, voice)
        except Exception:  # noqa: BLE001  # läuft im eigenen Thread - nur protokollieren
            log.exception("Vorlesen fehlgeschlagen")
            self._finish(generation)
            return
        with self._lock:
            if generation != self._generation:
                return
            self._player.play(audio, sample_rate)
        try:
            self._player.wait()
        except Exception:  # noqa: BLE001  # z. B. Gerät weg - dann ist das Vorlesen eben vorbei
            log.exception("Warten aufs Vorlesen fehlgeschlagen")
        self._finish(generation)

    def _finish(self, generation: int) -> None:
        """Auftrag ist durch - nur melden, wenn inzwischen kein neuer angefangen hat."""
        with self._lock:
            if generation == self._generation:
                self._report(False)

    def _report(self, speaking: bool) -> None:
        """Nur Änderungen melden; läuft unter self._lock, damit die Reihenfolge stimmt."""
        if speaking == self._speaking:
            return
        self._speaking = speaking
        if self._on_change is not None:
            try:
                self._on_change(speaking)
            except Exception:  # noqa: BLE001  # Anzeige ist Zugabe - Vorlesen geht trotzdem
                log.exception("Vorlese-Zustand nicht gemeldet")


_MARKDOWN = re.compile(r"[*_#`>|~]+")
_URL = re.compile(r"https?://\S+")


def speakable(text: str) -> str:
    """Markdown-Zeichen und Links entfernen - die würde die Stimme sonst mitlesen."""
    text = _URL.sub("", text)
    text = _MARKDOWN.sub(" ", text)
    return re.sub(r"[ \t]+", " ", text).strip()


# --- Fabriken ------------------------------------------------------------------

def _installed(*modules: str) -> bool:
    return all(importlib.util.find_spec(module) is not None for module in modules)


def _require_microphone_access() -> None:
    if sys.platform == "darwin":
        from backend.desktop.macos import require_microphone_access
        require_microphone_access()


def load_before_qt() -> None:
    """Vor dem ersten PyQt5-Import aufrufen (main.py, tests/conftest.py).

    PyQt5 bringt eine ältere msvcp140.dll mit. Ist Qt zuerst geladen, stürzt der
    Import von onnxruntime (Piper, Sprachfilter von faster-whisper) mit einer
    Zugriffsverletzung ab - lädt onnxruntime zuerst, gibt es keinen Konflikt.
    """
    if _installed("onnxruntime"):
        import onnxruntime  # noqa: F401


def create_speech_input() -> SpeechInput | None:
    """Spracheingabe mit Whisper, oder None, wenn die Pakete fehlen."""
    if not _installed("sounddevice", "numpy", "faster_whisper"):
        log.info("Spracheingabe aus: sounddevice/faster-whisper nicht installiert")
        return None
    transcriber = WhisperTranscriber(config.WHISPER_MODEL, config.SPEECH_LANGUAGE or None,
                                     config.SPEECH_DIR / "whisper")
    return VoiceInput(Microphone(), transcriber)


def create_speech_output(voice: Callable[[], Voice] | None = None,
                         on_change: Callable[[bool], None] | None = None) -> SpeechOutput | None:
    """Sprachausgabe mit Piper und plattformspezifischer Ersatzstimme.
    voice: liefert die eingestellte Piper-Stimme (backend/voice_settings.py); ohne gilt config.PIPER_VOICE.
    on_change: bekommt True/False, wenn das Vorlesen anfängt/aufhört (siehe VoiceOutput)."""
    if not _installed("sounddevice", "numpy"):
        log.info("Sprachausgabe aus: sounddevice nicht installiert")
        return None
    synthesizers: list[Synthesizer] = []
    if _installed("piper"):
        synthesizers.append(PiperSynthesizer(voice or Voice(config.PIPER_VOICE), config.SPEECH_DIR / "piper"))
    if sys.platform == "darwin":
        synthesizers.append(MacSynthesizer(config.SPEECH_LANGUAGE or None, config.MAC_VOICE))
    elif sys.platform == "win32" and _installed("win32com"):
        synthesizers.append(SapiSynthesizer(config.SPEECH_LANGUAGE or None))
    if not synthesizers:
        log.info("Sprachausgabe aus: keine Stimme verfügbar")
        return None
    return VoiceOutput(FallbackSynthesizer(synthesizers), AudioPlayer(), on_change)
