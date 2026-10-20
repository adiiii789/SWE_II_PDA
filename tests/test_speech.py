"""Tests für backend/speech.py - mit Attrappen statt Mikrofon, Lautsprecher und Modellen."""
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from backend import speech


class FakeMicrophone:
    sample_rate = 16000

    def __init__(self, seconds=1.0):
        self.samples = np.zeros(int(seconds * self.sample_rate), dtype=np.float32)
        self.started = 0
        self.stopped = 0

    def start(self):
        self.started += 1

    def stop(self):
        self.stopped += 1
        return self.samples


class FakeTranscriber:
    def __init__(self, text="Wie wird das Wetter?"):
        self.text = text
        self.preloaded = 0
        self.transcribed = []

    def preload(self):
        self.preloaded += 1

    def transcribe(self, audio):
        self.transcribed.append(audio)
        return self.text


class VoiceInputTest(unittest.TestCase):
    def test_satisfies_protocol(self):
        self.assertIsInstance(speech.VoiceInput(FakeMicrophone(), FakeTranscriber()), speech.SpeechInput)

    def test_start_preloads_model_and_stop_returns_text(self):
        microphone, transcriber = FakeMicrophone(), FakeTranscriber()
        voice_input = speech.VoiceInput(microphone, transcriber)
        voice_input.start()
        self.assertEqual((microphone.started, transcriber.preloaded), (1, 1))
        self.assertEqual(voice_input.stop(), "Wie wird das Wetter?")
        self.assertIs(transcriber.transcribed[0], microphone.samples)

    def test_too_short_recording_is_not_transcribed(self):
        transcriber = FakeTranscriber()
        voice_input = speech.VoiceInput(FakeMicrophone(seconds=0.1), transcriber)
        voice_input.start()
        self.assertEqual(voice_input.stop(), "")
        self.assertEqual(transcriber.transcribed, [])

    def test_cancel_stops_microphone_without_transcribing(self):
        microphone, transcriber = FakeMicrophone(), FakeTranscriber()
        voice_input = speech.VoiceInput(microphone, transcriber)
        voice_input.start()
        voice_input.cancel()
        self.assertEqual(microphone.stopped, 1)
        self.assertEqual(transcriber.transcribed, [])


class MicrophoneTest(unittest.TestCase):
    def test_collects_chunks_until_stop(self):
        stream = mock.MagicMock()
        with mock.patch("sounddevice.InputStream", return_value=stream) as input_stream:
            microphone = speech.Microphone()
            microphone.start()
            microphone.start()   # läuft schon - kein zweiter Stream
            callback = input_stream.call_args.kwargs["callback"]
            callback(np.ones((160, 1), dtype=np.float32), 160, None, None)
            callback(np.ones((80, 1), dtype=np.float32), 80, None, None)
            audio = microphone.stop()
        input_stream.assert_called_once()
        stream.start.assert_called_once()
        stream.close.assert_called_once()
        self.assertEqual(audio.shape, (240,))

    def test_stop_without_start_returns_empty_audio(self):
        self.assertEqual(len(speech.Microphone().stop()), 0)

    def test_missing_device_gives_readable_error(self):
        import sounddevice as sd

        with mock.patch("sounddevice.InputStream", side_effect=sd.PortAudioError("no device")):
            with self.assertRaisesRegex(RuntimeError, "Kein Mikrofon"):
                speech.Microphone().start()


class WhisperTranscriberTest(unittest.TestCase):
    def test_loads_model_once_and_joins_segments(self):
        model = mock.MagicMock()
        model.transcribe.return_value = ([mock.Mock(text=" Hallo"), mock.Mock(text=" Welt. ")], None)
        with mock.patch("faster_whisper.WhisperModel", return_value=model) as whisper_model:
            transcriber = speech.WhisperTranscriber("tiny", "de", speech.config.SPEECH_DIR)
            self.assertEqual(transcriber.transcribe(np.zeros(10)), "Hallo Welt.")
            transcriber.transcribe(np.zeros(10))
        whisper_model.assert_called_once()
        self.assertEqual(model.transcribe.call_args.kwargs["language"], "de")

    def test_preload_loads_in_background(self):
        transcriber = speech.WhisperTranscriber("tiny", None, speech.config.SPEECH_DIR)
        with mock.patch.object(threading, "Thread") as thread:
            transcriber.preload()
        thread.assert_called_once()
        thread.return_value.start.assert_called_once()

    def test_no_preload_when_model_is_loaded(self):
        transcriber = speech.WhisperTranscriber("tiny", None, speech.config.SPEECH_DIR)
        transcriber._model = object()
        with mock.patch.object(threading, "Thread") as thread:
            transcriber.preload()
        thread.assert_not_called()


class FakeSynthesizer:
    def __init__(self, error=None):
        self.error = error
        self.texts = []

    def synthesize(self, text):
        self.texts.append(text)
        if self.error:
            raise self.error
        return np.zeros(10, dtype=np.int16), 22050


class FakePlayer:
    def __init__(self):
        self.played = []
        self.stopped = 0

    def play(self, audio, sample_rate):
        self.played.append(sample_rate)

    def stop(self):
        self.stopped += 1


class SynchronousThread:
    """Ersetzt threading.Thread: läuft sofort beim start()."""

    def __init__(self, target, args=(), **kwargs):
        self._target, self._args = target, args

    def start(self):
        self._target(*self._args)


class VoiceOutputTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(speech.threading, "Thread", SynchronousThread)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_satisfies_protocol(self):
        self.assertIsInstance(speech.VoiceOutput(FakeSynthesizer(), FakePlayer()), speech.SpeechOutput)

    def test_speak_synthesizes_cleaned_text_and_plays(self):
        synthesizer, player = FakeSynthesizer(), FakePlayer()
        speech.VoiceOutput(synthesizer, player).speak("**Hallo** Welt")
        self.assertEqual(synthesizer.texts, ["Hallo Welt"])
        self.assertEqual(player.played, [22050])

    def test_empty_text_is_not_spoken(self):
        synthesizer = FakeSynthesizer()
        speech.VoiceOutput(synthesizer, FakePlayer()).speak("  ** ")
        self.assertEqual(synthesizer.texts, [])

    def test_stop_during_synthesis_prevents_playback(self):
        player = FakePlayer()
        output = speech.VoiceOutput(FakeSynthesizer(), player)

        class StoppingSynthesizer(FakeSynthesizer):
            def synthesize(self, text):
                output.stop()   # Escape kommt, während die Stimme noch rechnet
                return super().synthesize(text)

        output._synthesizer = StoppingSynthesizer()
        output.speak("Hallo")
        self.assertEqual(player.played, [])

    def test_synthesis_error_is_only_logged(self):
        player = FakePlayer()
        with self.assertLogs(speech.log, "ERROR"):
            speech.VoiceOutput(FakeSynthesizer(RuntimeError("kaputt")), player).speak("Hallo")
        self.assertEqual(player.played, [])


class FallbackSynthesizerTest(unittest.TestCase):
    def test_uses_next_synthesizer_and_skips_broken_one_afterwards(self):
        broken, working = FakeSynthesizer(RuntimeError("keine Stimme")), FakeSynthesizer()
        fallback = speech.FallbackSynthesizer([broken, working])
        with self.assertLogs(speech.log, "ERROR"):
            fallback.synthesize("eins")
        fallback.synthesize("zwei")
        self.assertEqual(broken.texts, ["eins"])
        self.assertEqual(working.texts, ["eins", "zwei"])

    def test_raises_when_nothing_works(self):
        fallback = speech.FallbackSynthesizer([FakeSynthesizer(RuntimeError("x"))])
        with self.assertLogs(speech.log, "ERROR"), self.assertRaises(RuntimeError):
            fallback.synthesize("Hallo")


class PiperSynthesizerTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.voice_dir = Path(tmp.name) / "piper"
        self.voice = mock.Mock()
        self.voice.config.sample_rate = 22050
        self.voice.synthesize.return_value = [mock.Mock(audio_int16_array=np.ones(3, dtype=np.int16)),
                                              mock.Mock(audio_int16_array=np.ones(2, dtype=np.int16))]
        for name, attribute, value in (("download", "piper.download_voices.download_voice", None),
                                       ("load", "piper.PiperVoice.load", self.voice)):
            patcher = mock.patch(attribute, return_value=value)
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)

    def test_downloads_missing_voice_once_and_joins_sentences(self):
        synthesizer = speech.PiperSynthesizer("de_DE-thorsten-medium", self.voice_dir)
        audio, rate = synthesizer.synthesize("Hallo. Welt.")
        synthesizer.synthesize("Noch mal")
        self.download.assert_called_once_with("de_DE-thorsten-medium", self.voice_dir)
        self.load.assert_called_once_with(self.voice_dir / "de_DE-thorsten-medium.onnx")
        self.assertEqual((len(audio), rate), (5, 22050))

    def test_existing_voice_is_not_downloaded(self):
        self.voice_dir.mkdir()
        (self.voice_dir / "de_DE-thorsten-medium.onnx").write_bytes(b"")
        speech.PiperSynthesizer("de_DE-thorsten-medium", self.voice_dir).synthesize("Hallo")
        self.download.assert_not_called()
        self.load.assert_called_once()


class SapiSynthesizerTest(unittest.TestCase):
    @staticmethod
    def _voice_token(language):
        token = mock.Mock()
        token.GetAttribute.return_value = language
        return token

    def test_prefers_voice_in_configured_language(self):
        german = self._voice_token("407;C07")
        voice, stream = mock.Mock(), mock.Mock()
        voice.GetVoices.return_value = [self._voice_token("409"), german]
        stream.GetData.return_value = np.ones(4, dtype=np.int16).tobytes()
        with mock.patch("pythoncom.CoInitialize"), \
                mock.patch("win32com.client.Dispatch", side_effect=[voice, stream]):
            audio, rate = speech.SapiSynthesizer("de").synthesize("Hallo")
        self.assertIs(voice.Voice, german)
        voice.Speak.assert_called_once_with("Hallo")
        self.assertEqual((len(audio), rate), (4, 22050))

    def test_keeps_default_voice_without_matching_language(self):
        # SimpleNamespace statt Mock: so lässt sich prüfen, dass "Voice" nie gesetzt wird
        voice = types.SimpleNamespace(GetVoices=lambda: [self._voice_token("409")])
        speech.SapiSynthesizer("de")._select_voice(voice)
        self.assertFalse(hasattr(voice, "Voice"))

    def test_unknown_language_does_not_search_voices(self):
        voice = types.SimpleNamespace(GetVoices=mock.Mock())
        speech.SapiSynthesizer("fr")._select_voice(voice)
        voice.GetVoices.assert_not_called()
        self.assertFalse(hasattr(voice, "Voice"))


class AudioPlayerTest(unittest.TestCase):
    def test_play_and_stop(self):
        with mock.patch("sounddevice.play") as play, mock.patch("sounddevice.stop") as stop:
            player = speech.AudioPlayer()
            player.play("audio", 22050)
            player.stop()
        play.assert_called_once_with("audio", 22050)
        stop.assert_called_once()


class SpeakableTest(unittest.TestCase):
    def test_removes_markdown_and_links(self):
        self.assertEqual(speech.speakable("## Termine\n* **9 Uhr** Meeting https://x.de/a"),
                         "Termine\n 9 Uhr Meeting")


class FactoryTest(unittest.TestCase):
    def test_none_without_packages(self):
        with mock.patch.object(speech, "_installed", return_value=False):
            self.assertIsNone(speech.create_speech_input())
            self.assertIsNone(speech.create_speech_output())

    def test_created_with_packages(self):
        with mock.patch.object(speech, "_installed", return_value=True):
            self.assertIsInstance(speech.create_speech_input(), speech.VoiceInput)
            self.assertIsInstance(speech.create_speech_output(), speech.VoiceOutput)

    @staticmethod
    def _output_with(*packages):
        """create_speech_output(), wenn außer sounddevice und numpy nur diese Pakete installiert sind."""
        available = {"sounddevice", "numpy", *packages}
        with mock.patch.object(speech, "_installed", side_effect=lambda *modules: set(modules) <= available):
            return speech.create_speech_output()

    def test_voices_depend_on_installed_packages(self):
        cases = {
            ("piper", "win32com"): [speech.PiperSynthesizer, speech.SapiSynthesizer],   # Piper zuerst
            ("piper",): [speech.PiperSynthesizer],
            ("win32com",): [speech.SapiSynthesizer],
        }
        for packages, expected in cases.items():
            with self.subTest(packages=packages):
                synthesizers = self._output_with(*packages)._synthesizer._synthesizers
                self.assertEqual([type(synthesizer) for synthesizer in synthesizers], expected)

    def test_no_output_without_any_voice(self):
        self.assertIsNone(self._output_with())


class LoadBeforeQtTest(unittest.TestCase):
    def test_without_onnxruntime_nothing_is_imported(self):
        with mock.patch.object(speech, "_installed", return_value=False) as installed, \
                mock.patch.dict("sys.modules", {"onnxruntime": None}):
            speech.load_before_qt()   # würde mit ImportError scheitern, wenn es importieren wollte
        installed.assert_called_once_with("onnxruntime")
