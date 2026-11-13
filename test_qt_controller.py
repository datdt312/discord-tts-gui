"""Exercise the shipped controller through actual Qt widgets and timers."""
import os
import threading
import time
import types
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import app


class QtControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from qt_ui import QtRoot
        except ImportError as error:
            raise unittest.SkipTest('Qt unavailable: ' + str(error))
        cls.QtRoot = QtRoot

    def setUp(self):
        self.root = self.QtRoot()
        self.neural = types.SimpleNamespace(
            voices=lambda: {'Giọng A — Bắc': 'preset-a', 'Giọng B — Nam': 'preset-b'},
            stop=lambda: None, close=lambda: None)
        with patch('neural_backend.NeuralEngine', return_value=self.neural), \
                patch('app.pulse_list', return_value=[]):
            self.ui = app.DiscordTTS(self.root)
        self.root.window.show()
        self.pump()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.ui.stop()
        worker = self.ui.worker_thread
        if worker is not None:
            worker.join(2)
        self.root.destroy()
        self.pump()

    def pump(self, until=None, timeout=1):
        deadline = time.monotonic() + timeout
        while True:
            self.root.application.processEvents()
            if until is None or until():
                return
            if time.monotonic() >= deadline:
                self.fail('Qt event loop did not reach expected state')
            time.sleep(0.005)

    def test_shipped_controller_defaults_to_ready_vieneu_without_download_controls(self):
        self.assertEqual(self.ui.engine_var.get(), app.NEURAL_ENGINE)
        self.assertEqual(self.ui.voice_var.get(), 'Giọng A — Bắc')
        self.assertFalse(self.ui.setup_button.widget.isVisible())
        self.assertFalse(self.ui.download_frame.widget.isVisible())
        self.assertTrue(self.ui.speak_button.widget.isVisible())

    def test_progress_disappears_after_setup_and_main_controls_stay_accessible(self):
        self.ui.preparing = self.ui.playing = True
        self.ui.events.put(('download_progress', {
            'filename': 'weights.data', 'downloaded': 50, 'total': 100}))
        self.ui.poll()
        self.pump()
        self.assertTrue(self.ui.download_frame.widget.isVisible())
        self.assertIn('50.0%', self.ui.download_label_var.get())
        self.ui.events.put(('neural_ready', self.neural.voices()))
        self.ui.poll()
        self.pump()
        self.assertFalse(self.ui.download_frame.widget.isVisible())
        self.assertFalse(self.ui.setup_button.widget.isVisible())
        self.assertEqual(self.ui.download_label_var.get(), '')
        self.assertTrue(self.ui.speak_button.widget.isEnabled())

    def test_missing_model_shows_download_without_starting_any_worker(self):
        self.neural.voices = lambda: {}
        self.ui.load_voices()
        self.pump()
        self.assertTrue(self.ui.setup_button.widget.isVisible())
        self.assertEqual(self.ui.voice_names, {})
        self.assertIsNone(self.ui.worker_thread)
        self.assertFalse(self.ui.preparing)

    def test_ctrl_a_and_paste_replace_unicode_selection_once_with_undo(self):
        import qt_ui
        if qt_ui.QT_BINDING == 'PyQt6':
            from PyQt6.QtTest import QTest
        else:
            from PyQt5.QtTest import QTest
        control = qt_ui._enum(qt_ui.QtCore.Qt, 'KeyboardModifier', 'ControlModifier')
        editor = self.ui.text.widget
        original = 'Nội dung cũ — tiếng Việt'
        replacement = 'Xin chào!\nĐây là nội dung mới 🙂'
        editor.setPlainText(original)
        editor.setFocus()
        QTest.keyClick(editor, qt_ui._enum(qt_ui.QtCore.Qt, 'Key', 'Key_A'), control)
        self.assertEqual(editor.textCursor().selectedText(), original)
        self.root.application.clipboard().setText(replacement)
        QTest.keyClick(editor, qt_ui._enum(qt_ui.QtCore.Qt, 'Key', 'Key_V'), control)
        self.assertEqual(self.ui.text.get(), replacement)
        QTest.keyClick(editor, qt_ui._enum(qt_ui.QtCore.Qt, 'Key', 'Key_Z'), control)
        self.assertEqual(self.ui.text.get(), original)

    def test_pasting_empty_clipboard_preserves_selected_text(self):
        import qt_ui
        if qt_ui.QT_BINDING == 'PyQt6':
            from PyQt6.QtTest import QTest
        else:
            from PyQt5.QtTest import QTest
        editor = self.ui.text.widget
        original = 'Giữ nguyên phần đang chọn'
        editor.setPlainText(original)
        editor.selectAll()
        self.root.application.clipboard().clear()
        control = qt_ui._enum(qt_ui.QtCore.Qt, 'KeyboardModifier', 'ControlModifier')
        QTest.keyClick(editor, qt_ui._enum(qt_ui.QtCore.Qt, 'Key', 'Key_V'), control)
        self.assertEqual(self.ui.text.get(), original)

    def test_real_speak_button_replaces_text_using_qt_restart_timer(self):
        self.ui.sink_active = True
        self.ui.text.widget.setPlainText('old text')
        started = []
        active = []
        maximum = []
        cancelled = threading.Event()

        def worker(text, voice, speed, engine, cancel, events):
            active.append(text)
            maximum.append(len(active))
            started.append(text)
            try:
                cancel.wait(3)
                if text == 'old text':
                    cancelled.set()
                    # Keep cleanup active long enough to exercise the Qt timer.
                    time.sleep(0.05)
                events.put(('done', 'Finished ' + text))
            finally:
                active.remove(text)

        self.ui.play_worker = worker
        self.ui.speak_button.widget.click()
        self.pump(lambda: started == ['old text'])
        self.ui.text.widget.setPlainText('latest Vietnamese: Xin chào!')
        self.ui.speak_button.widget.click()
        self.pump(lambda: len(started) == 2)
        self.assertTrue(cancelled.is_set())
        self.assertEqual(started, ['old text', 'latest Vietnamese: Xin chào!'])
        self.assertEqual(max(maximum), 1)
        self.assertTrue(self.ui.playing)
        self.ui.stop_button.widget.click()
        self.pump(lambda: not self.ui.worker_thread.is_alive())
        self.ui.poll()
        self.assertFalse(self.ui.playing)
        self.assertIsNone(self.ui.pending_speech)


if __name__ == '__main__':
    unittest.main()
