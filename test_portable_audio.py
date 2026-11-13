"""Portable routing contracts; PortAudio itself needs physical OS devices."""
import threading
import time
import unittest

try:
    from portable_audio import PortableAudio
except ImportError:
    PortableAudio = None


class CallbackStop(Exception):
    pass


class FakePortAudio:
    CallbackStop = CallbackStop
    CallbackAbort = CallbackStop

    def __init__(self):
        self.streams = []

    def query_devices(self, device=None):
        devices = [dict(name='Speakers', max_output_channels=2, hostapi=0),
                   dict(name='CABLE Output', max_output_channels=0, hostapi=0),
                   dict(name='CABLE Input', max_output_channels=2, hostapi=0),
                   dict(name='CABLE Input', max_output_channels=2, hostapi=1),
                   dict(name='BlackHole 2ch', max_output_channels=2, hostapi=0)]
        return devices if device is None else devices[device]

    def query_hostapis(self):
        return [dict(name='WASAPI'), dict(name='MME')]

    def check_output_settings(self, **kwargs):
        if kwargs['channels'] != 2 or kwargs['dtype'] != 'int16':
            raise ValueError('expected stereo signed 16-bit PCM')

    def RawOutputStream(self, **kwargs):
        stream = FakeStream(**kwargs)
        self.streams.append(stream)
        return stream


class FakeStream:
    def __init__(self, callback, finished_callback, **kwargs):
        self.callback = callback
        self.finished_callback = finished_callback
        self.options = kwargs
        self.samples = bytearray()
        self.closed = False
        self.thread = None

    def start(self):
        def run():
            try:
                while True:
                    buffer = bytearray(960 * 4)
                    try:
                        self.callback(buffer, 960, None, None)
                    except CallbackStop:
                        break
                    self.samples.extend(buffer)
                    time.sleep(0.001)
            finally:
                self.finished_callback()
        self.thread = threading.Thread(target=run)
        self.thread.start()

    def abort(self):
        pass

    def close(self):
        if self.thread:
            self.thread.join(timeout=1)
        self.closed = True


class PortableAudioTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(PortableAudio, 'portable audio backend is missing')
        self.backend = FakePortAudio()
        self.audio = PortableAudio(system='Windows', sounddevice_module=self.backend)

    def test_routes_include_host_api_and_never_suggest_capture_or_speakers(self):
        devices = self.audio.devices()
        self.assertEqual(len(devices), 4)
        self.assertEqual(len(set(devices)), 4)
        selected = self.audio.suggested_device(devices)
        self.assertIn('CABLE Input', selected)
        self.assertIn('WASAPI', selected)
        self.assertIsNone(self.audio.suggested_device({'Speakers [WASAPI]': 0}))
        self.assertIsNone(self.audio.suggested_device({'CABLE Output [WASAPI]': 1}))
        mac = PortableAudio(system='Darwin', sounddevice_module=self.backend)
        self.assertIn('BlackHole', mac.suggested_device(devices))

    def test_selected_device_is_required_and_capture_device_rejected(self):
        with self.assertRaises(ValueError):
            self.audio.play_pcm([b'\0' * 4], 48000, threading.Event(), lambda _: None)
        with self.assertRaises(ValueError):
            self.audio.validate_device(1)

    def test_stereo_pcm_reaches_virtual_device_and_preview_and_closes(self):
        pcm = b'\x11\x22\x33\x44' * 2400
        self.audio.play_pcm([pcm[:13], pcm[13:]], 48000, threading.Event(),
                            lambda _: None, device=4, preview_device=0)
        self.assertEqual(len(self.backend.streams), 2)
        for stream in self.backend.streams:
            self.assertEqual(stream.options['channels'], 2)
            self.assertEqual(stream.options['samplerate'], 48000)
            self.assertIn(pcm, bytes(stream.samples))
            self.assertTrue(stream.closed)

    def test_stop_interrupts_queue_backpressure_and_closes_preview(self):
        cancel = threading.Event()
        worker = threading.Thread(target=self.audio.play_pcm,
                                  args=([b'\x01\0\x02\0' * 2000000], 48000,
                                        cancel, lambda _: None),
                                  kwargs=dict(device=2, preview_device=0))
        worker.start()
        deadline = time.monotonic() + 2
        while len(self.backend.streams) < 2 and time.monotonic() < deadline:
            time.sleep(.005)
        started = time.monotonic()
        self.audio.stop()
        self.assertLess(time.monotonic() - started, .1)
        worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertTrue(cancel.is_set())
        self.assertTrue(all(s.closed for s in self.backend.streams))

    def test_preview_failure_closes_primary_stream(self):
        original = self.backend.RawOutputStream
        def fail_preview(**kwargs):
            if kwargs['device'] == 0:
                raise RuntimeError('preview unavailable')
            return original(**kwargs)
        self.backend.RawOutputStream = fail_preview
        with self.assertRaisesRegex(RuntimeError, 'preview unavailable'):
            self.audio.play_pcm([b'\0' * 400], 48000, threading.Event(),
                                lambda _: None, device=2, preview_device=0)
        self.assertTrue(self.backend.streams[0].closed)

    def test_cleanup_closes_every_stream_when_abort_fails(self):
        original = self.backend.RawOutputStream
        def output(**kwargs):
            stream = original(**kwargs)
            if kwargs['device'] == 2:
                def fail_abort():
                    raise RuntimeError('device disappeared')
                stream.abort = fail_abort
            return stream
        self.backend.RawOutputStream = output
        with self.assertRaisesRegex(RuntimeError, 'device disappeared'):
            self.audio.play_pcm([b'\0' * 400], 48000, threading.Event(),
                                lambda _: None, device=2, preview_device=0)
        self.assertTrue(all(stream.closed for stream in self.backend.streams))

    def test_device_disconnect_during_drain_reports_failure(self):
        disconnect = threading.Event()
        original = self.backend.RawOutputStream
        def output(**kwargs):
            stream = original(**kwargs)
            def start():
                def fail():
                    disconnect.wait(1)
                    stream.finished_callback()
                stream.thread = threading.Thread(target=fail)
                stream.thread.start()
            stream.start = start
            return stream
        self.backend.RawOutputStream = output
        def chunks():
            yield b'\0' * 400
            disconnect.set()
        with self.assertRaisesRegex(RuntimeError, 'stopped unexpectedly'):
            self.audio.play_pcm(chunks(), 48000, threading.Event(),
                                lambda _: None, device=2)
        self.assertTrue(all(stream.closed for stream in self.backend.streams))

    def test_precancelled_playback_does_not_open_stream(self):
        cancel = threading.Event()
        cancel.set()
        self.audio.play_pcm([b'\0' * 400], 48000, cancel, lambda _: None, device=2)
        self.assertEqual(self.backend.streams, [])


if __name__ == '__main__':
    unittest.main()
