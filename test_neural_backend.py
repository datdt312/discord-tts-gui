"""Neural setup, streaming and lifetime tests require no model or network."""
import importlib
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from test_neural_runtime import runtime_fixture


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('neural_backend'), 'neural backend must exist')
        self.module = importlib.import_module('neural_backend')
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.enterContext(patch.dict(os.environ, {'XDG_DATA_HOME': self.directory.name,
                                                'LOCALAPPDATA': self.directory.name}))
        self.enterContext(patch('pathlib.Path.home', return_value=Path(self.directory.name)))
        self.engine = self.module.NeuralEngine()
        self.addCleanup(self.engine.close)
        self.fixture = Path(self.directory.name) / 'fixture'
        self.fixture.mkdir()
        self.engine._runtime_path = runtime_fixture(self.fixture)
        self.status = []

    def fake_install(self, command, cancel_event, on_status):
        if '-m' in command and 'venv' in command:
            python = self.engine._python
            if sys.platform == 'win32':
                # A Windows Python executable needs its base-install DLLs and
                # stdlib; a real empty venv also avoids symlink privileges.
                subprocess.run([sys.executable, '-m', 'venv', '--without-pip',
                                str(self.engine._root / 'venv')], check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            else:
                python.parent.mkdir(parents=True, exist_ok=True)
                python.symlink_to(sys.executable)

    def prepare(self):
        with patch.object(self.engine, '_run_command', side_effect=self.fake_install):
            return self.engine.prepare(threading.Event(), self.status.append)

    def test_unprepared_speak_is_actionable_and_creates_no_data(self):
        self.assertEqual(self.engine.voices(), {})
        with self.assertRaisesRegex(RuntimeError, 'setup|Setup|download|Download'):
            list(self.engine.stream('Xin chào', 'nam', threading.Event(), self.status.append))
        self.assertFalse(self.engine._root.exists())

    def test_setup_writes_only_verified_manifest_and_reuses_resident_worker(self):
        voices = self.prepare()
        self.assertEqual(voices, {'Giọng Việt — nữ': 'giọng-thật', 'Giọng nam': 'nam'})
        self.assertTrue(self.engine._root.is_relative_to(Path(self.directory.name)))
        self.assertEqual(self.engine._root.parent.parent.name, 'discord-tts-gui')
        manifest = json.loads(self.engine._manifest.read_text(encoding='utf-8'))
        self.assertTrue(manifest['offline_verified'])
        self.assertEqual(manifest['voices'], voices)
        process = self.engine._process
        for _ in range(2):
            audio = b''.join(self.engine.stream('Xin chào', 'nam', threading.Event(), self.status.append))
            self.assertEqual(audio, b'\x00\x10\x00\xf0')
            self.assertIs(self.engine._process, process)
        self.assertEqual(self.engine.voices(), voices)

    def test_manifest_with_wrong_sdk_version_does_not_offer_stale_voices(self):
        self.prepare()
        manifest = json.loads(self.engine._manifest.read_text())
        manifest['sdk_version'] = '0.0.0'
        self.engine._manifest.write_text(json.dumps(manifest))
        self.assertEqual(self.engine.voices(), {})

    def test_stop_interrupts_blocked_worker_and_allows_new_utterance(self):
        self.prepare()
        process = self.engine._process
        errors = []
        def speak():
            try:
                list(self.engine.stream('hang', 'nam', threading.Event(), self.status.append))
            except Exception as exc:
                errors.append(exc)
        thread = threading.Thread(target=speak)
        thread.start()
        time.sleep(.15)
        self.engine.stop()
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertIsNotNone(process.poll())
        self.assertTrue(errors)
        self.assertTrue(b''.join(self.engine.stream('Again', 'nam', threading.Event(), self.status.append)))

    def test_external_cancel_event_interrupts_blocked_worker(self):
        self.prepare()
        event = threading.Event()
        errors = []
        def speak():
            try:
                list(self.engine.stream('hang', 'nam', event, self.status.append))
            except Exception as exc:
                errors.append(exc)
        thread = threading.Thread(target=speak)
        thread.start()
        time.sleep(.15)
        event.set()
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertTrue(errors)

    def test_stop_during_worker_startup_has_no_reader_thread_errors(self):
        self.prepare()
        self.engine.stop()
        original = self.engine._spawn
        errors = []
        def stop_immediately_after_spawn(*args, **kwargs):
            process = original(*args, **kwargs)
            self.engine.stop()
            return process
        with patch.object(self.engine, '_spawn', side_effect=stop_immediately_after_spawn):
            with patch('threading.excepthook', side_effect=errors.append):
                with self.assertRaisesRegex(RuntimeError, 'cancelled'):
                    list(self.engine.stream('Again', 'nam', threading.Event(), self.status.append))
        self.assertEqual(errors, [])

    def test_close_reaps_idle_resident_worker(self):
        self.prepare()
        process = self.engine._process
        self.engine.close()
        self.assertIsNotNone(process.poll())
        self.assertTrue(process.stdin.closed)
        self.assertTrue(process.stdout.closed)
        self.assertTrue(process.stderr.closed)
        with self.assertRaisesRegex(RuntimeError, 'closed'):
            list(self.engine.stream('Again', 'nam', threading.Event(), self.status.append))

    def test_malformed_manifest_is_treated_as_unprepared(self):
        self.prepare()
        for value in ([], None, 42, {'voices': []}):
            self.engine._manifest.write_text(json.dumps(value))
            self.assertEqual(self.engine.voices(), {})

    def test_offline_verification_failure_never_writes_ready_manifest(self):
        original = self.engine._start_runtime
        def remove_cache_before_verification(offline, cancel_event, on_status, on_progress=None):
            if offline:
                (self.engine._root / 'cache' / 'huggingface' / 'downloaded').unlink()
            return original(offline, cancel_event, on_status, on_progress)
        with patch.object(self.engine, '_start_runtime', side_effect=remove_cache_before_verification):
            with self.assertRaisesRegex(RuntimeError, 'model cache missing'):
                self.prepare()
        self.assertEqual(self.engine.voices(), {})
        self.assertFalse(self.engine._manifest.exists())

    def test_abandoning_a_stream_reaps_its_worker(self):
        self.prepare()
        process = self.engine._process
        stream = self.engine.stream('Again', 'nam', threading.Event(), self.status.append)
        self.assertTrue(next(stream))
        stream.close()
        self.assertIsNotNone(process.poll())

    def test_paused_consumer_applies_backpressure_to_audio_generation(self):
        self.prepare()
        stream = self.engine.stream('flood', 'nam', threading.Event(), self.status.append)
        self.assertTrue(next(stream))
        marker = self.engine._root / 'cache' / 'huggingface' / 'flood-complete'
        deadline = time.monotonic() + 1
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(.02)
        try:
            self.assertFalse(marker.exists(), 'worker ran entire utterance ahead of the audio consumer')
        finally:
            stream.close()

    def test_already_cancelled_setup_does_not_install_or_create_directories(self):
        event = threading.Event()
        event.set()
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            self.engine.prepare(event, self.status.append)
        self.assertFalse(self.engine._root.exists())

    def test_unknown_voice_fails_before_model_receives_request(self):
        self.prepare()
        with self.assertRaisesRegex(RuntimeError, 'voice|Voice'):
            list(self.engine.stream('Xin chào', 'invented', threading.Event(), self.status.append))

    def test_setup_failure_never_marks_partial_install_ready(self):
        with patch.object(self.engine, '_run_command', side_effect=RuntimeError('pip failed')):
            with self.assertRaisesRegex(RuntimeError, 'pip failed'):
                self.engine.prepare(threading.Event(), self.status.append)
        self.assertEqual(self.engine.voices(), {})
        self.assertFalse(self.engine._manifest.exists())

    def test_setup_isolates_user_supplied_huggingface_cache_overrides(self):
        outside = str(Path(self.directory.name) / 'outside-cache')
        with patch.dict(os.environ, {'HF_ASSETS_CACHE': outside, 'HF_XET_CACHE': outside}):
            self.assertTrue(self.prepare())

    def test_prepare_forwards_real_per_file_progress_before_ready(self):
        progress = []
        with patch.dict(os.environ, {'NEURAL_FIXTURE_DOWNLOAD': 'resumed.bin'}):
            with patch.object(self.engine, '_run_command', side_effect=self.fake_install):
                voices = self.engine.prepare(threading.Event(), self.status.append, progress.append)
        self.assertTrue(voices)
        self.assertTrue(progress)
        self.assertEqual(progress[0], {'filename': 'resumed.bin', 'downloaded': 4, 'total': 10})
        self.assertEqual(progress[-1]['downloaded'], 10)
        self.assertNotIn('event', progress[0])

    def test_cancel_during_download_progress_stops_setup_and_reaps_worker(self):
        event = threading.Event()
        progress = []
        def cancel_after_initial(data):
            progress.append(data)
            event.set()
        with patch.dict(os.environ, {'NEURAL_FIXTURE_DOWNLOAD': 'hanging.bin'}):
            with patch.object(self.engine, '_run_command', side_effect=self.fake_install):
                with self.assertRaisesRegex(RuntimeError, 'cancelled'):
                    self.engine.prepare(event, self.status.append, cancel_after_initial)
        self.assertTrue(progress)
        self.assertIsNone(self.engine._process)
        self.assertFalse(self.engine._manifest.exists())

    @unittest.skipUnless(sys.platform.startswith('linux'), 'child liveness uses Linux /proc')
    def test_cancel_reaps_install_process_group_including_children(self):
        child_pid_file = Path(self.directory.name) / 'child.pid'
        source = ('import subprocess,sys,time; '
                  'p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"]); '
                  f'open({str(child_pid_file)!r},"w").write(str(p.pid)); '
                  'time.sleep(60)')
        errors = []
        def install():
            try:
                self.engine._run_command([sys.executable, '-c', source], threading.Event(), self.status.append)
            except Exception as exc:
                errors.append(exc)
        thread = threading.Thread(target=install)
        thread.start()
        deadline = time.monotonic() + 3
        while not child_pid_file.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(child_pid_file.exists())
        self.engine.stop()
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertTrue(errors)
        child = int(child_pid_file.read_text())
        stat = Path(f'/proc/{child}/stat')
        deadline = time.monotonic() + 2
        while stat.exists() and stat.read_text().split()[2] != 'Z' and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(not stat.exists() or stat.read_text().split()[2] == 'Z')

    def test_platform_private_runtime_paths_and_bundled_worker(self):
        bundle = Path(self.directory.name) / 'bundle'
        for system, suffix in (('Windows', 'Scripts/python.exe'), ('Darwin', 'bin/python')):
            with self.subTest(system=system), patch('platform.system', return_value=system):
                with patch.dict(os.environ, {'LOCALAPPDATA': self.directory.name}):
                    with patch.object(sys, '_MEIPASS', str(bundle), create=True):
                        with patch.object(sys, 'frozen', True, create=True):
                            engine = self.module.NeuralEngine()
                self.assertEqual(engine._python.relative_to(engine._root / 'venv'), Path(suffix))
                # Worker scripts must not add the frozen native-library root
                # to the private interpreter's sys.path.
                self.assertEqual(engine._runtime_path, bundle / 'workers/neural_runtime.py')
                engine.close()

    def test_source_worker_stays_beside_backend_module(self):
        with patch.object(sys, 'frozen', False, create=True):
            engine = self.module.NeuralEngine()
        self.assertEqual(engine._runtime_path, Path(self.module.__file__).resolve().with_name('neural_runtime.py'))
        engine.close()

    def test_frozen_setup_bootstraps_managed_python_without_running_app_as_python(self):
        bundle = Path(self.directory.name) / 'bundle'
        (bundle / 'tools').mkdir(parents=True)
        for system, binary in (('Windows', 'uv.exe'), ('Darwin', 'uv')):
            with self.subTest(system=system), patch('platform.system', return_value=system):
                bootstrap = bundle / 'tools' / binary
                bootstrap.touch()
                with patch.object(sys, 'frozen', True, create=True):
                    with patch.object(sys, '_MEIPASS', str(bundle), create=True):
                        engine = self.module.NeuralEngine()
                        commands = []
                        def install(command, event, status):
                            commands.append(command)
                            if len(commands) == 2:
                                raise RuntimeError('stop before downloading models')
                        with patch.object(engine, '_run_command', side_effect=install):
                            with self.assertRaisesRegex(RuntimeError, 'stop before downloading'):
                                engine.prepare(threading.Event(), self.status.append)
                        self.assertEqual(commands[0][0], str(bootstrap))
                        self.assertIn('venv', commands[0])
                        self.assertIn('--seed', commands[0])
                        self.assertEqual(commands[0][commands[0].index('--python') + 1], '3.12')
                        self.assertEqual(commands[0][-1], str(engine._root / 'venv'))
                        self.assertEqual(commands[1][:5], [str(engine._python), '-m', 'pip', '--isolated', 'install'])
                        cache_arg = commands[1].index('--cache-dir')
                        self.assertEqual(commands[1][cache_arg + 1], str(engine._root / 'cache/pip'))
                        env = engine._environment(False)
                        self.assertEqual(env['UV_PYTHON_INSTALL_DIR'], str(engine._root / 'python'))
                        self.assertEqual(env['UV_PYTHON_PREFERENCE'], 'only-managed')
                        self.assertEqual(env['UV_PYTHON_DOWNLOADS'], 'automatic')
                        self.assertFalse(engine._manifest.exists())
                        engine.close()

    def test_frozen_setup_without_bootstrap_gives_actionable_error(self):
        with patch.object(sys, 'frozen', True, create=True):
            with patch.object(sys, '_MEIPASS', self.directory.name, create=True):
                with patch('shutil.which', return_value=None):
                    with patch.object(self.engine, '_run_command') as run:
                        with self.assertRaisesRegex(RuntimeError, 'uv|bootstrap'):
                            self.engine.prepare(threading.Event(), self.status.append)
                        run.assert_not_called()

    def test_private_python_environment_restores_system_library_search_paths(self):
        bundle = Path(self.directory.name) / 'bundle'
        with patch.object(sys, 'frozen', True, create=True):
            with patch.object(sys, '_MEIPASS', str(bundle), create=True):
                overrides = {'LD_LIBRARY_PATH': str(bundle), 'LD_LIBRARY_PATH_ORIG': '/system/lib',
                             'DYLD_LIBRARY_PATH': str(bundle / 'lib') + os.pathsep + '/external/lib',
                             'PATH': str(bundle / 'bin') + os.pathsep + '/usr/bin',
                             'PYTHONPATH': '/outside/modules', 'PYTHONHOME': '/outside/python',
                             'VIRTUAL_ENV': '/outside/venv', 'CONDA_PREFIX': '/outside/conda',
                             'PIP_TARGET': '/outside/target', 'PIP_PREFIX': '/outside/prefix',
                             'PIP_USER': '1', 'PIP_CONFIG_FILE': '/outside/pip.conf'}
                with patch.dict(os.environ, overrides):
                    env = self.engine._environment(False)
                    self.assertEqual(env['LD_LIBRARY_PATH'], '/system/lib')
                    self.assertEqual(env['DYLD_LIBRARY_PATH'], '/external/lib')
                    self.assertEqual(env['PATH'], '/usr/bin')
                    for key in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'CONDA_PREFIX',
                                'PIP_TARGET', 'PIP_PREFIX', 'PIP_USER'):
                        self.assertFalse(key in env, key)
                    self.assertEqual(env['PIP_CONFIG_FILE'], os.devnull)
                    self.assertEqual(os.environ['LD_LIBRARY_PATH'], str(bundle))
        with patch.object(sys, 'frozen', True, create=True):
            with patch.dict(os.environ, {'LD_LIBRARY_PATH': 'bundled'}, clear=True):
                self.assertNotIn('LD_LIBRARY_PATH', self.engine._environment(False))

    def test_windows_launch_hides_console_and_temporarily_restores_dll_search(self):
        bundle = Path(self.directory.name) / 'bundle'
        self.engine._system = 'Windows'
        process = Mock()
        kernel = Mock()
        with patch.object(sys, 'frozen', True, create=True):
            with patch.object(sys, '_MEIPASS', str(bundle), create=True):
                with patch('ctypes.windll', create=True) as windll:
                    windll.kernel32 = kernel
                    with patch.object(subprocess, 'Popen', return_value=process) as popen, \
                            patch.object(self.module, '_WindowsJob', create=True) as job:
                        self.engine._spawn(['python.exe', 'worker.py'], threading.Event())
                        options = popen.call_args.kwargs
                        self.assertNotIn('start_new_session', options)
                        self.assertEqual(options['creationflags'], 0x08000000 | 0x00000200)
                        self.assertEqual(kernel.SetDllDirectoryW.call_args_list[0].args, (None,))
                        self.assertEqual(kernel.SetDllDirectoryW.call_args_list[-1].args, (str(bundle),))
                        job.return_value.assign.assert_called_once_with(process)
                        self.assertIs(process._neural_job, job.return_value)
        self.engine._process = None

    def test_windows_cancel_terminates_and_reaps_the_entire_process_tree(self):
        self.engine._system = 'Windows'
        process = Mock(pid=54321, _neural_job=None)
        with patch.object(subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            with patch.object(os, 'killpg', create=True) as killpg:
                self.engine._terminate(process)
                command = run.call_args.args[0]
                self.assertEqual(command[1:], ['/PID', '54321', '/T', '/F'])
                self.assertTrue(command[0].lower().endswith('taskkill.exe'))
                self.assertEqual(run.call_args.kwargs['creationflags'], 0x08000000)
                killpg.assert_not_called()
                process.wait.assert_called()

    def test_windows_job_assignment_failure_terminates_parent_and_closes_handle(self):
        self.engine._system = 'Windows'
        process = Mock(pid=54321)
        with patch.object(subprocess, 'Popen', return_value=process), \
                patch.object(self.module, '_WindowsJob', create=True) as job:
            job.return_value.assign.side_effect = OSError('cannot assign process to job')
            with self.assertRaisesRegex(OSError, 'assign process'):
                self.engine._spawn(['python.exe'], threading.Event())
            process.kill.assert_called_once()
            process.wait.assert_called_once()
            job.return_value.close.assert_called_once()
            self.assertIsNone(self.engine._process)

    def test_windows_job_termination_reaps_process_without_taskkill(self):
        self.engine._system = 'Windows'
        process = Mock(pid=54321)
        with patch.object(subprocess, 'run') as run:
            self.engine._terminate(process)
            process._neural_job.close.assert_called_once()
            process.wait.assert_called_once()
            run.assert_not_called()

    @unittest.skipUnless(sys.platform == 'win32', 'requires real Windows Job Objects')
    def test_windows_job_reaps_child_after_parent_already_exited(self):
        import time
        child_pid_file = Path(self.directory.name) / 'windows-child.pid'
        source = ('import subprocess,sys,time; time.sleep(.3); '
                  'p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"]); '
                  f'open({str(child_pid_file)!r},"w").write(str(p.pid))')
        parent = self.engine._spawn([sys.executable, '-c', source], threading.Event(),
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
        parent.wait(timeout=5)
        self.assertTrue(child_pid_file.exists())
        child_pid = int(child_pid_file.read_text())
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel.WaitForSingleObject.restype = ctypes.c_uint32
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle.restype = ctypes.c_int
        child = kernel.OpenProcess(0x00100000, False, child_pid)  # SYNCHRONIZE
        self.assertTrue(child, 'child must still exist before closing the parent job')
        try:
            self.assertEqual(kernel.WaitForSingleObject(child, 0), 0x00000102)  # WAIT_TIMEOUT
            self.engine._terminate(parent)
            self.assertEqual(kernel.WaitForSingleObject(child, 5000), 0)  # WAIT_OBJECT_0
        finally:
            kernel.CloseHandle(child)


class WindowsJobTests(unittest.TestCase):
    def setUp(self):
        import neural_backend
        self.module = neural_backend
        self.kernel = Mock()
        self.kernel.CreateJobObjectW.return_value = 0x123456789
        self.kernel.SetInformationJobObject.return_value = 1
        self.kernel.AssignProcessToJobObject.return_value = 1
        self.kernel.CloseHandle.return_value = 1
        self.enterContext(patch('ctypes.WinDLL', return_value=self.kernel, create=True))

    def test_job_sets_kill_on_close_and_handle_signatures(self):
        job = self.module._WindowsJob()
        self.addCleanup(job.close)
        arguments = self.kernel.SetInformationJobObject.call_args.args
        self.assertEqual(arguments[1], 9)  # JobObjectExtendedLimitInformation
        info = arguments[2]._obj
        self.assertEqual(info.BasicLimitInformation.LimitFlags, 0x00002000)
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            self.assertEqual(ctypes.sizeof(info), 144)
        self.assertIs(self.kernel.CreateJobObjectW.restype, ctypes.c_void_p)

    def test_job_closes_once_across_concurrent_stop_and_discard(self):
        job = self.module._WindowsJob()
        process = Mock(_handle=0x998877665)
        job.assign(process)
        self.assertEqual(self.kernel.AssignProcessToJobObject.call_args.args,
                         (0x123456789, 0x998877665))
        threads = [threading.Thread(target=job.close) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        job.close()
        self.kernel.CloseHandle.assert_called_once_with(0x123456789)

    def test_job_configuration_failure_closes_handle(self):
        self.kernel.SetInformationJobObject.return_value = 0
        with self.assertRaisesRegex(OSError, 'JobObject'):
            self.module._WindowsJob()
        self.kernel.CloseHandle.assert_called_once_with(0x123456789)


if __name__ == '__main__':
    unittest.main()
