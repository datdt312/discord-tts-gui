"""Neural setup, streaming and lifetime tests require no model or network."""
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from test_neural_runtime import runtime_fixture


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('neural_backend'), 'neural backend must exist')
        self.module = importlib.import_module('neural_backend')
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.enterContext(patch.dict(os.environ, {'XDG_DATA_HOME': self.directory.name}))
        self.engine = self.module.NeuralEngine()
        self.addCleanup(self.engine.close)
        self.fixture = Path(self.directory.name) / 'fixture'
        self.fixture.mkdir()
        self.engine._runtime_path = runtime_fixture(self.fixture)
        self.status = []

    def fake_install(self, command, cancel_event, on_status):
        if '-m' in command and 'venv' in command:
            python = self.engine._python
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
        self.assertTrue(str(self.engine._root).startswith(self.directory.name + '/discord-tts-gui/'))
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


if __name__ == '__main__':
    unittest.main()
