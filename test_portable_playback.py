"""Exercise real FFmpeg with deterministic PCM and a device boundary double."""
import asyncio
import importlib
import queue
import shutil
import struct
import subprocess
import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import patch
from media_tools import ffmpeg_executable

try:
    FFMPEG = ffmpeg_executable()
except RuntimeError:
    FFMPEG = None

try:
    import portable_playback
except ImportError:
    portable_playback = None


class RecordingAudio:
    def __init__(self):
        self.data = bytearray()
        self.started = threading.Event()
        self.formats = []

    def play_pcm(self, chunks, sample_rate, cancel_event, on_status,
                 preview_device=None, device=None):
        self.formats.append((sample_rate, device, preview_device))
        for data in chunks:
            if cancel_event.is_set():
                return
            self.data.extend(data)
            self.started.set()


@unittest.skipUnless(FFMPEG, 'real FFmpeg is required')
class PortablePlaybackTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(portable_playback, 'portable streaming module is missing')
        self.audio = RecordingAudio()
        self.cancel = threading.Event()
        self.events = queue.Queue()
        self.processes = []
        original_popen = subprocess.Popen
        def capture(*args, **kwargs):
            process = original_popen(*args, **kwargs)
            self.processes.append(process)
            return process
        self.popen_patch = patch.object(portable_playback.subprocess, 'Popen', capture)
        self.popen_patch.start()
        self.addCleanup(self.popen_patch.stop)

    def tearDown(self):
        if portable_playback is not None:
            self.assertTrue(all(p.poll() is not None for p in self.processes), 'decoder was not reaped')
            self.assertFalse([t.name for t in threading.enumerate()
                              if t.name.startswith('portable-')], 'playback worker leaked')

    def mp3(self):
        return subprocess.check_output([FFMPEG, '-hide_banner', '-loglevel', 'error',
                                        '-f', 'lavfi', '-i', 'sine=frequency=400:duration=5',
                                        '-f', 'mp3', 'pipe:1'])

    def test_online_starts_before_provider_finishes(self):
        mp3 = self.mp3()
        async def receive(text, voice, speed, write_audio, events):
            await write_audio(mp3[:30000])
            deadline = time.monotonic() + 3
            while not self.audio.started.is_set():
                self.assertLess(time.monotonic(), deadline, 'decoder buffered the whole provider')
                await asyncio.sleep(.01)
            await write_audio(mp3[30000:])
        asyncio.run(portable_playback.play_online('text', 'voice', 155, self.cancel,
                                                 self.events, receive, self.audio, 2, 0))
        self.assertGreater(len(self.audio.data), 48000 * 4 * 4)
        self.assertEqual(self.audio.formats, [(48000, 2, 0)])

    def test_stop_cancels_slow_provider_before_first_audio(self):
        closed = threading.Event()
        async def receive(*args):
            try:
                await asyncio.sleep(60)
            finally:
                closed.set()
        async def run():
            task = asyncio.create_task(portable_playback.play_online(
                'text', 'voice', 155, self.cancel, self.events, receive, self.audio, 2))
            await asyncio.sleep(.05)
            self.cancel.set()
            await asyncio.wait_for(task, 2)
        asyncio.run(run())
        self.assertTrue(closed.is_set())
        self.assertEqual(self.audio.data, b'')

    def test_async_task_cancellation_reaps_decoder_and_workers(self):
        async def receive(*args):
            await asyncio.sleep(60)
        async def run():
            task = asyncio.create_task(portable_playback.play_online(
                'text', 'voice', 155, self.cancel, self.events, receive, self.audio, 2))
            await asyncio.sleep(.05)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, 2)
        asyncio.run(run())

    def test_provider_error_is_preserved_and_decoder_reaped(self):
        async def receive(*args):
            raise RuntimeError('provider unavailable')
        with self.assertRaisesRegex(RuntimeError, 'provider unavailable'):
            asyncio.run(portable_playback.play_online('text', 'voice', 155,
                        self.cancel, self.events, receive, self.audio, 2))
        self.assertFalse(self.cancel.is_set(), 'provider error must not become user cancellation')

    def test_invalid_compressed_audio_reports_ffmpeg_failure(self):
        async def receive(text, voice, speed, write_audio, events):
            await write_audio(b'bad MP3 data')
        with self.assertRaisesRegex(RuntimeError, 'FFmpeg'):
            asyncio.run(portable_playback.play_online('text', 'voice', 155,
                        self.cancel, self.events, receive, self.audio, 2))

    def test_file_decodes_mono_to_identical_stereo_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'audio with spaces.wav'
            with wave.open(str(path), 'wb') as output:
                output.setparams((1, 2, 48000, 4800, 'NONE', 'not compressed'))
                output.writeframes(struct.pack('<h', 1234) * 4800)
            portable_playback.play_file(path, self.cancel, self.events, self.audio, 4)
        self.assertEqual(len(self.audio.data), 4800 * 4)
        # FFmpeg's mono-to-stereo mapping applies -3 dB gain to each channel.
        left, right = struct.unpack('<hh', self.audio.data[:4])
        self.assertEqual(left, right)
        self.assertGreater(left, 800)
        self.assertLess(left, 1000)

    def test_neural_speed_and_stereo_conversion(self):
        class Engine:
            def stream(self, text, voice, cancel_event, on_status):
                for _ in range(50):
                    yield struct.pack('<h', 1200) * 960
        portable_playback.play_neural(Engine(), 'text', 'voice', 310, self.cancel,
                                     self.events, self.audio, 4)
        frames = len(self.audio.data) // 4
        self.assertGreater(frames, 20000)
        self.assertLess(frames, 26000)
        self.assertEqual(self.audio.data[:2], self.audio.data[2:4])

    def test_output_failure_cancels_slow_provider_and_preserves_error(self):
        class BrokenAudio:
            def play_pcm(self, *args, **kwargs):
                raise RuntimeError('selected output disconnected')
        async def receive(*args):
            await asyncio.sleep(60)
        with self.assertRaisesRegex(RuntimeError, 'selected output disconnected'):
            asyncio.run(portable_playback.play_online('text', 'voice', 155,
                        self.cancel, self.events, receive, BrokenAudio(), 2))
        self.assertFalse(self.cancel.is_set())

    def test_cleanup_failure_is_reported_after_successful_playback(self):
        mp3 = self.mp3()
        original = portable_playback._Decoder.close
        def failing_close(decoder):
            original(decoder)
            raise RuntimeError('audio cleanup failed')
        async def receive(text, voice, speed, write_audio, events):
            await write_audio(mp3)
        with patch.object(portable_playback._Decoder, 'close', failing_close):
            with self.assertRaisesRegex(RuntimeError, 'audio cleanup failed'):
                asyncio.run(portable_playback.play_online('text', 'voice', 155,
                            self.cancel, self.events, receive, self.audio, 2))

    def test_cleanup_failure_does_not_hide_provider_error(self):
        original = portable_playback._Decoder.close
        def failing_close(decoder):
            original(decoder)
            raise RuntimeError('audio cleanup failed')
        async def receive(*args):
            raise RuntimeError('provider unavailable')
        with patch.object(portable_playback._Decoder, 'close', failing_close):
            with self.assertRaisesRegex(RuntimeError, 'provider unavailable'):
                asyncio.run(portable_playback.play_online('text', 'voice', 155,
                            self.cancel, self.events, receive, self.audio, 2))

    def test_precancelled_request_does_not_start_decoder_or_provider(self):
        self.cancel.set()
        async def receive(*args):
            self.fail('provider called after cancellation')
        asyncio.run(portable_playback.play_online('text', 'voice', 155, self.cancel,
                                                 self.events, receive, self.audio, 2))
        self.assertEqual(self.processes, [])


if __name__ == '__main__':
    unittest.main()
