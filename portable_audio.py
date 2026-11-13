"""Explicit stereo output routing through PortAudio on Windows and macOS.

Importing this module never loads PortAudio. The UI may inspect the platform and
show setup instructions even when sounddevice or the virtual driver is absent.
"""
import platform
import queue
import sys
import threading


class PortableAudio:
    def __init__(self, system=None, sounddevice_module=None):
        self.system = system or platform.system()
        self._sounddevice = sounddevice_module
        self._state_lock = threading.Lock()
        self._play_lock = threading.Lock()
        self._cancel = None
        self._closed = False

    def _backend(self):
        if self._sounddevice is None:
            try:
                import sounddevice
            except ImportError as error:
                raise RuntimeError('Audio output requires sounddevice. Reinstall the application dependencies.') from error
            self._sounddevice = sounddevice
        return self._sounddevice

    def devices(self):
        """Return output labels containing both host API and stable device index."""
        backend = self._backend()
        hosts = backend.query_hostapis()
        return {f"{item['name']} [{hosts[item['hostapi']]['name']}; #{index}]": index
                for index, item in enumerate(backend.query_devices())
                if item['max_output_channels'] > 0}

    def suggested_device(self, devices):
        """Suggest an installed virtual playback endpoint, never system speakers."""
        needle = 'cable input' if self.system == 'Windows' else 'blackhole' if self.system == 'Darwin' else None
        if needle is None:
            return None
        matches = [label for label in devices if needle in label.casefold()]
        if self.system == 'Windows':
            matches.sort(key=lambda label: 'wasapi' not in label.casefold())
        return matches[0] if matches else None

    def validate_device(self, device):
        if device is None or isinstance(device, bool) or not isinstance(device, int) or device < 0:
            raise ValueError('Select an audio output device before playing.')
        backend = self._backend()
        try:
            info = backend.query_devices(device)
            if info['max_output_channels'] < 2:
                raise ValueError('Selected device must support stereo audio output.')
            backend.check_output_settings(device=device, channels=2, dtype='int16', samplerate=48000)
        except (IndexError, KeyError) as error:
            raise ValueError('Selected audio output is no longer available. Refresh devices.') from error
        return device

    def stop(self):
        """Signal cancellation without calling a potentially blocking PortAudio API."""
        with self._state_lock:
            if self._cancel is not None:
                self._cancel.set()

    def close(self):
        with self._state_lock:
            self._closed = True
            if self._cancel is not None:
                self._cancel.set()

    def play_pcm(self, chunks, sample_rate, cancel_event, on_status,
                 preview_device=None, device=None):
        """Consume interleaved stereo s16le chunks with bounded callback buffers.

        The caller owns producing chunks and must unblock its iterator when the
        cancellation event is set. Decoder helpers in portable_playback do this
        by terminating FFmpeg. PortAudio callbacks never wait for the producer.
        """
        if cancel_event.is_set():
            return
        self.stop()
        with self._play_lock:
            with self._state_lock:
                if self._closed:
                    raise RuntimeError('Audio output is closed.')
                self._cancel = cancel_event
            streams = []
            buffers = []
            finished = threading.Event()
            try:
                self.validate_device(device)
                if sample_rate != 48000:
                    raise ValueError('Portable audio requires 48000 Hz stereo PCM.')
                devices = [device]
                if preview_device is not None and preview_device != device:
                    self.validate_device(preview_device)
                    devices.append(preview_device)
                backend = self._backend()
                for output in devices:
                    buffered = queue.Queue(maxsize=12)
                    done = threading.Event()
                    intentional_stop = threading.Event()
                    buffers.append((buffered, done, intentional_stop))

                    def make_callback(pending, intentional):
                        remainder = bytearray()

                        def callback(outdata, frames, time_info, status):
                            if cancel_event.is_set():
                                raise backend.CallbackAbort
                            target = memoryview(outdata).cast('B')
                            target[:] = b'\0' * len(target)
                            written = 0
                            while written < len(target):
                                if not remainder:
                                    try:
                                        remainder.extend(pending.get_nowait())
                                    except queue.Empty:
                                        if finished.is_set() and written == 0:
                                            intentional.set()
                                            raise backend.CallbackStop
                                        break
                                take = min(len(remainder), len(target) - written)
                                target[written:written + take] = remainder[:take]
                                del remainder[:take]
                                written += take
                        return callback

                    stream = backend.RawOutputStream(
                        device=output, samplerate=sample_rate, channels=2,
                        dtype='int16', blocksize=960, latency='low',
                        callback=make_callback(buffered, intentional_stop), finished_callback=done.set)
                    streams.append(stream)
                    stream.start()
                on_status('Playing audio to the selected output...')
                carry = bytearray()
                for chunk in chunks:
                    if cancel_event.is_set():
                        return
                    carry.extend(chunk)
                    while len(carry) >= 4:
                        take = min((len(carry) // 4) * 4, 3840)
                        block = bytes(carry[:take])
                        del carry[:take]
                        for pending, done, intentional in buffers:
                            while not cancel_event.is_set():
                                if done.is_set():
                                    raise RuntimeError('Audio output stopped unexpectedly.')
                                try:
                                    pending.put(block, timeout=.02)
                                    break
                                except queue.Full:
                                    pass
                        if cancel_event.is_set():
                            return
                if carry and not cancel_event.is_set():
                    raise ValueError('Incomplete stereo PCM frame.')
                finished.set()
                for pending, done, intentional in buffers:
                    while not cancel_event.is_set() and not done.wait(.02):
                        pass
                    if not cancel_event.is_set() and not intentional.is_set():
                        raise RuntimeError('Audio output stopped unexpectedly.')
            finally:
                finished.set()
                # Stop callbacks before close even when opening the preview fails.
                propagating_error = sys.exc_info()[0] is not None
                cleanup_error = None
                for stream in streams:
                    for operation in (stream.abort, stream.close):
                        try:
                            operation()
                        except Exception as error:
                            cleanup_error = cleanup_error or error
                with self._state_lock:
                    if self._cancel is cancel_event:
                        self._cancel = None
                if cleanup_error is not None and not propagating_error:
                    raise cleanup_error
