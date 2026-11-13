"""Text shortcut regressions, with optional real Tk/clipboard integration."""
import unittest

import app


class TextBuffer:
    """Small in-memory widget boundary for environments without an X display."""
    def __init__(self, content, clipboard=''):
        self.content = content
        self.clipboard = clipboard
        self.selection = ()
        self.cursor = len(content)
        self.bindings = {}

    def bind(self, sequence, callback):
        self.bindings[sequence] = callback

    def press(self, sequence):
        return self.bindings[sequence](None)

    def offset(self, index):
        return {'1.0': 0, 'end-1c': len(self.content), 'end': len(self.content),
                'insert': self.cursor}.get(index, index)

    def tag_add(self, tag, start, end):
        self.selection = (self.offset(start), self.offset(end))

    def tag_ranges(self, tag):
        return self.selection

    def tag_remove(self, tag, start, end):
        self.selection = ()

    def mark_set(self, mark, index):
        self.cursor = self.offset(index)

    def clipboard_get(self):
        if self.clipboard is None:
            raise app.tk.TclError('CLIPBOARD selection does not exist')
        return self.clipboard

    def replace(self, start, end, value):
        start, end = self.offset(start), self.offset(end)
        self.content = self.content[:start] + value + self.content[end:]
        if self.cursor >= end:
            self.cursor += len(value) - (end - start)
        elif self.cursor >= start:
            self.cursor = start + len(value)

    def insert(self, index, value):
        index = self.offset(index)
        self.replace(index, index, value)

    def edit_separator(self):
        pass

    def see(self, index):
        pass


class TextShortcutTests(unittest.TestCase):
    def buffer(self, content, clipboard=''):
        text = TextBuffer(content, clipboard)
        app.bind_text_shortcuts(text)
        return text

    def test_ctrl_a_selects_entire_multiline_vietnamese_text(self):
        for shortcut in ('<Control-a>', '<Control-A>', '<<SelectAll>>'):
            with self.subTest(shortcut=shortcut):
                content = 'Xin chào\nTiếng Việt 🙂'
                text = self.buffer(content)
                self.assertEqual(text.press(shortcut), 'break')
                self.assertEqual(text.selection, (0, len(content)))
                self.assertEqual(text.content, content)

    def test_paste_replaces_selection_even_when_cursor_is_outside_selection(self):
        text = self.buffer('trước CŨ sau', 'mới\nTiếng Việt 🙂')
        text.selection = (6, 8)
        text.cursor = len(text.content)
        self.assertEqual(text.press('<<Paste>>'), 'break')
        self.assertEqual(text.content, 'trước mới\nTiếng Việt 🙂 sau')
        self.assertFalse(text.selection)
        self.assertEqual(text.cursor, len('trước mới\nTiếng Việt 🙂'))

    def test_select_all_then_paste_replaces_entire_content_once(self):
        text = self.buffer('Nội dung cũ\ndòng hai', 'Nội dung mới')
        text.press('<Control-a>')
        text.press('<<Paste>>')
        self.assertEqual(text.content, 'Nội dung mới')

    def test_paste_without_selection_inserts_at_cursor(self):
        text = self.buffer('Xin !', 'chào')
        text.cursor = 4
        text.press('<<Paste>>')
        self.assertEqual(text.content, 'Xin chào!')

    def test_empty_or_unavailable_clipboard_preserves_selected_text(self):
        for clipboard in ('', None):
            with self.subTest(clipboard=clipboard):
                text = self.buffer('Giữ nguyên nội dung', clipboard)
                text.selection = (0, len(text.content))
                self.assertEqual(text.press('<<Paste>>'), 'break')
                self.assertEqual(text.content, 'Giữ nguyên nội dung')
                self.assertEqual(text.selection, (0, len(text.content)))


class TkTextIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = app.tk.Tk()
        except app.tk.TclError as error:
            raise unittest.SkipTest('Real Tk display unavailable: ' + str(error))
        cls.addClassCleanup(cls.root.destroy)

    def setUp(self):
        ui = object.__new__(app.DiscordTTS)
        ui.root = self.root
        ui.build()
        self.text = ui.text
        self.text.delete('1.0', 'end')
        self.text.edit_reset()
        for child in self.root.winfo_children():
            self.addCleanup(child.destroy)
        self.root.update()
        self.text.focus_force()
        self.root.update()

    def test_actual_ctrl_a_key_event_selects_every_character(self):
        self.text.insert('1.0', 'Xin chào\nTiếng Việt 🙂')
        self.text.event_generate('<Control-a>')
        self.root.update()
        self.assertEqual(self.text.get('sel.first', 'sel.last'), 'Xin chào\nTiếng Việt 🙂')

    def test_paste_replacement_has_one_step_undo_and_redo(self):
        original = 'trước CŨ sau'
        self.text.insert('1.0', original)
        self.text.edit_reset()
        self.text.tag_add('sel', '1.6', '1.8')
        self.text.mark_set('insert', 'end-1c')
        self.text.clipboard_clear()
        self.text.clipboard_append('mới 🙂')
        self.text.event_generate('<<Paste>>')
        self.root.update()
        self.assertEqual(self.text.get('1.0', 'end-1c'), 'trước mới 🙂 sau')
        self.text.edit_undo()
        self.assertEqual(self.text.get('1.0', 'end-1c'), original)
        self.text.edit_redo()
        self.assertEqual(self.text.get('1.0', 'end-1c'), 'trước mới 🙂 sau')


if __name__ == '__main__':
    unittest.main()
