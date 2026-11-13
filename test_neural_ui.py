"""Offline neural engine selection/setup and worker integration, without Tk windows."""
import queue
import threading
import types
import unittest
from unittest.mock import patch

import app


class NeuralUITests(unittest.TestCase):
    def setUp(self):
        self.tcl = app.tk.Tcl()
        self.ui = object.__new__(app.DiscordTTS)
        self.ui.engine_var = app.tk.StringVar(self.tcl, value='VieNeu-TTS v3 Turbo (offline AI)')
        self.ui.voice_var = app.tk.StringVar(self.tcl)
        self.ui.status = app.tk.StringVar(self.tcl)
        self.ui.engine_hint = app.tk.StringVar(self.tcl)
        self.ui.voice_combo = {}
        self.ui.voice_names = {'old selection': 'vi'}
        self.ui.events = queue.Queue()
        self.ui.proc = None
        self.ui.playing = False
        self.ui.preparing = False
        self.ui.closing = False
        self.ui.removing = False
        self.ui.root = types.SimpleNamespace(after=lambda *args: None)
        self.presets = {'Giọng A — Bắc': 'voice-a', 'Giọng B — Nam': 'voice-b'}
        self.ui.neural = types.SimpleNamespace(voices=lambda: self.presets)
        self.ui.download_label_var = app.tk.StringVar(self.tcl)
        self.progress_state = {'value': 0, 'mode': 'determinate', 'running': False}
        self.ui.download_bar = types.SimpleNamespace(
            configure=lambda **values: self.progress_state.update(values),
            start=lambda interval: self.progress_state.update(running=True),
            stop=lambda: self.progress_state.update(running=False))
        self.progress_state['visible'] = False
        self.ui.download_frame = types.SimpleNamespace(
            grid=lambda: self.progress_state.update(visible=True),
            grid_remove=lambda: self.progress_state.update(visible=False))

    def test_neural_engine_offers_actual_installed_presets(self):
        self.ui.load_voices()
        self.assertEqual(self.ui.voice_names, self.presets)
        self.assertEqual(self.ui.voice_var.get(), 'Giọng A — Bắc')
        self.assertNotIn('vi', self.ui.voice_names.values())
        self.assertIn('offline', self.ui.engine_hint.get().lower())

    def test_unprepared_neural_engine_has_download_hint_and_no_espeak_fallback(self):
        self.ui.neural.voices = lambda: {}
        self.ui.load_voices()
        self.assertEqual(self.ui.voice_names, {})
        self.assertEqual(self.ui.voice_var.get(), '')
        self.assertIn('download', self.ui.engine_hint.get().lower())

    def test_successful_setup_refreshes_voice_list_on_tk_thread(self):
        self.ui.playing = True
        self.ui.preparing = True
        self.ui.events.put(('neural_ready', self.presets))
        self.ui.poll()
        self.assertFalse(self.ui.playing)
        self.assertFalse(self.ui.preparing)
        self.assertEqual(self.ui.voice_names, self.presets)

    def test_setup_runs_backend_and_reports_ready(self):
        self.ui.neural.prepare = lambda cancel, status, on_progress=None: self.presets
        self.ui.setup_neural_worker(threading.Event())
        self.assertEqual(self.ui.events.get_nowait(), ('neural_ready', self.presets))

    def test_cancelled_setup_does_not_show_an_error(self):
        cancel = threading.Event()

        def prepare(event, status, on_progress=None):
            event.set()
            raise RuntimeError('Download interrupted')

        self.ui.neural.prepare = prepare
        self.ui.setup_neural_worker(cancel)
        self.assertEqual(self.ui.events.get_nowait(), ('done', 'Stopped.'))

    def test_neural_worker_does_not_use_online_or_espeak_synthesis(self):
        seen = []
        self.ui.cancel_event = threading.Event()

        def playback(engine, text, voice, speed, sink, cancel, status, player):
            seen.append((engine, text, voice, speed, sink))

        with patch('app.play_neural_audio', playback, create=True), \
                patch('app.synthesize_speech', side_effect=AssertionError('Wrong engine')):
            self.ui.play_worker('Xin chào', 'voice-b', 155,
                                'VieNeu-TTS v3 Turbo (offline AI)', self.ui.cancel_event)
        self.assertEqual(seen, [(self.ui.neural, 'Xin chào', 'voice-b', 155, 'discord_tts_sink')])
        self.assertEqual(self.ui.events.get_nowait(),
                         ('done', 'Finished speaking. Ready for next message.'))

    def test_stop_cancels_model_worker_even_before_first_audio(self):
        stopped = []
        self.ui.neural.stop = lambda: stopped.append(True)
        self.ui.cancel_event = threading.Event()
        self.ui.playing = True
        self.ui.stop()
        self.assertTrue(self.ui.cancel_event.is_set())
        self.assertEqual(stopped, [True])

    def test_download_events_show_real_file_percentage_and_megabytes(self):
        self.ui.preparing = True
        self.ui.events.put(('download_progress', {
            'filename': 'weights.data', 'downloaded': 50_000_000, 'total': 100_000_000}))
        self.ui.poll()
        self.assertEqual(self.progress_state['value'], 50)
        self.assertEqual(self.progress_state['mode'], 'determinate')
        label = self.ui.download_label_var.get()
        self.assertIn('50.0%', label)
        self.assertIn('50.0 MB', label)
        self.assertIn('100.0 MB', label)
        self.assertIn('weights.data', label)
        self.assertTrue(self.progress_state['visible'])

    def test_unknown_download_size_does_not_make_up_a_percentage(self):
        self.ui.preparing = True
        self.ui.events.put(('download_progress', {
            'filename': 'unknown.data', 'downloaded': 15_000_000, 'total': None}))
        self.ui.poll()
        self.assertEqual(self.progress_state['mode'], 'indeterminate')
        self.assertTrue(self.progress_state['running'])
        label = self.ui.download_label_var.get()
        self.assertIn('15.0 MB', label)
        self.assertNotIn('%', label)

    def test_model_loading_after_file_download_uses_a_separate_busy_stage(self):
        self.ui.preparing = True
        self.ui.events.put(('download_progress', {
            'filename': 'weights.data', 'downloaded': 100, 'total': 100}))
        self.ui.events.put(('status', 'Verifying model offline...'))
        self.ui.poll()
        self.assertEqual(self.progress_state['mode'], 'indeterminate')
        self.assertTrue(self.progress_state['running'])
        self.assertEqual(self.ui.download_label_var.get(), 'Verifying model offline...')

    def test_setup_completion_stops_progress_and_marks_ready(self):
        self.ui.preparing = True
        self.ui.events.put(('neural_ready', self.presets))
        self.ui.poll()
        self.assertEqual(self.progress_state['value'], 100)
        self.assertFalse(self.progress_state['running'])
        self.assertFalse(self.progress_state['visible'])
        self.assertEqual(self.ui.download_label_var.get(), '')

    def test_cancelled_setup_never_reports_complete(self):
        self.ui.preparing = True
        self.ui.events.put(('done', 'Stopped.'))
        self.ui.poll()
        self.assertNotEqual(self.progress_state['value'], 100)
        self.assertFalse(self.progress_state['running'])
        self.assertFalse(self.progress_state['visible'])

    def test_setup_error_hides_progress_and_keeps_full_error_available(self):
        self.ui.preparing = True
        self.ui.show_download_progress({'downloaded': 10, 'total': 100})
        self.ui.events.put(('error', 'Model setup failed: missing weights'))
        with patch('app.messagebox.showerror') as show_error:
            self.ui.poll()
        self.assertFalse(self.progress_state['visible'])
        self.assertFalse(self.ui.preparing)
        show_error.assert_called_once_with(app.APP, 'Model setup failed: missing weights')

    def test_setup_worker_forwards_byte_progress_to_gui_queue(self):
        payload = {'filename': 'weights.data', 'downloaded': 4, 'total': 10}

        def prepare(cancel, status, on_progress=None):
            on_progress(payload)
            return self.presets

        self.ui.neural.prepare = prepare
        self.ui.setup_neural_worker(threading.Event())
        self.assertEqual(self.ui.events.get_nowait(), ('download_progress', payload))
        self.assertEqual(self.ui.events.get_nowait(), ('neural_ready', self.presets))


if __name__ == '__main__':
    unittest.main()
