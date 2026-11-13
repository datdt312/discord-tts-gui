"""Optional, per-user CPU neural runtime; importing this needs only stdlib.

Only prepare() installs software or downloads models. stream() uses the
offline-verified cache and an isolated resident worker in the private venv.
"""
import base64
import collections
import ctypes
import json
import os
from pathlib import Path
import platform
import queue
import shutil
import signal
import subprocess
import sys
import tempfile
import threading

from runtime_support import user_data_dir, venv_python


SDK_VERSION = '3.8.4'
_WINDOWS_DLL_LOCK = threading.Lock()


class _JobBasicLimits(ctypes.Structure):
    # Fixed-width Windows fields also keep mocked API tests accurate on Unix,
    # where ctypes.c_ulong has a different size from a Windows DWORD.
    _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64),
                ('PerJobUserTimeLimit', ctypes.c_int64),
                ('LimitFlags', ctypes.c_uint32),
                ('MinimumWorkingSetSize', ctypes.c_size_t),
                ('MaximumWorkingSetSize', ctypes.c_size_t),
                ('ActiveProcessLimit', ctypes.c_uint32),
                ('Affinity', ctypes.c_size_t),
                ('PriorityClass', ctypes.c_uint32),
                ('SchedulingClass', ctypes.c_uint32)]


class _JobIoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in
                ('ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
                 'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]


class _JobExtendedLimits(ctypes.Structure):
    _fields_ = [('BasicLimitInformation', _JobBasicLimits),
                ('IoInfo', _JobIoCounters),
                ('ProcessMemoryLimit', ctypes.c_size_t),
                ('JobMemoryLimit', ctypes.c_size_t),
                ('PeakProcessMemoryUsed', ctypes.c_size_t),
                ('PeakJobMemoryUsed', ctypes.c_size_t)]


class _WindowsJob:
    """Own one process tree, including children surviving the original parent."""
    def __init__(self):
        self._lock = threading.Lock()
        self._handle = None
        self._kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self._kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        self._kernel.CreateJobObjectW.restype = ctypes.c_void_p
        self._kernel.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                                       ctypes.c_void_p, ctypes.c_uint32]
        self._kernel.SetInformationJobObject.restype = ctypes.c_int
        self._kernel.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self._kernel.AssignProcessToJobObject.restype = ctypes.c_int
        self._kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        self._kernel.CloseHandle.restype = ctypes.c_int
        self._handle = self._kernel.CreateJobObjectW(None, None)
        if not self._handle:
            raise self._error('CreateJobObjectW')
        information = _JobExtendedLimits()
        information.BasicLimitInformation.LimitFlags = 0x00002000  # KILL_ON_JOB_CLOSE
        if not self._kernel.SetInformationJobObject(self._handle, 9, ctypes.byref(information),
                                                   ctypes.sizeof(information)):
            error = self._error('SetInformationJobObject')
            self.close()
            raise error

    @staticmethod
    def _error(operation):
        code = getattr(ctypes, 'get_last_error', lambda: 0)()
        return OSError(f'Windows {operation} failed (error {code}).')

    def assign(self, process):
        with self._lock:
            if not self._kernel.AssignProcessToJobObject(self._handle, int(process._handle)):
                raise self._error('AssignProcessToJobObject')

    def close(self):
        with self._lock:
            if self._handle is not None:
                handle, self._handle = self._handle, None
                if not self._kernel.CloseHandle(handle):
                    raise self._error('CloseHandle(JobObject)')


class NeuralEngine:
    def __init__(self):
        self._system = platform.system()
        self._root = user_data_dir(system=self._system) / 'neural' / 'v3turbo-onnx-fp32'
        self._python = venv_python(self._root / 'venv', system=self._system)
        self._manifest = self._root / 'ready.json'
        # Executing a script adds its directory to sys.path. Keep private SDK
        # workers apart from PyInstaller's incompatible native extensions.
        worker_dir = (self._resource_dir() / 'workers' if getattr(sys, 'frozen', False)
                      else Path(__file__).resolve().parent)
        self._runtime_path = worker_dir / 'neural_runtime.py'
        self._state_lock = threading.Lock()
        self._operation_lock = threading.Lock()
        self._cancel = threading.Event()
        self._closed = False
        self._process = None
        self._messages = None
        self._errors = collections.deque(maxlen=30)

    @staticmethod
    def _resource_dir():
        return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))

    def _bootstrap_command(self):
        if not getattr(sys, 'frozen', False):
            return [sys.executable, '-m', 'venv', str(self._root / 'venv')]
        binary = 'uv.exe' if self._system == 'Windows' else 'uv'
        resource = self._resource_dir()
        candidates = (resource / 'tools' / binary, resource / binary)
        bootstrap = next((str(path) for path in candidates if path.is_file()), None)
        bootstrap = bootstrap or shutil.which(binary)
        if not bootstrap:
            raise RuntimeError('The private Python bootstrap (uv) is missing. '
                               'Reinstall the application, then retry Download neural voices.')
        # Frozen sys.executable is the GUI, not an interpreter. uv downloads a
        # private managed Python; no system Python installation is required.
        return [bootstrap, '--no-config', 'venv', '--managed-python',
                '--python', '3.12', '--seed', str(self._root / 'venv')]

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
                   PIP_DISABLE_PIP_VERSION_CHECK='1',
                   UV_CACHE_DIR=str(cache / 'uv'),
                   UV_PYTHON_INSTALL_DIR=str(self._root / 'python'),
                   UV_PYTHON_PREFERENCE='only-managed', UV_PYTHON_DOWNLOADS='automatic',
                   PIP_CONFIG_FILE=os.devnull)
        # Packages belong to the private venv, never a caller's import override.
        for variable in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'CONDA_PREFIX',
                         'PIP_TARGET', 'PIP_PREFIX', 'PIP_USER'):
            env.pop(variable, None)
        if getattr(sys, 'frozen', False):
            # External Python must load its own libraries, not PyInstaller's.
            original = env.get('LD_LIBRARY_PATH_ORIG')
            if original is None:
                env.pop('LD_LIBRARY_PATH', None)
            else:
                env['LD_LIBRARY_PATH'] = original
            bundle = self._resource_dir().resolve()
            for variable in ('PATH', 'DYLD_LIBRARY_PATH'):
                if variable not in env:
                    continue
                paths = []
                for entry in env[variable].split(os.pathsep):
                    if entry and not Path(entry).resolve().is_relative_to(bundle):
                        paths.append(entry)
                env[variable] = os.pathsep.join(paths)
        if offline:
            env.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
        else:
            env.pop('HF_HUB_OFFLINE', None)
            env.pop('TRANSFORMERS_OFFLINE', None)
        return env

    def _spawn(self, command, cancel_event, **kwargs):
        self._check_cancel(cancel_event)
        if self._system == 'Windows':
            # CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW: a GUI should never
            # flash a console during Python setup or resident-worker startup.
            kwargs['creationflags'] = 0x00000200 | 0x08000000
            job = _WindowsJob()
            process = None
            try:
                if getattr(sys, 'frozen', False):
                    with _WINDOWS_DLL_LOCK:
                        ctypes.windll.kernel32.SetDllDirectoryW(None)
                        try:
                            process = subprocess.Popen(command, **kwargs)
                        finally:
                            ctypes.windll.kernel32.SetDllDirectoryW(str(self._resource_dir()))
                else:
                    process = subprocess.Popen(command, **kwargs)
                # Popen closes the primary thread handle, so assigning the job
                # happens immediately after launch rather than suspended. No
                # process is exposed to cancellation until assignment succeeds.
                job.assign(process)
                process._neural_job = job
            except BaseException:
                try:
                    if process is not None:
                        process.kill()
                        process.wait(timeout=2)
                finally:
                    job.close()
                raise
        else:
            process = subprocess.Popen(command, start_new_session=True, **kwargs)
        with self._state_lock:
            cancelled = self._closed or self._cancel.is_set() or cancel_event.is_set()
            if not cancelled:
                self._process = process
        if cancelled:
            self._terminate(process)
            raise RuntimeError('Neural speech cancelled')
        return process

    def _terminate(self, process):
        if self._system == 'Windows':
            job = getattr(process, '_neural_job', None)
            if job is not None:
                # Closing the job terminates descendants even when the parent
                # has exited. Its lock makes concurrent stop/discard idempotent.
                try:
                    job.close()
                finally:
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=1)
                return
            # taskkill /T includes pip/build-backend and worker descendants.
            taskkill = str(Path(os.environ.get('SystemRoot', r'C:\Windows')) /
                           'System32' / 'taskkill.exe')
            try:
                subprocess.run([taskkill, '/PID', str(process.pid), '/T', '/F'],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, creationflags=0x08000000,
                               timeout=10, check=False)
            except (OSError, subprocess.TimeoutExpired):
                # Still reap the direct child if taskkill is unavailable.
                process.kill()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)
            return
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
                    hint = ('For source installs, check Python venv and libsndfile support. '
                            if self._system == 'Linux' and not getattr(sys, 'frozen', False) else '')
                    raise RuntimeError('Neural setup failed. ' + hint +
                                       'Check the Internet connection and available disk space, '
                                       'then retry Download neural voices.\n' + detail)
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
                self._run_command(self._bootstrap_command(), cancel_event, on_status)
                on_status('Installing VieNeu CPU runtime (first setup may take several minutes)…')
                self._run_command([str(self._python), '-m', 'pip', '--isolated', 'install', '--no-input',
                                   '--cache-dir', str(self._root / 'cache' / 'pip'),
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
