"""Streaming playback with a real decoder and a local recording audio sink."""
import asyncio
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from tests.test_speech import NoAudioReceived


@unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required for streaming integration')
class StreamingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        fixture = Path(cls.directory.name) / 'stream.mp3'
        subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-f', 'lavfi',
                        '-i', 'sine=frequency=440:duration=4', '-ar', '24000',
                        '-ac', '1', '-b:a', '48k', str(fixture)],
                       check=True, capture_output=True, timeout=10)
        cls.mp3 = fixture.read_bytes()

    def setUp(self):
        self.output = tempfile.TemporaryDirectory()
        self.addCleanup(self.output.cleanup)
        self.pcm = Path(self.output.name) / 'audio.pcm'
        self.cancel = threading.Event()
        self.events = queue.Queue()
        self.processes = []
        self.requests = []
        self.player_code = (
            'import os, sys\n'
            'with open(sys.argv[1], "wb", buffering=0) as output:\n'
            '    while data := os.read(0, 512):\n'
            '        output.write(data)\n')
        # Replace only the audio-server boundary; keep real pipe IO and decoding.
        create_process = asyncio.create_subprocess_exec

        async def record_audio(*args, **kwargs):
            if args[0] == 'paplay':
                self.assertIn('discord_tts_sink', args)
                self.assertIn('--raw', args)
                args = (sys.executable, '-c', self.player_code, str(self.pcm))
            process = await create_process(*args, **kwargs)
            self.processes.append(process)
            return process

        self.enterContext(patch('app.asyncio.create_subprocess_exec', side_effect=record_audio))

    def provider(self, stream):
        requests = self.requests

        class Communicate:
            def __init__(self, text, voice, **kwargs):
                requests.append((text, voice, kwargs))

            def stream(self):
                return stream()

        self.enterContext(patch.dict('sys.modules', {
            'edge_tts': types.SimpleNamespace(
                Communicate=Communicate,
                exceptions=types.SimpleNamespace(NoAudioReceived=NoAudioReceived)),
        }))

    def play(self):
        asyncio.run(asyncio.wait_for(app.play_online_speech(
            'Xin chào mọi người!', 'vi-VN-HoaiMyNeural', 155,
            self.cancel, self.events), timeout=8))

    def assert_reaped(self):
        self.assertTrue(self.processes)
        self.assertTrue(all(process.returncode is not None for process in self.processes))

    def test_audio_reaches_player_before_provider_finishes(self):
        async def stream():
            yield {'type': 'SentenceBoundary', 'offset': 0, 'duration': 100,
                   'text': 'Xin chào mọi người!'}
            yield {'type': 'audio', 'data': self.mp3[:4096]}
            # The provider withholds the rest until actual decoded PCM is played.
            for _ in range(200):
                if self.pcm.exists() and self.pcm.stat().st_size > 0:
                    break
                await asyncio.sleep(0.01)
            self.assertTrue(self.pcm.exists() and self.pcm.stat().st_size > 0,
                            'Playback must start before the complete MP3 arrives')
            yield {'type': 'audio', 'data': self.mp3[4096:]}

        self.provider(stream)
        self.play()
        self.assertGreater(len(self.pcm.read_bytes()), 24000 * 2 * 3)
        self.assertNotEqual(set(self.pcm.read_bytes()), {0})
        self.assertEqual(self.requests[0][:2], ('Xin chào mọi người!', 'vi-VN-HoaiMyNeural'))
        self.assert_reaped()

    def test_empty_responses_retry_before_playing(self):
        attempts = 0

        async def stream():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise NoAudioReceived('No audio')
            yield {'type': 'audio', 'data': self.mp3}

        self.provider(stream)
        self.play()
        self.assertEqual(attempts, 3)
        self.assertGreater(self.pcm.stat().st_size, 0)
        self.assert_reaped()

    def test_failure_after_audio_is_never_retried_or_replayed(self):
        async def stream():
            yield {'type': 'audio', 'data': self.mp3[:4096]}
            raise NoAudioReceived('Later segment failed')

        self.provider(stream)
        with self.assertRaisesRegex(RuntimeError, 'interrupted'):
            self.play()
        self.assertEqual(len(self.requests), 1)
        self.assert_reaped()

    def test_stop_interrupts_wait_for_first_audio(self):
        closed = []

        async def stream():
            try:
                self.cancel.set()
                await asyncio.sleep(30)
                yield {'type': 'audio', 'data': self.mp3}
            finally:
                closed.append(True)

        self.provider(stream)
        self.play()
        self.assertEqual(closed, [True])
        self.assertFalse(self.pcm.exists() and self.pcm.stat().st_size > 0)
        self.assert_reaped()

    def test_stop_during_audio_closes_stream_and_players(self):
        closed = []

        async def stream():
            try:
                yield {'type': 'audio', 'data': self.mp3[:4096]}
                self.cancel.set()
                await asyncio.sleep(30)
            finally:
                closed.append(True)

        self.provider(stream)
        self.play()
        self.assertEqual(closed, [True])
        self.assert_reaped()

    def test_already_stopped_request_never_contacts_provider(self):
        async def stream():
            self.fail('Stopped requests must not reach the provider')
            yield

        self.provider(stream)
        self.cancel.set()
        self.play()
        self.assertEqual(self.requests, [])
        self.assertEqual(self.processes, [])

    def test_player_start_failure_reaps_decoder(self):
        create_process = asyncio.create_subprocess_exec

        async def missing_player(*args, **kwargs):
            if args[0] == 'paplay':
                raise FileNotFoundError('paplay is missing')
            return await create_process(*args, **kwargs)

        async def scenario():
            try:
                with self.assertRaisesRegex(FileNotFoundError, 'paplay is missing'):
                    await app.play_online_speech('Hello', 'en-US-JennyNeural', 155,
                                                 self.cancel, self.events)
                self.assert_reaped()
            finally:
                # Clean up even when the regression reintroduces a leaked decoder.
                for process in self.processes:
                    if process.returncode is None:
                        process.kill()
                        await process.wait()

        with patch('app.asyncio.create_subprocess_exec', side_effect=missing_player):
            asyncio.run(scenario())

    def test_audio_server_failure_interrupts_pending_download(self):
        self.player_code = 'import sys; sys.stderr.write("Audio server unavailable"); sys.exit(1)'

        async def stream():
            await asyncio.sleep(30)
            yield {'type': 'audio', 'data': self.mp3}

        self.provider(stream)
        with self.assertRaisesRegex(RuntimeError, 'Audio playback.*Audio server unavailable'):
            self.play()
        self.assert_reaped()

    def test_stop_during_player_start_never_contacts_provider(self):
        async def stream():
            self.fail('Stopped requests must not reach the provider')
            yield

        self.provider(stream)
        create_process = asyncio.create_subprocess_exec

        async def stop_after_spawn(*args, **kwargs):
            process = await create_process(*args, **kwargs)
            if args[0] == 'paplay':
                self.cancel.set()
            return process

        with patch('app.asyncio.create_subprocess_exec', side_effect=stop_after_spawn):
            self.play()
        self.assertEqual(self.requests, [])
        self.assert_reaped()


class StreamingWorkerTests(unittest.TestCase):
    def test_online_worker_uses_streaming_playback(self):
        ui = object.__new__(app.DiscordTTS)
        ui.events = queue.Queue()
        ui.proc = None
        ui.cancel_event = threading.Event()
        started = []

        async def play(*args):
            started.append(args[:3])

        with patch('app.play_online_speech', play, create=True), \
                patch('app.synthesize_speech', side_effect=AssertionError('Buffered playback used')):
            ui.play_worker('Xin chào', 'vi-VN-HoaiMyNeural', 155,
                           app.ONLINE_ENGINE, ui.cancel_event)
        self.assertEqual(started, [('Xin chào', 'vi-VN-HoaiMyNeural', 155)])
        self.assertEqual(ui.events.get_nowait(),
                         ('done', 'Finished speaking. Ready for next message.'))


class ShutdownTests(unittest.TestCase):
    def setUp(self):
        self.ui = object.__new__(app.DiscordTTS)
        self.alive = True
        self.callbacks = []
        self.actions = []
        self.ui.worker_thread = types.SimpleNamespace(is_alive=lambda: self.alive)
        self.ui.root = types.SimpleNamespace(
            after=lambda delay, callback: self.callbacks.append(callback),
            destroy=lambda: self.actions.append('destroy'))
        self.ui.stop = lambda: self.actions.append('stop')
        self.ui.note = lambda message: None
        self.ui.modules = [101, 102]
        self.ui.unload_module = lambda module: self.actions.append(('unload', module))

    def test_close_waits_for_worker_before_unloading_sink_and_destroying_window(self):
        self.ui.close()
        self.assertEqual(self.actions, ['stop'])
        self.assertTrue(self.callbacks)
        self.alive = False
        self.callbacks.pop(0)()
        self.assertEqual(self.actions[-3:], [('unload', 102), ('unload', 101), 'destroy'])

    def test_remove_virtual_waits_for_worker_so_audio_cannot_move_to_default_sink(self):
        self.ui.remove_virtual()
        self.assertEqual(self.actions, ['stop'])
        self.assertTrue(self.callbacks)
        self.alive = False
        self.callbacks.pop(0)()
        self.assertEqual(self.actions[-2:], [('unload', 102), ('unload', 101)])
        self.assertNotIn('destroy', self.actions)


if __name__ == '__main__':
    unittest.main()
