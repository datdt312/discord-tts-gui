"""Exercise the desktop layout with real Tk widgets when a display is available."""
import tkinter as tk
from types import SimpleNamespace
import unittest

try:
    from desktop_ui import build_ui
except ModuleNotFoundError:
    build_ui = None


ENGINES = ('VieNeu-TTS v3 Turbo (offline AI)', 'Microsoft Edge (online)',
           'eSpeak NG (offline)')


class DesktopLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.display = tk.Tk()
        except tk.TclError as error:
            raise unittest.SkipTest('Real Tk display unavailable: ' + str(error))
        cls.display.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.display.destroy()

    def setUp(self):
        self.assertIsNotNone(build_ui, 'the responsive desktop builder must exist')
        self.root = tk.Toplevel(self.display)
        self.root.geometry('740x620')
        self.addCleanup(self.root.destroy)
        self.actions = []
        self.ui = SimpleNamespace(root=self.root)
        for name in ('on_engine_changed', 'on_voice_changed', 'create_virtual',
                     'remove_virtual', 'refresh_devices', 'update_preview',
                     'update_mix', 'speak', 'stop', 'setup_neural'):
            setattr(self.ui, name, lambda event=None, name=name: self.actions.append(name))
        build_ui(self.ui, lambda text: None, ENGINES)
        self.root.update()

    def assert_inside_window(self, widget):
        self.assertTrue(widget.winfo_ismapped(), str(widget))
        self.assertGreaterEqual(widget.winfo_rootx(), self.root.winfo_rootx())
        self.assertGreaterEqual(widget.winfo_rooty(), self.root.winfo_rooty())
        self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(),
                             self.root.winfo_rootx() + self.root.winfo_width())
        self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(),
                             self.root.winfo_rooty() + self.root.winfo_height())

    def test_defaults_to_vieneu_with_progress_and_optional_audio_settings_hidden(self):
        self.assertEqual(self.ui.engine_var.get(), ENGINES[0])
        self.assertFalse(self.ui.download_frame.winfo_ismapped())
        self.assertFalse(self.ui.audio_settings.winfo_ismapped())
        for widget in (self.ui.speak_button, self.ui.stop_button, self.ui.start_button):
            self.assert_inside_window(widget)

    def test_long_download_and_device_details_never_displace_footer_actions(self):
        self.ui.download_label_var.set('Downloading weights/large_model.data: ' * 25)
        self.ui.download_frame.grid()
        self.ui.engine_hint.set('Download offline voices before speaking. ' * 12)
        self.ui.status.set('Preparing offline speech. ' * 12)
        self.ui.audio_settings_button.invoke()
        self.ui.speaker_var.set('Long speaker name with hardware details ' * 12)
        self.ui.mic_var.set('Long microphone name with hardware details ' * 12)
        for width, height in ((560, 480), (740, 620), (840, 760)):
            with self.subTest(size=(width, height)):
                self.root.geometry(f'{width}x{height}')
                self.root.update()
                for widget in (self.ui.speak_button, self.ui.stop_button,
                               self.ui.start_button, self.ui.status_label):
                    self.assert_inside_window(widget)
                for combo in (self.ui.engine_combo, self.ui.voice_combo,
                              self.ui.speaker_combo, self.ui.mic_combo):
                    self.assertLessEqual(combo.winfo_rootx() + combo.winfo_width(),
                                         self.root.winfo_rootx() + width)
                self.assertGreater(self.ui.body_canvas.bbox('all')[3],
                                   self.ui.body_canvas.winfo_height())

    def test_audio_controls_can_be_reached_by_scrolling_while_speak_stays_visible(self):
        self.root.geometry('560x480')
        self.ui.audio_settings_button.invoke()
        self.root.update()
        self.ui.body_canvas.yview_moveto(1)
        self.root.update()
        self.assertTrue(self.ui.audio_settings.winfo_ismapped())
        self.assert_inside_window(self.ui.remove_button)
        self.assert_inside_window(self.ui.speak_button)
        self.ui.audio_settings_button.invoke()
        self.root.update()
        self.assertFalse(self.ui.audio_settings.winfo_ismapped())
        self.assert_inside_window(self.ui.speak_button)

    def test_engine_voice_and_action_controls_use_controller_callbacks(self):
        self.ui.engine_combo.event_generate('<<ComboboxSelected>>')
        self.ui.voice_combo.event_generate('<<ComboboxSelected>>')
        self.ui.speak_button.invoke()
        self.ui.stop_button.invoke()
        self.ui.start_button.invoke()
        self.assertEqual(self.actions, ['on_engine_changed', 'on_voice_changed',
                                        'speak', 'stop', 'create_virtual'])

    def test_keyboard_focus_reveals_a_control_below_the_editor(self):
        self.root.geometry('560x480')
        self.root.update()
        self.ui.voice_combo.event_generate('<FocusIn>')
        self.root.update()
        self.assertGreaterEqual(self.ui.voice_combo.winfo_rooty(),
                                self.ui.body_canvas.winfo_rooty())
        self.assertLessEqual(self.ui.voice_combo.winfo_rooty() + self.ui.voice_combo.winfo_height(),
                             self.ui.body_canvas.winfo_rooty() + self.ui.body_canvas.winfo_height())
        self.assert_inside_window(self.ui.speak_button)


if __name__ == '__main__':
    unittest.main()
