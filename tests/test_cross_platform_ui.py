"""Portable routes never depend on Linux audio utilities or select speakers implicitly."""
import os
import queue
import threading
import types
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import app


class PortableControllerTests(unittest.TestCase):
    def setUp(self):
        from qt_ui import QtRoot
        self.root = QtRoot()
        self.enterContext(patch('app.messagebox.showerror'))
        self.enterContext(patch('app.messagebox.showwarning'))
        self.neural = types.SimpleNamespace(voices=lambda: {'Giọng A': 'a'},
                                            stop=lambda: None, close=lambda: None)
        self.validated = []
        self.stops = []
        self.audio = types.SimpleNamespace(
            devices=lambda: {'Speakers [WASAPI]': 0, 'CABLE Input [WASAPI]': 5},
            suggested_device=lambda devices: 'CABLE Input [WASAPI]',
            validate_device=lambda device: self.validated.append(device),
            stop=lambda: self.stops.append(True), close=lambda: None)
        with patch('app.current_platform', return_value='win32', create=True), \
                patch('neural_backend.NeuralEngine', return_value=self.neural), \
                patch('portable_audio.PortableAudio', return_value=self.audio), \
                patch('app.pulse_list', side_effect=AssertionError('Linux-only audio used')):
            self.ui = app.DiscordTTS(self.root)
        self.enterContext(patch('app.messagebox.showerror'))
        self.enterContext(patch('app.messagebox.showwarning'))
        self.root.window.show()
        self.root.application.processEvents()
        self.addCleanup(self.root.destroy)

    def test_windows_lists_virtual_output_and_connects_without_pactl(self):
        self.assertEqual(self.ui.target_var.get(), 'CABLE Input [WASAPI]')
        with patch('app.command', side_effect=AssertionError('Linux utility used')):
            self.ui.create_virtual()
        self.assertTrue(self.ui.sink_active)
        self.assertEqual(self.ui.active_output, 5)
        self.assertEqual(self.validated, [5])
        self.assertIn('CABLE Output', self.ui.connection_hint_var.get())

    def test_missing_virtual_endpoint_does_not_choose_default_speakers(self):
        self.audio.suggested_device = lambda devices: ''
        self.ui.target_var.set('')
        self.ui.refresh_devices()
        self.assertEqual(self.ui.target_var.get(), '')
        with patch('app.messagebox.showwarning') as warning:
            self.ui.create_virtual()
        self.assertFalse(self.ui.sink_active)
        warning.assert_called_once()

    def test_disconnect_only_stops_app_audio(self):
        self.ui.create_virtual()
        with patch('app.command', side_effect=AssertionError('Driver removal attempted')):
            self.ui.remove_virtual()
        self.assertFalse(self.ui.sink_active)
        self.assertIsNone(self.ui.active_output)
        self.assertGreater(len(self.stops), 0)

    def test_portable_neural_playback_receives_selected_output(self):
        self.ui.create_virtual()
        cancel = threading.Event()
        with patch('portable_playback.play_neural') as playback:
            self.ui.play_worker('Xin chào', 'a', 155, app.NEURAL_ENGINE, cancel)
        self.assertEqual(playback.call_args.args[:4], (self.neural, 'Xin chào', 'a', 155))
        self.assertEqual(playback.call_args.kwargs['device'], 5)

    def test_refresh_does_not_reuse_old_index_for_different_hardware(self):
        self.ui.create_virtual()
        self.audio.devices = lambda: {'Speakers [WASAPI]': 5}
        self.audio.suggested_device = lambda devices: None
        self.ui.refresh_devices()
        self.assertFalse(self.ui.sink_active)
        self.assertIsNone(self.ui.active_output)

    def test_changing_output_during_model_download_does_not_cancel_setup(self):
        self.ui.preparing = True
        self.ui.playing = True
        self.ui.cancel_event = threading.Event()
        self.ui.on_output_changed()
        self.assertFalse(self.ui.cancel_event.is_set())
        self.assertTrue(self.ui.preparing)

    def test_refresh_during_setup_does_not_cancel_download_when_device_disappears(self):
        self.ui.create_virtual()
        self.ui.preparing = self.ui.playing = True
        self.ui.cancel_event = threading.Event()
        self.audio.devices = lambda: {'Speakers [WASAPI]': 5}
        self.audio.suggested_device = lambda devices: None
        self.ui.refresh_devices()
        self.assertFalse(self.ui.cancel_event.is_set())
        self.assertFalse(self.ui.sink_active)

    def test_actual_mac_builder_uses_blackhole_guidance(self):
        from qt_ui import QtRoot
        root = QtRoot()
        self.addCleanup(root.destroy)
        self.audio.devices = lambda: {'BlackHole 2ch': 7}
        self.audio.suggested_device = lambda devices: 'BlackHole 2ch'
        with patch('app.current_platform', return_value='darwin'), \
                patch('portable_audio.PortableAudio', return_value=self.audio), \
                patch('neural_backend.NeuralEngine', return_value=self.neural):
            ui = app.DiscordTTS(root)
        self.assertEqual(ui.target_var.get(), 'BlackHole 2ch')
        self.assertIn('BlackHole', ui.driver_button.widget.text())
        self.assertIn('BlackHole', ui.connection_hint_var.get())

    def test_mac_uses_blackhole_hint_and_driver_link(self):
        self.ui.platform = 'darwin'
        self.ui.target_devices = {'BlackHole 2ch': 7}
        self.ui.target_combo['values'] = ['BlackHole 2ch']
        self.ui.target_var.set('BlackHole 2ch')
        self.ui.create_virtual()
        self.assertIn('BlackHole', self.ui.connection_hint_var.get())
        with patch('app.webbrowser.open') as open_url:
            self.ui.open_driver_help()
        open_url.assert_called_once_with('https://existential.audio/blackhole/')


if __name__ == '__main__':
    unittest.main()
