"""Streaming FFmpeg decoding with portable, explicitly selected audio outputs.

Popen pipes and worker threads work on Windows without inheritable descriptors
or an asyncio subprocess event-loop policy. Neither encoded nor decoded audio
is collected into a complete in-memory file.
"""
import asyncio
import queue
import subprocess
import sys
import tempfile
import threading

from media_tools import ffmpeg_executable, subprocess_options


class _Cancellation:
    """Internal failures stop workers without misreporting user cancellation."""
    def __init__(self, external):
        self.external = external
        self.local = threading.Event()

    def is_set(self):
        return self.external.is_set() or self.local.is_set()

    def set(self):
        self.external.set()

    def wait(self, timeout=None):
        import time
        deadline = None if timeout is None else time.monotonic() + timeout
        while not self.is_set():
            if deadline is not None and time.monotonic() >= deadline:
                return False
            self.local.wait(.02 if deadline is None else max(0, min(.02, deadline - time.monotonic())))
        return True


class _Decoder:
    def __init__(self, arguments, cancel, events, audio, device, preview_device,
                 source=None, queued_input=False):
        self.cancel = _Cancellation(cancel)
        self.events = events
        self.errors = queue.Queue()
        self.input = queue.Queue(maxsize=12) if queued_input else None
        self.done = threading.Event()
        self.player_done = threading.Event()
        self.threads = []
        self.process = None
        self.log = tempfile.TemporaryFile()
        self.received = False
        try:
            self.process = subprocess.Popen(
                [ffmpeg_executable(), '-nostdin', '-hide_banner', '-loglevel', 'error']
                + arguments + ['-vn', '-ac', '2', '-ar', '48000', '-c:a', 'pcm_s16le',
                               '-f', 's16le', '-flush_packets', '1', 'pipe:1'],
                stdin=subprocess.PIPE if source is not None or queued_input else subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=self.log, **subprocess_options())

            def play():
                try:
                    audio.play_pcm(self._pcm(), 48000, self.cancel,
                                   self.status, device=device, preview_device=preview_device)
                except BaseException as error:
                    self._fail(error)
                finally:
                    self.player_done.set()

            def watch():
                while not self.done.wait(.02):
                    if self.cancel.is_set():
                        self._terminate()
                        return

            self._thread('player', play)
            self._thread('cancel', watch)
            if source is not None or queued_input:
                self._thread('feeder', lambda: self._feed(source))
        except BaseException:
            self.close()
            raise

    def status(self, message):
        if self.events is not None:
            self.events.put(('status', message))

    def _thread(self, name, function):
        thread = threading.Thread(target=function, name='portable-' + name)
        self.threads.append(thread)
        thread.start()

    def _fail(self, error):
        self.errors.put(error)
        self.cancel.local.set()
        self._terminate()

    def _terminate(self):
        if self.process is not None and self.process.poll() is None:
            try:
                self.process.terminate()
            except OSError:
                pass

    def _pcm(self):
        while not self.cancel.is_set():
            data = self.process.stdout.read(3840)
            if not data:
                return
            self.received = True
            yield data

    def _feed(self, source):
        iterator = None
        try:
            if source is not None:
                iterator = iter(source(self.cancel, self.status))
            while not self.cancel.is_set():
                if iterator is None:
                    try:
                        data = self.input.get(timeout=.02)
                    except queue.Empty:
                        continue
                    if data is None:
                        break
                else:
                    try:
                        data = next(iterator)
                    except StopIteration:
                        break
                if data:
                    self.process.stdin.write(data)
                    self.process.stdin.flush()
        except BaseException as error:
            if not self.cancel.is_set():
                self._fail(error)
        finally:
            if iterator is not None and hasattr(iterator, 'close'):
                iterator.close()
            try:
                self.process.stdin.close()
            except OSError:
                pass

    async def send(self, data):
        # Backpressure never blocks the asyncio provider or cancellation checks.
        # Split provider chunks too, so the input bound is bytes as well as items.
        parts = [None] if data is None else (data[index:index + 16384]
                                            for index in range(0, len(data), 16384))
        for part in parts:
            while not self.cancel.is_set():
                self.check_error()
                try:
                    self.input.put_nowait(part)
                    break
                except queue.Full:
                    await asyncio.sleep(.01)
            if self.cancel.is_set():
                self.check_error()
                return

    def check_error(self):
        try:
            error = self.errors.get_nowait()
        except queue.Empty:
            return
        raise error

    def wait(self):
        while not self.player_done.wait(.02):
            self.check_error()
        self.check_result()

    def check_result(self):
        self.check_error()
        if self.cancel.is_set():
            return
        code = self.process.wait()
        if code:
            self.log.seek(0)
            detail = self.log.read().decode(errors='replace').strip()
            raise RuntimeError('FFmpeg decoding failed: ' + (detail or str(code)))
        if not self.received:
            raise RuntimeError('FFmpeg returned no audio.')

    def close(self):
        self.cancel.local.set()
        self.done.set()
        self._terminate()
        if self.process is not None:
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        # Terminating the process releases pipe reads/writes before joining.
        for thread in self.threads:
            thread.join()
        if self.process is not None:
            for pipe in (self.process.stdin, self.process.stdout):
                if pipe is not None:
                    pipe.close()
        self.log.close()


async def play_online(text, voice, speed, cancel, events, receive_audio,
                      audio, device, preview_device=None):
    if cancel.is_set():
        return
    decoder = _Decoder(['-f', 'mp3', '-probesize', '32', '-analyzeduration', '0',
                        '-i', 'pipe:0'], cancel, events, audio, device,
                       preview_device, queued_input=True)
    provider = None
    try:
        provider = asyncio.create_task(receive_audio(text, voice, speed, decoder.send, events))
        while not provider.done() and not cancel.is_set():
            decoder.check_error()
            await asyncio.sleep(.01)
        if cancel.is_set():
            return
        await provider
        await decoder.send(None)
        while not decoder.player_done.is_set() and not cancel.is_set():
            decoder.check_error()
            await asyncio.sleep(.01)
        decoder.check_result()
    finally:
        if provider is not None and not provider.done():
            provider.cancel()
        if provider is not None:
            await asyncio.gather(provider, return_exceptions=True)
        # Poll a worker Event: this also works in restricted environments where
        # thread-safe asyncio wakeups cannot use a socketpair.
        propagating_error = sys.exc_info()[0] is not None
        complete = threading.Event()
        cleanup_errors = []
        def cleanup():
            try:
                decoder.close()
            except BaseException as error:
                cleanup_errors.append(error)
            finally:
                complete.set()
        cleaner = threading.Thread(target=cleanup, name='portable-cleanup')
        cleaner.start()
        while not complete.is_set():
            await asyncio.sleep(.01)
        cleaner.join()
        if cleanup_errors and not propagating_error:
            raise cleanup_errors[0]


def play_neural(engine, text, voice, speed, cancel, events, audio, device,
                preview_device=None):
    if cancel.is_set():
        return
    factor = speed / 155
    if not .5 <= factor <= 3:
        raise ValueError('Offline speech speed is out of range')
    filters = []
    while factor > 2:
        filters.append('atempo=2')
        factor /= 2
    if factor != 1:
        filters.append(f'atempo={factor:.8f}')
    arguments = ['-f', 's16le', '-ar', '48000', '-ac', '1',
                 '-probesize', '32', '-analyzeduration', '0', '-i', 'pipe:0']
    if filters:
        arguments += ['-af', ','.join(filters)]
    def source(combined_cancel, on_status):
        return engine.stream(text, voice, combined_cancel, on_status)
    decoder = _Decoder(arguments, cancel, events, audio, device, preview_device, source=source)
    try:
        decoder.wait()
    finally:
        decoder.close()


def play_file(path, cancel, events, audio, device, preview_device=None):
    if cancel.is_set():
        return
    decoder = _Decoder(['-i', str(path)], cancel, events, audio, device, preview_device)
    try:
        decoder.wait()
    finally:
        decoder.close()
