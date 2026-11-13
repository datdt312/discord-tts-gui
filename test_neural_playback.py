"""Decode/play offline neural PCM with a real FFmpeg and a recording sink."""
import array
import math
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import neural_playback
except ImportError:
    neural_playback = None


@unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg required')
class NeuralPlaybackTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(neural_playback, 'Offline neural PCM playback must exist')
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.output = Path(self.directory.name) / 'played.pcm'
        samples = array.array('h', [round(16000 * math.sin(i * 2 * math.pi * 440 / 48000))
                                    for i in range(48000)])
        if sys.byteorder != 'little':
            samples.byteswap()
        self.pcm = samples.tobytes()
        self.cancel = threading.Event()
        self.children = []
        popen = subprocess.Popen

        def recording_player(args, **kwargs):
            if args[0] == 'paplay':
                self.assertIn('discord_tts_sink', args)
                self.assertIn('--rate=48000', args)
                args = [sys.executable, '-c',
                        'import sys\nwith_open=open(sys.argv[1], "wb", buffering=0)\n'
                        'while data := sys.stdin.buffer.read(4096): with_open.write(data)\n'
                        'with_open.close()', str(self.output)]
            process = popen(args, **kwargs)
            self.children.append(process)
            return process

        self.enterContext(patch('neural_playback.subprocess.Popen', side_effect=recording_player))

    def play(self, chunks, speed=155):
        engine = types.SimpleNamespace(stream=lambda *args: iter(chunks))
        neural_playback.play_neural_audio(engine, 'Xin chào', 'test-voice', speed,
                                         'discord_tts_sink', self.cancel,
                                         lambda status: None, lambda player: None)
        self.assertTrue(all(child.poll() is not None for child in self.children))

    def test_normal_speed_preserves_neural_audio(self):
        self.play([self.pcm[:8192], self.pcm[8192:]])
        actual = array.array('h')
        actual.frombytes(self.output.read_bytes())
        self.assertGreater(len(actual), 47000)
        self.assertGreater(max(map(abs, actual)), 10000)

    def test_double_speed_shortens_audio_without_changing_sample_rate(self):
        self.play([self.pcm], speed=310)
        samples = self.output.stat().st_size // 2
        self.assertGreater(samples, 20000)
        self.assertLess(samples, 28000)

    def test_cancelled_request_does_not_start_audio_processes(self):
        self.cancel.set()
        self.play([self.pcm])
        self.assertEqual(self.children, [])

    def test_offline_audio_starts_before_model_finishes(self):
        def chunks():
            yield self.pcm[:8192]
            for _ in range(200):
                if self.output.exists() and self.output.stat().st_size:
                    break
                time.sleep(0.01)
            self.assertTrue(self.output.exists() and self.output.stat().st_size,
                            'PCM must reach the player while the model is still generating')
            yield self.pcm[8192:]

        self.play(chunks())

    def test_model_failure_reaps_audio_processes(self):
        def chunks():
            yield self.pcm[:8192]
            raise RuntimeError('Model inference failed')

        with self.assertRaisesRegex(RuntimeError, 'Model inference failed'):
            self.play(chunks())
        self.assertTrue(all(child.poll() is not None for child in self.children))


if __name__ == '__main__':
    unittest.main()
