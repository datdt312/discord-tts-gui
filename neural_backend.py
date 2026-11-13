"""Optional, per-user CPU neural runtime; importing this needs only stdlib.

Only prepare() installs software or downloads models. stream() uses the
offline-verified cache and an isolated resident worker in the private venv.
"""
import base64
import collections
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import tempfile
import threading


SDK_VERSION = '3.8.4'


class NeuralEngine:
    def __init__(self):
        data_home = Path(os.environ.get('XDG_DATA_HOME', '~/.local/share')).expanduser()
        if not data_home.is_absolute():
            data_home = Path.home() / '.local' / 'share'
        self._root = data_home / 'discord-tts-gui' / 'neural' / 'v3turbo-onnx-fp32'
        self._python = self._root / 'venv' / 'bin' / 'python'
        self._manifest = self._root / 'ready.json'
        self._runtime_path = Path(__file__).with_name('neural_runtime.py')
        self._state_lock = threading.Lock()
        self._operation_lock = threading.Lock()
        self._cancel = threading.Event()
        self._closed = False
        self._process = None
        self._messages = None
        self._errors = collections.deque(maxlen=30)

    def voices(self):
        try:
            data = json.loads(self._manifest.read_text(encoding='utf-8'))
            voices = data['voices']
            if (data.get('sdk_version') != SDK_VERSION or data.get('offline_verified') is not True
                    or not self._python.is_file() or not (self._root / 'cache').is_dir()
                    or not isinstance(voices, dict) or not voices
                    or any(not isinstance(k, str) or not k.strip() or
                           not isinstance(v, str) or not v.strip() for k, v in voices.items())):
                return {}
            return voices
        except (OSError, ValueError, KeyError, TypeError):
            return {}

    def _begin(self, cancel_event):
        with self._state_lock:
            if self._closed:
                raise RuntimeError('Neural engine is closed')
            self._cancel = threading.Event()
        self._check_cancel(cancel_event)

    def _check_cancel(self, cancel_event):
        if self._cancel.is_set() or cancel_event.is_set():
            raise RuntimeError('Neural speech cancelled')

    def _environment(self, offline):
        env = dict(os.environ)
        cache = self._root / 'cache'
        env.update(HF_HOME=str(cache / 'huggingface'),
                   HF_HUB_CACHE=str(cache / 'huggingface' / 'hub'),
                   HUGGINGFACE_HUB_CACHE=str(cache / 'huggingface' / 'hub'),
                   HF_ASSETS_CACHE=str(cache / 'huggingface' / 'assets'),
                   HF_XET_CACHE=str(cache / 'huggingface' / 'xet'),
                   TRANSFORMERS_CACHE=str(cache / 'transformers'),
                   PIP_CACHE_DIR=str(cache / 'pip'),
                   XDG_CACHE_HOME=str(cache), TORCH_HOME=str(cache / 'torch'),
                   HF_HUB_DISABLE_TELEMETRY='1', DO_NOT_TRACK='1',
                   PYTHONNOUSERSITE='1', PYTHONUNBUFFERED='1',
                   PIP_DISABLE_PIP_VERSION_CHECK='1')
        # Packages belong to the private venv, never a caller's import override.
        env.pop('PYTHONPATH', None)
        env.pop('PYTHONHOME', None)
        if offline:
            env.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
        else:
            env.pop('HF_HUB_OFFLINE', None)
            env.pop('TRANSFORMERS_OFFLINE', None)
        return env

    def _spawn(self, command, cancel_event, **kwargs):
        self._check_cancel(cancel_event)
        process = subprocess.Popen(command, start_new_session=True, **kwargs)
        with self._state_lock:
            cancelled = self._closed or self._cancel.is_set() or cancel_event.is_set()
            if not cancelled:
                self._process = process
        if cancelled:
            self._terminate(process)
            raise RuntimeError('Neural speech cancelled')
        return process

    @staticmethod
    def _terminate(process):
        # Signal the whole group: pip/build backends may create child processes.
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=.2)
        except subprocess.TimeoutExpired:
            pass
        # A parent may exit before a child. Kill the group even in that case.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass

    def _discard(self, process):
        if process is None:
            return
        reader_stop = getattr(process, '_neural_reader_stop', None)
        if reader_stop is not None:
            reader_stop.set()
        self._terminate(process)
        with self._state_lock:
            if self._process is process:
                self._process = None
                self._messages = None
        for reader in getattr(process, '_neural_readers', ()):
            if reader is not threading.current_thread() and reader.ident is not None:
                reader.join(timeout=.2)
        for pipe in (process.stdin, process.stdout, process.stderr):
            if pipe is not None:
                pipe.close()

    def stop(self):
        """May be called from Tk while another thread is waiting for the SDK."""
        with self._state_lock:
            self._cancel.set()
            process = self._process
            self._process = None
            self._messages = None
        if process is not None:
            self._discard(process)

    def close(self):
        with self._state_lock:
            self._closed = True
        self.stop()

    def _run_command(self, command, cancel_event, on_status):
        # A file avoids pipe blockage and keeps installer output bounded in RAM.
        with tempfile.TemporaryFile(mode='w+b') as log:
            process = self._spawn(command, cancel_event, stdout=log, stderr=subprocess.STDOUT,
                                  env=self._environment(False), stdin=subprocess.DEVNULL)
            try:
                while process.poll() is None:
                    self._check_cancel(cancel_event)
                    cancel_event.wait(.05)
                self._check_cancel(cancel_event)
                if process.returncode:
                    log.seek(0, os.SEEK_END)
                    log.seek(max(0, log.tell() - 6000))
                    detail = log.read().decode('utf-8', errors='replace').strip()
                    raise RuntimeError('Neural setup failed. Install python3-venv and libsndfile1, '
                                       'check the Internet connection, then retry setup.\n' + detail)
            finally:
                self._discard(process)

    def _start_runtime(self, offline, cancel_event, on_status, on_progress=None):
        on_status('Loading downloaded neural voices…' if offline else 'Downloading and checking neural models…')
        process = self._spawn([str(self._python), str(self._runtime_path),
                               '--offline' if offline else '--download'], cancel_event,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, encoding='utf-8', errors='replace', bufsize=1,
                              env=self._environment(offline))
        # Bound buffered PCM so long text cannot grow RAM while paplay blocks.
        messages = queue.Queue(maxsize=8)
        errors = collections.deque(maxlen=30)
        reader_stop = threading.Event()

        def enqueue(message):
            while not reader_stop.is_set():
                try:
                    messages.put(message, timeout=.05)
                    return
                except queue.Full:
                    pass

        def read_messages():
            try:
                for line in process.stdout:
                    if reader_stop.is_set():
                        break
                    try:
                        enqueue(json.loads(line))
                    except ValueError:
                        enqueue({'event': 'error', 'message': 'Invalid neural worker response'})
            except (OSError, ValueError):
                # Stop can close pipes between spawning and starting readers.
                pass
            finally:
                enqueue(None)

        def read_errors():
            try:
                for line in process.stderr:
                    errors.append(line.rstrip()[-1000:])
            except (OSError, ValueError):
                pass

        readers = (threading.Thread(target=read_messages, daemon=True),
                   threading.Thread(target=read_errors, daemon=True))
        process._neural_reader_stop = reader_stop
        process._neural_readers = readers
        for reader in readers:
            reader.start()
        with self._state_lock:
            if self._process is process:
                self._messages, self._errors = messages, errors
        try:
            while True:
                response = self._receive(process, messages, errors, cancel_event)
                if response.get('event') != 'progress':
                    break
                if offline:
                    raise RuntimeError('Unexpected download progress from offline neural worker')
                progress = self._validate_progress(response)
                if on_progress is not None:
                    on_progress(progress)
            if response.get('event') != 'ready':
                raise RuntimeError('Neural worker did not report readiness')
            voices = response.get('voices')
            if (not isinstance(voices, dict) or not voices or
                    any(not isinstance(k, str) or not k.strip() or
                        not isinstance(v, str) or not v.strip() for k, v in voices.items())):
                raise RuntimeError('Neural worker returned no valid preset voices')
            return process, voices
        except BaseException:
            self._discard(process)
            raise

    @staticmethod
    def _validate_progress(response):
        filename = response.get('filename')
        downloaded, total = response.get('downloaded'), response.get('total')
        if (not isinstance(filename, str) or not filename.strip()
                or type(downloaded) is not int or downloaded < 0
                or (total is not None and (type(total) is not int or total < downloaded))
                or ('cached' in response and type(response['cached']) is not bool)):
            raise RuntimeError('Invalid neural download progress')
        result = dict(filename=filename, downloaded=downloaded, total=total)
        if 'cached' in response:
            result['cached'] = response['cached']
        return result

    def _receive(self, process, messages, errors, cancel_event):
        while True:
            self._check_cancel(cancel_event)
            try:
                message = messages.get(timeout=.05)
            except queue.Empty:
                continue
            if message is None:
                detail = '\n'.join(errors).strip()
                raise RuntimeError('Neural worker stopped unexpectedly. Run neural setup again.' +
                                   ('\n' + detail if detail else ''))
            if not isinstance(message, dict):
                raise RuntimeError('Invalid neural worker response')
            if message.get('event') == 'error':
                raise RuntimeError('Neural TTS: ' + str(message.get('message', 'unknown SDK failure')))
            return message

    def prepare(self, cancel_event, on_status, on_progress=None):
        with self._operation_lock:
            self._begin(cancel_event)
            # Reinstalling must never leave a readiness claim from an old cache.
            with self._state_lock:
                previous = self._process
            self._discard(previous)
            self._check_cancel(cancel_event)
            self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
            self._manifest.unlink(missing_ok=True)
            (self._root / 'cache').mkdir(exist_ok=True)
            process = None
            try:
                on_status('Creating a private neural speech environment…')
                self._run_command([sys.executable, '-m', 'venv', str(self._root / 'venv')], cancel_event, on_status)
                on_status('Installing VieNeu CPU runtime (first setup may take several minutes)…')
                self._run_command([str(self._python), '-m', 'pip', 'install', '--no-input',
                                   'vieneu==' + SDK_VERSION], cancel_event, on_status)
                process, _ = self._start_runtime(False, cancel_event, on_status, on_progress)
                self._discard(process)
                process = None
                on_status('Verifying model loading and speech with network access disabled…')
                process, voices = self._start_runtime(True, cancel_event, on_status)
                self._check_cancel(cancel_event)
                manifest = {'sdk_version': SDK_VERSION, 'offline_verified': True, 'voices': voices,
                            'sample_rate': 48000, 'backend': 'onnx', 'precision': 'fp32'}
                temporary = self._manifest.with_suffix('.tmp')
                temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
                temporary.replace(self._manifest)
                on_status('Offline neural voices are ready.')
                return voices
            except BaseException:
                self._discard(process)
                self._manifest.unlink(missing_ok=True)
                raise

    def stream(self, text, voice, cancel_event, on_status):
        with self._operation_lock:
            self._begin(cancel_event)
            voices = self.voices()
            if not voices:
                raise RuntimeError('Download neural voices with the model setup button before speaking.')
            if voice not in voices.values():
                raise RuntimeError('Selected neural voice is not installed. Run model setup again.')
            if not isinstance(text, str) or not text.strip():
                raise RuntimeError('Speech text must not be empty')
            with self._state_lock:
                process, messages, errors = self._process, self._messages, self._errors
            completed = False
            try:
                if process is None or process.poll() is not None:
                    self._discard(process)
                    process, actual_voices = self._start_runtime(True, cancel_event, on_status)
                    if actual_voices != voices:
                        raise RuntimeError('Installed neural presets changed. Run model setup again.')
                    with self._state_lock:
                        messages, errors = self._messages, self._errors
                self._check_cancel(cancel_event)
                on_status('Generating offline neural speech…')
                process.stdin.write(json.dumps({'command': 'speak', 'text': text, 'voice': voice}, ensure_ascii=False) + '\n')
                process.stdin.flush()
                received = False
                while True:
                    response = self._receive(process, messages, errors, cancel_event)
                    event = response.get('event')
                    if event == 'audio':
                        data = base64.b64decode(response['data'], validate=True)
                        if not data or len(data) % 2:
                            raise RuntimeError('Neural worker returned invalid PCM audio')
                        received = True
                        yield data
                    elif event == 'done':
                        if not received:
                            raise RuntimeError('Neural model produced no audio')
                        completed = True
                        return
                    else:
                        raise RuntimeError('Unexpected neural worker response')
            except (OSError, ValueError, KeyError) as exc:
                raise RuntimeError('Neural speech failed: ' + str(exc)) from exc
            finally:
                if not completed:
                    self._discard(process)
