"""Latest-text playback replaces an active request without overlapping workers."""
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import types
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import app


class ReplacementTests(unittest.TestCase):
    def setUp(self):
        self.tcl = app.tk.Tcl()
        self.ui = object.__new__(app.DiscordTTS)
        self.ui.engine_var = app.tk.StringVar(self.tcl, value=app.ONLINE_ENGINE)
        self.ui.voice_var = app.tk.StringVar(self.tcl, value='First')
        self.ui.speed_var = app.tk.IntVar(self.tcl, value=155)
        self.ui.engine_hint = app.tk.StringVar(self.tcl)
        self.ui.status = app.tk.StringVar(self.tcl)
        self.ui.voice_names = {'First': 'voice-1', 'Second': 'voice-2'}
        self.ui.voice_combo = {}
        self.ui.sink_active = True
        self.ui.playing = False
        self.ui.preparing = False
        self.ui.closing = False
        self.ui.removing = False
        self.ui.worker_thread = None
        self.ui.cancel_event = None
        self.ui.proc = None
        self.ui.events = queue.Queue()
        self.ui.neural = types.SimpleNamespace(
            voices=lambda: {'Preset A': 'preset-a'}, stop=lambda: None)
        self.callbacks = []
        self.ui.root = types.SimpleNamespace(after=lambda ms, callback: self.callbacks.append(callback))
        self.content = 'old'
        self.ui.text = types.SimpleNamespace(get=lambda *args: self.content)
        self.started = []
        self.old_entered = threading.Event()
        self.new_entered = threading.Event()
        self.release_old = threading.Event()
        self.active = 0
        self.maximum_active = 0
        self.lock = threading.Lock()

        def worker(text, voice, speed, engine, cancel_event=None, events=None):
            events = events if events is not None else self.ui.events
            with self.lock:
                self.started.append((text, voice, speed, engine))
                self.active += 1
                self.maximum_active = max(self.maximum_active, self.active)
            try:
                if text == 'old':
                    self.old_entered.set()
                    cancel_event.wait(3)
                    self.release_old.wait(3)
                else:
                    self.new_entered.set()
                    cancel_event.wait(3)
                events.put(('done', 'old completion' if text == 'old' else 'finished'))
            finally:
                with self.lock:
                    self.active -= 1

        self.ui.play_worker = worker
        self.addCleanup(self.cleanup_worker)

    def cleanup_worker(self):
        self.release_old.set()
        if self.ui.cancel_event is not None:
            self.ui.cancel_event.set()
        thread = self.ui.worker_thread
        if thread is not None:
            thread.join(3)

    def start_old(self):
        self.ui.speak()
        self.assertTrue(self.old_entered.wait(1), 'Initial speech must start')
        return self.ui.worker_thread

    def finish_old(self, thread):
        self.release_old.set()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.ui.start_pending_speech()

    def test_repeated_speak_stops_old_and_only_starts_latest_snapshot(self):
        old = self.start_old()
        self.content = 'intermediate'
        self.ui.speak()
        self.content = 'latest text'
        self.ui.voice_var.set('Second')
        self.ui.speed_var.set(200)
        self.ui.speak()
        self.assertTrue(self.ui.cancel_event.is_set())
        self.assertEqual(len(self.started), 1, 'Old cleanup must finish before starting a replacement')
        self.finish_old(old)
        self.assertTrue(self.new_entered.wait(1))
        self.assertEqual(self.started[-1], ('latest text', 'voice-2', 200, app.ONLINE_ENGINE))
        self.assertEqual(self.maximum_active, 1)

    def test_old_done_does_not_clear_new_playback_state(self):
        old = self.start_old()
        self.content = 'new'
        self.ui.speak()
        self.finish_old(old)
        self.assertTrue(self.new_entered.wait(1))
        self.ui.poll()
        self.assertTrue(self.ui.playing)
        self.assertNotEqual(self.ui.status.get(), 'old completion')

    def test_stop_discards_pending_restart(self):
        old = self.start_old()
        self.content = 'must not play'
        self.ui.speak()
        self.ui.stop()
        self.finish_old(old)
        self.assertEqual(len(self.started), 1)
        self.assertFalse(self.ui.playing)

    def test_engine_change_restarts_with_current_text_and_new_voice(self):
        old = self.start_old()
        self.content = 'new model text'
        self.ui.engine_var.set(app.NEURAL_ENGINE)
        self.ui.on_engine_changed()
        self.finish_old(old)
        self.assertTrue(self.new_entered.wait(1))
        self.assertEqual(self.started[-1], ('new model text', 'preset-a', 155, app.NEURAL_ENGINE))
        self.assertEqual(self.maximum_active, 1)

    def test_voice_change_restarts_active_speech(self):
        old = self.start_old()
        self.content = 'new voice text'
        self.ui.voice_var.set('Second')
        self.ui.on_voice_changed()
        self.finish_old(old)
        self.assertTrue(self.new_entered.wait(1))
        self.assertEqual(self.started[-1][:2], ('new voice text', 'voice-2'))

    def test_rapid_clicks_schedule_only_one_restart_callback(self):
        self.start_old()
        for index in range(20):
            self.content = str(index)
            self.ui.speak()
        self.assertEqual(len(self.callbacks), 1)

    def test_stale_status_and_error_cannot_affect_replacement(self):
        old = self.start_old()
        old_generation = self.ui._speech_generation
        self.content = 'new'
        self.ui.speak()
        self.finish_old(old)
        self.assertTrue(self.new_entered.wait(1))
        self.ui.events.put(('status', 'stale status', old_generation))
        self.ui.events.put(('error', 'stale error', old_generation))
        with patch('app.messagebox.showerror') as show_error:
            self.ui.poll()
        show_error.assert_not_called()
        self.assertTrue(self.ui.playing)
        self.assertNotIn('stale', self.ui.status.get())

    def test_unprepared_new_engine_stops_old_and_requests_setup(self):
        old = self.start_old()
        self.ui.neural.voices = lambda: {}
        self.ui.engine_var.set(app.NEURAL_ENGINE)
        with patch('app.messagebox.showwarning') as warning:
            self.ui.on_engine_changed()
        self.assertTrue(self.ui.cancel_event.is_set())
        self.finish_old(old)
        self.assertEqual(len(self.started), 1)
        warning.assert_called_once()

    def test_remove_discards_pending_speech(self):
        old = self.start_old()
        self.content = 'must not play'
        self.ui.speak()
        self.ui.remove_virtual()
        self.finish_old(old)
        self.assertIsNone(self.ui.pending_speech)
        self.assertEqual(len(self.started), 1)

    def test_close_discards_pending_speech(self):
        old = self.start_old()
        self.content = 'must not play'
        self.ui.speak()
        self.ui.close()
        self.finish_old(old)
        self.assertIsNone(self.ui.pending_speech)
        self.assertEqual(len(self.started), 1)

    def test_idle_engine_change_does_not_speak(self):
        self.ui.engine_var.set(app.NEURAL_ENGINE)
        self.ui.on_engine_changed()
        self.assertEqual(self.started, [])
        self.assertEqual(self.ui.voice_names, {'Preset A': 'preset-a'})

    def test_empty_new_text_stops_old_instead_of_continuing_it(self):
        old = self.start_old()
        self.content = ''
        self.ui.speak()
        self.assertTrue(self.ui.cancel_event.is_set())
        self.release_old.set()
        old.join(2)
        self.assertEqual(len(self.started), 1)


class CancelableOfflineTests(unittest.TestCase):
    def test_stop_interrupts_offline_generation_before_playback(self):
        with tempfile.TemporaryDirectory() as directory:
            output = str(Path(directory) / 'speech.wav')
            event = threading.Event()
            started = threading.Event()
            children = []
            errors = []
            popen = subprocess.Popen

            def sleeping_synth(args, **kwargs):
                process = popen([sys.executable, '-c', 'import time; time.sleep(30)'], **kwargs)
                children.append(process)
                started.set()
                return process

            def generate():
                try:
                    app.synthesize_speech('Xin chào', 'vi', 155, output, app.OFFLINE_ENGINE, event)
                except Exception as error:
                    errors.append(error)

            with patch('app.subprocess.Popen', side_effect=sleeping_synth):
                thread = threading.Thread(target=generate, daemon=True)
                thread.start()
                try:
                    self.assertTrue(started.wait(1))
                    event.set()
                    thread.join(2)
                    self.assertFalse(thread.is_alive())
                    self.assertIsNotNone(children[0].poll())
                    self.assertEqual(errors, [])
                finally:
                    event.set()
                    for child in children:
                        if child.poll() is None:
                            child.kill()
                        child.wait()
                    thread.join(2)

    @unittest.skipUnless(shutil.which('espeak-ng'), 'eSpeak required')
    def test_cancelable_offline_path_still_generates_valid_wav(self):
        with tempfile.TemporaryDirectory() as directory:
            output = str(Path(directory) / 'speech.wav')
            app.synthesize_speech('Xin chào mọi người!', 'vi', 155, output,
                                  app.OFFLINE_ENGINE, threading.Event())
            with wave.open(output) as audio:
                self.assertGreater(audio.getnframes(), 1000)


if __name__ == '__main__':
    unittest.main()
