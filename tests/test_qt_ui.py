"""Real Qt widget/controller integration, including offscreen layout checks."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from types import SimpleNamespace
import unittest

try:
    import qt_ui
except ImportError:
    qt_ui = None


ENGINES = ('VieNeu-TTS v3 Turbo (offline AI)', 'Microsoft Edge (online)',
           'eSpeak NG (offline)')


class QtLayoutTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(qt_ui, 'the modern Qt frontend must exist')
        self.root = qt_ui.QtRoot()
        self.addCleanup(self.root.destroy)
        self.root.geometry('820x720')
        self.root.minsize(560, 480)
        self.actions = []
        self.ui = SimpleNamespace(root=self.root)
        for name in ('on_engine_changed', 'on_voice_changed', 'create_virtual',
                     'remove_virtual', 'refresh_devices', 'update_preview',
                     'update_mix', 'speak', 'stop', 'setup_neural'):
            setattr(self.ui, name, lambda event=None, name=name: self.actions.append(name))
        qt_ui.build_ui(self.ui, None, ENGINES)
        self.root.window.show()
        self.flush()

    def flush(self):
        self.root.application.processEvents()
        self.root.application.processEvents()

    def assert_inside_window(self, adapter):
        widget = getattr(adapter, 'widget', adapter)
        self.assertTrue(widget.isVisible())
        origin = widget.mapTo(self.root.window, qt_ui.QtCore.QPoint(0, 0))
        self.assertTrue(self.root.window.rect().contains(
            qt_ui.QtCore.QRect(origin, widget.size())), str(widget.objectName()))

    def test_vieneu_is_default_and_temporary_or_optional_content_starts_hidden(self):
        self.assertEqual(self.ui.engine_var.get(), ENGINES[0])
        self.assertEqual(self.ui.engine_combo.widget.currentText(), ENGINES[0])
        self.assertTrue(self.ui.download_frame.widget.isHidden())
        self.assertTrue(self.ui.audio_settings.widget.isHidden())
        for button in (self.ui.speak_button, self.ui.stop_button, self.ui.start_button):
            self.assert_inside_window(button)
        self.assert_inside_window(self.ui.audio_settings_button)
        toggle = self.ui.audio_settings_button.widget
        toggle_bottom = toggle.mapTo(self.root.window, qt_ui.QtCore.QPoint(
            0, toggle.height())).y()
        footer_top = self.ui.footer.widget.mapTo(
            self.root.window, qt_ui.QtCore.QPoint(0, 0)).y()
        self.assertLessEqual(toggle_bottom, footer_top)

    def test_long_progress_and_devices_keep_actions_visible_at_every_window_size(self):
        self.ui.download_frame.grid()
        self.ui.download_label_var.set('Downloading nested/model_weights.data: ' * 30)
        self.ui.status.set('Preparing local speech. ' * 30)
        self.ui.engine_hint.set('Ready for offline speech. ' * 15)
        self.ui.audio_settings_button.widget.click()
        self.ui.speaker_combo['values'] = ['Long speaker hardware name ' * 20]
        self.ui.speaker_var.set('Long speaker hardware name ' * 20)
        self.ui.mic_combo['values'] = ['Long microphone hardware name ' * 20]
        self.ui.mic_var.set('Long microphone hardware name ' * 20)
        for width, height in ((560, 480), (740, 620), (840, 760)):
            with self.subTest(size=(width, height)):
                self.root.geometry(f'{width}x{height}')
                self.flush()
                self.assertEqual(self.root.window.width(), width)
                self.assertEqual(self.root.window.height(), height)
                for widget in (self.ui.speak_button, self.ui.stop_button,
                               self.ui.start_button, self.ui.status_label):
                    self.assert_inside_window(widget)
                self.assertEqual(self.ui.body_scroll.horizontalScrollBar().maximum(), 0)
                self.assertGreater(self.ui.body_scroll.verticalScrollBar().maximum(), 0)

    def test_programmatic_voice_changes_do_not_restart_speech_but_user_changes_do(self):
        self.ui.voice_combo['values'] = ['Giọng A — Bắc', 'Giọng B — Nam']
        self.ui.voice_var.set('Giọng A — Bắc')
        self.ui.engine_var.set(ENGINES[1])
        self.assertEqual(self.actions, [])
        self.assertEqual(self.ui.voice_combo.widget.currentText(), 'Giọng A — Bắc')
        self.ui.voice_combo.widget.activated[int].emit(1)
        self.assertEqual(self.ui.voice_var.get(), 'Giọng B — Nam')
        self.assertEqual(self.actions, ['on_voice_changed'])
        self.ui.voice_combo['values'] = ['Giọng B — Nam', 'Giọng C']
        self.assertEqual(self.ui.voice_var.get(), 'Giọng B — Nam')
        self.assertEqual(self.ui.voice_combo.widget.currentText(), 'Giọng B — Nam')
        self.assertEqual(self.actions, ['on_voice_changed'])
        self.ui.engine_combo.widget.activated[int].emit(0)
        self.assertEqual(self.ui.engine_var.get(), ENGINES[0])
        self.assertEqual(self.actions, ['on_voice_changed', 'on_engine_changed'])

    def test_existing_controller_progress_and_button_updates_work_with_qt(self):
        import app
        self.ui._show_download_widgets = lambda: app.DiscordTTS._show_download_widgets(self.ui)
        app.DiscordTTS.show_download_progress(self.ui, {
            'filename': 'weights.data', 'downloaded': 50, 'total': 100})
        self.flush()
        self.assertTrue(self.ui.download_frame.widget.isVisible())
        self.assertEqual(self.ui.download_bar.widget.value(), 50)
        app.DiscordTTS.download_stage(self.ui, 'Loading model...')
        self.assertEqual(self.ui.download_bar.widget.maximum(), 0)
        app.DiscordTTS.download_stage(self.ui, 'Ready.', finished=True, success=True)
        self.assertTrue(self.ui.download_frame.widget.isHidden())
        self.assertEqual(self.ui.download_label_var.get(), '')
        self.assertEqual(self.ui.download_bar.widget.value(), 100)
        self.ui.playing = True
        self.ui.preparing = self.ui.closing = self.ui.removing = False
        self.ui.sink_active = False
        self.ui.pending_speech = None
        self.ui.neural_ready = True
        self.ui._worker_alive = lambda: False
        self.ui.update_setup_button = lambda: app.DiscordTTS.update_setup_button(self.ui)
        app.DiscordTTS.update_action_buttons(self.ui)
        self.assertEqual(self.ui.speak_button.widget.text(), 'Restart speech')
        self.assertTrue(self.ui.stop_button.widget.isEnabled())
        self.assertTrue(self.ui.setup_button.widget.isHidden())
        self.assertFalse(self.ui.repair_button.widget.isHidden())
        self.ui.speak_button.widget.click()
        self.ui.stop_button.widget.click()
        self.assertEqual(self.actions, ['speak', 'stop'])

    def test_native_editor_exposes_current_unicode_text_to_controller(self):
        text = 'Xin chào!\nTiếng Việt ă â đ ê ô ơ ư 🙂'
        self.ui.text.widget.setPlainText(text)
        self.assertEqual(self.ui.text.get('1.0', 'end'), text)
        self.ui.preview_var.set(True)
        self.assertTrue(self.ui.preview_checkbox.isChecked())
        self.ui.preview_checkbox.click()
        self.assertFalse(self.ui.preview_var.get())
        self.assertEqual(self.actions, ['update_preview'])

    def test_root_close_waits_for_controller_cleanup_and_timers_run_on_event_loop(self):
        called = []
        self.root.after(0, lambda: called.append('timer'))
        self.flush()
        self.assertEqual(called, ['timer'])
        self.root.protocol('WM_DELETE_WINDOW', lambda: called.append('close'))
        self.root.window.close()
        self.assertEqual(called, ['timer', 'close'])
        self.assertTrue(self.root.window.isVisible())
        self.root.after(0, lambda: called.append('late timer'))
        self.root.destroy()
        self.flush()
        self.assertFalse(self.root.window.isVisible())
        self.assertEqual(called, ['timer', 'close'])

    def test_long_error_dialog_keeps_full_details_behind_a_compact_summary(self):
        payload = 'Offline AI setup failed: ' + '/very/long/model/cache/path/' * 60
        observed = {}

        def inspect_dialog():
            dialog = self.root.application.activeModalWidget()
            observed['summary'] = dialog.text()
            observed['details'] = dialog.detailedText()
            observed['width'] = dialog.width()
            dialog.accept()

        qt_ui.QtCore.QTimer.singleShot(0, inspect_dialog)
        qt_ui.dialogs.showerror('Discord TTS', payload)
        self.assertLess(len(observed['summary']), 300)
        self.assertEqual(observed['details'], payload)
        self.assertLessEqual(observed['width'], 640)


if __name__ == '__main__':
    unittest.main()
