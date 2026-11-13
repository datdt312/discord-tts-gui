"""Speech synthesis and voice selection regressions, without an audio server."""
import array
import asyncio
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import types
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import app


class NoAudioReceived(Exception):
    """Stand-in for the provider's empty-response exception."""


@unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required for codec integration tests')
class SpeechTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.fixtures.cleanup)
        cls.mp3 = Path(cls.fixtures.name) / 'fixture.mp3'
        subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-f', 'lavfi',
                        '-i', 'sine=frequency=440:duration=0.15', str(cls.mp3)],
                       check=True, capture_output=True, timeout=10)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.output = Path(self.directory.name) / 'speech.wav'

    def provider(self, failure=None, failures=None):
        """Replace only the remote service; exercise the real FFmpeg decoder."""
        requests = []
        mp3 = self.mp3
        outcomes = iter(failures) if failures is not None else None

        class Communicate:
            def __init__(self, text, voice, **kwargs):
                requests.append((text, voice, kwargs))
                self.used = False

            async def stream(self):
                if self.used:
                    raise RuntimeError('stream can only be called once')
                self.used = True
                error = next(outcomes, None) if outcomes is not None else failure
                if error:
                    raise error
                yield {'type': 'audio', 'data': mp3.read_bytes()}

        self.enterContext(patch.dict('sys.modules', {
            'edge_tts': types.SimpleNamespace(
                Communicate=Communicate,
                exceptions=types.SimpleNamespace(NoAudioReceived=NoAudioReceived)),
        }))
        return requests

    def assert_audio(self):
        with wave.open(str(self.output), 'rb') as audio:
            self.assertEqual(audio.getsampwidth(), 2)
            self.assertEqual(audio.getcomptype(), 'NONE')
            samples = array.array('h', audio.readframes(audio.getnframes()))
            self.assertGreater(max(map(abs, samples), default=0), 100)

    def test_online_vietnamese_preserves_text_and_decodes_mp3_for_paplay(self):
        requests = self.provider()
        text = 'Xin chào! Tiếng Việt: ă â đ ê ô ơ ư. <Một> & hai.'
        app.synthesize_speech(text, 'vi-VN-HoaiMyNeural', 155,
                              str(self.output), 'Microsoft Edge (online)')
        self.assertEqual(requests[0][:2], (text, 'vi-VN-HoaiMyNeural'))
        self.assertEqual(requests[0][2]['rate'], '+0%')
        self.assert_audio()

    def test_speed_310_is_twice_normal_online_speed(self):
        requests = self.provider()
        app.synthesize_speech('Xin chào', 'vi-VN-NamMinhNeural', 310,
                              str(self.output), 'Microsoft Edge (online)')
        self.assertEqual(requests[0][1], 'vi-VN-NamMinhNeural')
        self.assertEqual(requests[0][2]['rate'], '+100%')

    def test_network_failure_is_reported_without_offline_fallback(self):
        requests = self.provider(OSError('connection refused'))
        with self.assertRaisesRegex(RuntimeError, 'Online TTS.*connection refused'):
            app.synthesize_speech('Xin chào', 'vi-VN-HoaiMyNeural', 155,
                                  str(self.output), 'Microsoft Edge (online)')
        self.assertFalse(self.output.exists())
        self.assertEqual(len(requests), 1)

    def test_empty_service_responses_recover_with_fresh_requests(self):
        requests = self.provider(failures=[NoAudioReceived('No audio'),
                                           NoAudioReceived('No audio'), None])
        app.synthesize_speech('Xin chào', 'vi-VN-HoaiMyNeural', 155,
                              str(self.output), app.ONLINE_ENGINE)
        self.assertEqual(len(requests), 3)
        self.assertTrue(all(request[:2] == ('Xin chào', 'vi-VN-HoaiMyNeural')
                            for request in requests))
        self.assert_audio()

    def test_persistent_empty_response_is_bounded_and_explains_voice_failure(self):
        requests = self.provider(NoAudioReceived('No audio was received'))
        with self.assertRaises(RuntimeError) as raised:
            app.synthesize_speech('Xin chào', 'vi-VN-HoaiMyNeural', 155,
                                  str(self.output), app.ONLINE_ENGINE)
        self.assertEqual(len(requests), 3)
        message = str(raised.exception)
        self.assertIn('vi-VN-HoaiMyNeural', message)
        self.assertIn('3 attempts', message)
        self.assertIn('not a usage limit', message)
        self.assertIn('another voice', message)
        self.assertNotIn('Check your Internet connection', message)
        self.assertFalse(self.output.exists())

    def test_online_can_speak_more_than_three_successful_messages(self):
        requests = self.provider()
        for _ in range(4):
            app.synthesize_speech('Xin chào', 'vi-VN-HoaiMyNeural', 155,
                                  str(self.output), app.ONLINE_ENGINE)
        self.assertEqual(len(requests), 4)
        self.assert_audio()

    def test_timeout_is_not_retried(self):
        requests = self.provider(TimeoutError())
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            app.synthesize_speech('Xin chào', 'vi-VN-HoaiMyNeural', 155,
                                  str(self.output), app.ONLINE_ENGINE)
        self.assertEqual(len(requests), 1)
        self.assertFalse(self.output.exists())

    def test_total_deadline_includes_retry_backoff(self):
        requests = self.provider(NoAudioReceived('No audio'))
        wait_for = asyncio.wait_for

        async def short_deadline(awaitable, timeout):
            return await wait_for(awaitable, timeout=0.01)

        with patch('app.asyncio.wait_for', side_effect=short_deadline):
            with self.assertRaisesRegex(RuntimeError, 'timed out'):
                app.synthesize_speech('Xin chào', 'vi-VN-HoaiMyNeural', 155,
                                      str(self.output), app.ONLINE_ENGINE)
        self.assertEqual(len(requests), 1)
        self.assertFalse(self.output.exists())

    def test_decode_failure_does_not_claim_network_failure_or_retry(self):
        requests = self.provider()
        error = subprocess.CalledProcessError(1, 'ffmpeg', stderr='Invalid audio data')
        with patch('app.command', side_effect=error):
            with self.assertRaisesRegex(RuntimeError, 'FFmpeg.*Invalid audio data') as raised:
                app.synthesize_speech('Xin chào', 'vi-VN-HoaiMyNeural', 155,
                                      str(self.output), app.ONLINE_ENGINE)
        self.assertEqual(len(requests), 1)
        self.assertNotIn('Internet connection', str(raised.exception))

    def test_missing_online_package_gives_installation_instructions(self):
        with patch.dict('sys.modules', {'edge_tts': None}):
            with self.assertRaisesRegex(RuntimeError, 'install.sh'):
                app.synthesize_speech('Xin chào', 'vi-VN-HoaiMyNeural', 155,
                                      str(self.output), 'Microsoft Edge (online)')

    @unittest.skipUnless(shutil.which('espeak-ng'), 'eSpeak NG required')
    def test_offline_vietnamese_still_produces_audio_without_online_package(self):
        with patch.dict('sys.modules', {'edge_tts': None}):
            app.synthesize_speech('Xin chào mọi người!', 'vi', 155,
                                  str(self.output), 'eSpeak NG (offline)')
        self.assert_audio()


class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.tcl = app.tk.Tcl()
        self.ui = object.__new__(app.DiscordTTS)
        self.ui.engine_var = app.tk.StringVar(self.tcl, value='Microsoft Edge (online)')
        self.ui.voice_var = app.tk.StringVar(self.tcl)
        self.ui.status = app.tk.StringVar(self.tcl)
        self.ui.engine_hint = app.tk.StringVar(self.tcl)
        self.ui.voice_combo = {}
        self.ui.voice_names = {'old selection': 'vi'}

    def test_online_defaults_to_vietnamese_and_offers_both_genders(self):
        self.ui.load_voices()
        self.assertEqual(self.ui.voice_names[self.ui.voice_var.get()], 'vi-VN-HoaiMyNeural')
        self.assertIn('vi-VN-NamMinhNeural', self.ui.voice_names.values())
        self.assertNotIn('old selection', self.ui.voice_names)

    @unittest.skipUnless(shutil.which('espeak-ng'), 'eSpeak NG required')
    def test_switching_to_offline_replaces_online_voices(self):
        self.ui.load_voices()
        self.ui.engine_var.set('eSpeak NG (offline)')
        self.ui.load_voices()
        self.assertEqual(self.ui.voice_names[self.ui.voice_var.get()], 'vi')
        self.assertNotIn('vi-VN-HoaiMyNeural', self.ui.voice_names.values())


class WorkerTests(unittest.TestCase):
    def test_failed_synthesis_never_reaches_playback(self):
        ui = object.__new__(app.DiscordTTS)
        ui.events = queue.Queue()
        ui.proc = None
        with patch('app.synthesize_speech', side_effect=RuntimeError('Online TTS failed')), \
                patch('app.subprocess.Popen') as player:
            ui.play_worker('Xin chào', 'vi', 155, app.OFFLINE_ENGINE)
        self.assertEqual(ui.events.get_nowait(), ('error', 'Online TTS failed'))
        player.assert_not_called()

    def test_stopping_during_synthesis_prevents_later_discord_playback(self):
        ui = object.__new__(app.DiscordTTS)
        ui.events = queue.Queue()
        ui.proc = None
        ui.playing = True
        ui.cancel_event = threading.Event()
        ui.status = types.SimpleNamespace(set=lambda message: None)
        # Stop is pressed while the network synthesis request is still pending.
        with patch('app.synthesize_speech', side_effect=lambda *args: ui.stop()), \
                patch('app.subprocess.Popen') as player:
            ui.play_worker('Xin chào', 'vi', 155,
                           app.OFFLINE_ENGINE, ui.cancel_event)
        self.assertEqual(ui.events.get_nowait(), ('done', 'Stopped.'))
        player.assert_not_called()


if __name__ == '__main__':
    unittest.main()
