"""Qt desktop frontend with small adapters for the existing speech controller.

Qt owns widgets, native editing and its event loop. The controller continues
to own requests, cancellation, model setup and audio routing.
"""
import re
import sys
import textwrap
import weakref

try:
    from PyQt6 import QtCore, QtGui, QtWidgets
    QT_BINDING = 'PyQt6'
except ImportError:
    from PyQt5 import QtCore, QtGui, QtWidgets
    QT_BINDING = 'PyQt5'


def _enum(owner, group, name):
    """Qt 6 scopes enums; Qt 5 exposes the same values on their owner."""
    scoped = getattr(owner, group, None)
    if scoped is not None and hasattr(scoped, name):
        return getattr(scoped, name)
    return getattr(owner, name)


def _without_signals(widget, callback):
    previous = widget.blockSignals(True)
    try:
        callback()
    finally:
        widget.blockSignals(previous)


class Value:
    def __init__(self, value=''):
        self._value = value
        self._listeners = []

    def get(self):
        return self._value

    def set(self, value):
        if self._value == value:
            return
        self._value = value
        for listener in self._listeners:
            listener(value)

    def connect(self, listener):
        self._listeners.append(listener)
        listener(self._value)


class Widget:
    def __init__(self, widget):
        self.widget = widget

    def grid(self, **unused):
        self.widget.show()

    def grid_remove(self):
        self.widget.hide()

    def configure(self, **options):
        if 'state' in options:
            self.widget.setEnabled(options['state'] != 'disabled')
        if 'text' in options:
            self.widget.setText(str(options['text']))


class Text(Widget):
    def get(self, start='1.0', end='end'):
        return self.widget.toPlainText()


class _ComboBox(QtWidgets.QComboBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        # Keep a clear dropdown affordance with either Qt binding/style. Some
        # native styles omit their arrow after a rounded stylesheet is applied.
        painter = QtGui.QPainter(self)
        painter.setRenderHint(_enum(QtGui.QPainter, 'RenderHint', 'Antialiasing'))
        pen = QtGui.QPen(QtGui.QColor('#64748b' if self.isEnabled() else '#a0adbf'))
        pen.setWidthF(1.6)
        pen.setCapStyle(_enum(QtCore.Qt, 'PenCapStyle', 'RoundCap'))
        painter.setPen(pen)
        center_x, center_y = self.width() - 19, self.height() / 2
        painter.drawPolyline(QtGui.QPolygonF([
            QtCore.QPointF(center_x - 4, center_y - 2),
            QtCore.QPointF(center_x, center_y + 2),
            QtCore.QPointF(center_x + 4, center_y - 2),
        ]))


class Combo(Widget):
    def __init__(self, variable, values=(), command=None):
        super().__init__(_ComboBox())
        self.variable = variable
        self.widget.setMinimumWidth(0)
        self.widget.setMinimumContentsLength(1)
        self.widget.setSizeAdjustPolicy(_enum(
            QtWidgets.QComboBox, 'SizeAdjustPolicy', 'AdjustToMinimumContentsLengthWithIcon'))
        self.widget.setSizePolicy(_enum(QtWidgets.QSizePolicy, 'Policy', 'Expanding'),
                                  _enum(QtWidgets.QSizePolicy, 'Policy', 'Fixed'))
        self['values'] = values
        variable.connect(self._show_value)

        def activated(index):
            variable.set(self.widget.itemText(index))
            if command is not None:
                command()

        # Only user activation restarts speech. Clearing/repopulating the list
        # or setting a stored voice must never look like another user request.
        self.widget.activated[int].connect(activated)

    def _show_value(self, value):
        _without_signals(self.widget, lambda: self.widget.setCurrentIndex(
            self.widget.findText(str(value))))

    def __setitem__(self, key, values):
        if key != 'values':
            raise KeyError(key)

        def replace_items():
            self.widget.clear()
            self.widget.addItems([str(value) for value in values])
            self.widget.setCurrentIndex(self.widget.findText(str(self.variable.get())))

        _without_signals(self.widget, replace_items)

    def __getitem__(self, key):
        if key != 'values':
            raise KeyError(key)
        return tuple(self.widget.itemText(index) for index in range(self.widget.count()))


class Progress(Widget):
    def __init__(self):
        super().__init__(QtWidgets.QProgressBar())
        self.mode = 'determinate'
        self.widget.setRange(0, 100)
        self.widget.setValue(0)
        self.widget.setTextVisible(False)
        self.widget.setFixedHeight(7)

    def configure(self, *, mode=None, value=None):
        if mode is not None:
            self.mode = mode
            self.widget.setRange(0, 0 if mode == 'indeterminate' else 100)
        if value is not None and self.mode != 'indeterminate':
            self.widget.setValue(max(0, min(100, round(value))))

    def start(self, interval=15):
        if self.mode == 'indeterminate':
            self.widget.setRange(0, 0)

    def stop(self):
        if self.mode == 'indeterminate':
            self.widget.setRange(0, 100)
            self.widget.setValue(0)


class _Window(QtWidgets.QMainWindow):
    def __init__(self, owner):
        super().__init__()
        self._owner = weakref.ref(owner)

    def closeEvent(self, event):
        owner = self._owner()
        if owner is None or owner._destroyed:
            event.accept()
            return
        event.ignore()
        if owner._close_callback is None:
            owner.destroy()
        else:
            owner._close_callback()
        # Cleanup can finish synchronously inside the controller's close().
        if owner._destroyed:
            event.accept()


_application = None


class QtRoot:
    def __init__(self):
        global _application
        if QtWidgets.QApplication.instance() is None:
            _application = QtWidgets.QApplication(sys.argv)
        self.application = QtWidgets.QApplication.instance()
        self.app = self.application
        self.application.setApplicationName('discord-tts-gui')
        self.application.setApplicationDisplayName('Discord TTS')
        self.application.setDesktopFileName('discord-tts-gui-packaged')
        self.application.setStyle('Fusion')
        self.application.setFont(QtGui.QFont('Noto Sans', 10))
        icon = QtGui.QIcon.fromTheme('discord-tts-gui')
        if not icon.isNull():
            self.application.setWindowIcon(icon)
        self._close_callback = None
        self._destroyed = False
        self._timers = set()
        self.window = _Window(self)
        self.window.setObjectName('DiscordTTS')
        self.window.resize(820, 720)
        self.window.setMinimumSize(560, 480)

    def title(self, text):
        self.window.setWindowTitle(text)

    def geometry(self, value=None):
        if value is None:
            return f'{self.window.width()}x{self.window.height()}'
        match = re.fullmatch(r'(\d+)x(\d+)(?:([+-]\d+)([+-]\d+))?', value)
        if match is None:
            raise ValueError('Expected window geometry WIDTHxHEIGHT')
        self.window.resize(int(match[1]), int(match[2]))
        if match[3] is not None:
            self.window.move(int(match[3]), int(match[4]))

    def minsize(self, width, height):
        self.window.setMinimumSize(width, height)

    def after(self, milliseconds, callback):
        if self._destroyed:
            return None
        timer = QtCore.QTimer(self.window)
        timer.setSingleShot(True)

        def invoke():
            self._timers.discard(timer)
            timer.deleteLater()
            if not self._destroyed:
                callback()

        timer.timeout.connect(invoke)
        self._timers.add(timer)
        timer.start(milliseconds)
        return timer

    def protocol(self, name, callback):
        if name != 'WM_DELETE_WINDOW':
            raise ValueError('Unsupported window protocol: ' + name)
        self._close_callback = callback

    def destroy(self):
        if self._destroyed:
            return
        self._destroyed = True
        for timer in self._timers:
            timer.stop()
            timer.deleteLater()
        self._timers.clear()
        self.window.close()

    def mainloop(self):
        self.window.show()
        execute = getattr(self.application, 'exec', None) or self.application.exec_
        return execute()


class _Dialogs:
    @staticmethod
    def showwarning(title, text):
        return _Dialogs._show('Warning', title, text)

    @staticmethod
    def showerror(title, text):
        return _Dialogs._show('Critical', title, text)

    @staticmethod
    def _show(icon, title, text):
        payload = str(text)
        compact = ' '.join(payload.split())
        box = QtWidgets.QMessageBox(QtWidgets.QApplication.activeWindow())
        box.setWindowTitle(str(title))
        box.setIcon(_enum(QtWidgets.QMessageBox, 'Icon', icon))
        box.setStandardButtons(_enum(QtWidgets.QMessageBox, 'StandardButton', 'Ok'))
        box.setTextFormat(_enum(QtCore.Qt, 'TextFormat', 'PlainText'))
        box.setTextInteractionFlags(
            _enum(QtCore.Qt, 'TextInteractionFlag', 'TextSelectableByMouse')
            | _enum(QtCore.Qt, 'TextInteractionFlag', 'TextSelectableByKeyboard'))
        if len(compact) > 250:
            compact = compact[:217].rstrip() + '…'
            box.setInformativeText('Open Show Details for the complete error message.')
            box.setDetailedText(payload)
        # Long unbroken cache paths should not dictate the dialog's width.
        box.setText(textwrap.fill(compact, width=64, break_long_words=True,
                                  break_on_hyphens=False))
        execute = getattr(box, 'exec', None) or box.exec_
        return execute()


dialogs = _Dialogs()


STYLESHEET = '''
QMainWindow, QWidget#Surface { background: #f5f7fb; color: #17243b; }
QWidget { font-family: "Noto Sans", "Segoe UI", sans-serif; font-size: 13px; color: #17243b; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: #f5f7fb; }
QFrame#Card { background: #ffffff; border: 1px solid #e1e7f0; border-radius: 16px; }
QFrame#Footer { background: #ffffff; border-top: 1px solid #e1e7f0; }
QFrame#Download { background: #edf4ff; border: 1px solid #dbe9ff; border-radius: 10px; }
QLabel { background: transparent; border: none; }
QLabel#Logo { background: #2563eb; color: white; border-radius: 12px; font-size: 22px; font-weight: 700; }
QLabel#Title { font-size: 25px; font-weight: 700; letter-spacing: -0.5px; }
QLabel#Subtitle, QLabel#Hint, QLabel#ConnectionHint { color: #5a6b82; }
QLabel#Subtitle { font-size: 12px; }
QLabel#SectionTitle { font-size: 15px; font-weight: 600; }
QLabel#FieldLabel { color: #41526a; font-size: 12px; font-weight: 600; }
QLabel#EditorHint { color: #7a899c; font-size: 11px; }
QLabel#ConnectionHint { font-size: 11px; }
QPlainTextEdit { background: #ffffff; border: none; border-radius: 6px;
                padding: 4px 0px; font-size: 16px; selection-background-color: #dbeafe;
                selection-color: #17243b; }
QPlainTextEdit:focus { background: #ffffff; }
QComboBox, QSpinBox { background: #f8fafd; border: 1px solid #d5deeb; border-radius: 8px;
                      padding: 9px 12px; min-height: 18px; selection-background-color: #2563eb; }
QComboBox:focus, QSpinBox:focus { border: 1px solid #2563eb; background: #ffffff; }
QComboBox:disabled { color: #8b98a9; background: #f1f4f8; }
QComboBox::drop-down { border: none; width: 30px; }
QComboBox::down-arrow { image: none; }
QComboBox QAbstractItemView { background: #ffffff; color: #17243b; padding: 5px;
                            border: 1px solid #d5deeb; selection-background-color: #e6efff;
                            selection-color: #173b83; outline: none; }
QPushButton, QToolButton { background: #ffffff; border: 1px solid #d5deeb; border-radius: 8px;
                         padding: 10px 14px; font-weight: 500; min-height: 18px; }
QPushButton:hover, QToolButton:hover { background: #f0f5fd; border-color: #a9bddb; }
QPushButton:pressed, QToolButton:pressed { background: #e4edfc; }
QPushButton:focus, QToolButton:focus { border: 2px solid #2563eb; padding: 9px 13px; }
QPushButton:disabled { background: #f5f7fa; border-color: #e2e8f0; color: #8b98a9; }
QPushButton#Speak { background: #2563eb; color: #ffffff; border-color: #2563eb; font-weight: 600; }
QPushButton#Speak:hover { background: #1d4ed8; border-color: #1d4ed8; }
QPushButton#Speak:pressed { background: #1e40af; }
QPushButton#Speak:focus { border: 2px solid #152f66; }
QPushButton#Speak:disabled { background: #adc4eb; border-color: #adc4eb; color: #ffffff; }
QPushButton#Setup { background: #edf4ff; color: #1d4ed8; border-color: #c9dcff; }
QPushButton#Stop { color: #b33d4c; }
QPushButton#Stop:disabled { color: #99a4b4; }
QToolButton#SettingsToggle { text-align: left; border: none; background: transparent; padding: 2px; }
QToolButton#SettingsToggle:focus { border: 1px solid #2563eb; border-radius: 5px; }
QCheckBox { spacing: 9px; background: transparent; }
QCheckBox::indicator { width: 17px; height: 17px; border: 1px solid #b6c6dc; border-radius: 5px; background: white; }
QCheckBox::indicator:checked { background: #2563eb; border-color: #2563eb; }
QCheckBox:focus { color: #1d4ed8; }
QProgressBar { border: none; border-radius: 3px; background: #dce7f7; }
QProgressBar::chunk { background: #2563eb; border-radius: 3px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #c4d0e1; min-height: 28px; border-radius: 3px; }
QScrollBar::handle:vertical:hover { background: #9aaec9; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
'''


def _label(text='', name='', variable=None, wrap=False):
    label = QtWidgets.QLabel(str(text))
    label.setObjectName(name)
    label.setTextFormat(_enum(QtCore.Qt, 'TextFormat', 'PlainText'))
    if wrap:
        label.setWordWrap(True)
        label.setMinimumWidth(0)
        label.setSizePolicy(_enum(QtWidgets.QSizePolicy, 'Policy', 'Ignored'),
                            _enum(QtWidgets.QSizePolicy, 'Policy', 'Preferred'))
    if variable is not None:
        variable.connect(lambda value: label.setText(str(value)))
    return label


def _button(text, command, name=''):
    button = QtWidgets.QPushButton(text)
    button.setObjectName(name)
    button.clicked.connect(lambda checked=False: command())
    return Widget(button)


def _card():
    frame = QtWidgets.QFrame()
    frame.setObjectName('Card')
    frame.setMinimumWidth(0)
    layout = QtWidgets.QVBoxLayout(frame)
    layout.setContentsMargins(20, 12, 20, 12)
    layout.setSpacing(12)
    return frame, layout


def _checkbox(text, variable, command):
    checkbox = QtWidgets.QCheckBox(text)
    variable.connect(lambda value: _without_signals(
        checkbox, lambda: checkbox.setChecked(bool(value))))

    def toggled(checked):
        variable.set(checked)
        command()

    checkbox.toggled.connect(toggled)
    return checkbox


def build_ui(ui, bind_text_shortcuts_unused, engine_choices):
    window = ui.root.window
    window.setStyleSheet(STYLESHEET)
    surface = QtWidgets.QWidget()
    surface.setObjectName('Surface')
    window.setCentralWidget(surface)
    shell = QtWidgets.QVBoxLayout(surface)
    shell.setContentsMargins(0, 0, 0, 0)
    shell.setSpacing(0)

    ui.body_scroll = QtWidgets.QScrollArea()
    ui.body_scroll.setWidgetResizable(True)
    ui.body_scroll.setHorizontalScrollBarPolicy(_enum(
        QtCore.Qt, 'ScrollBarPolicy', 'ScrollBarAlwaysOff'))
    shell.addWidget(ui.body_scroll, 1)
    body = QtWidgets.QWidget()
    body.setObjectName('Surface')
    body.setMinimumWidth(0)
    body_layout = QtWidgets.QVBoxLayout(body)
    body_layout.setContentsMargins(24, 18, 24, 18)
    body_layout.setSpacing(14)
    ui.body_scroll.setWidget(body)

    header = QtWidgets.QHBoxLayout()
    header.setSpacing(12)
    logo = _label('D', 'Logo')
    logo.setAlignment(_enum(QtCore.Qt, 'AlignmentFlag', 'AlignCenter'))
    logo.setFixedSize(46, 46)
    header.addWidget(logo)
    heading = QtWidgets.QVBoxLayout()
    heading.setSpacing(2)
    heading.addWidget(_label('Discord TTS', 'Title'))
    heading.addWidget(_label('Text to speech for your Discord microphone', 'Subtitle', wrap=True))
    header.addLayout(heading, 1)
    body_layout.addLayout(header)

    editor_card, editor_layout = _card()
    editor_heading = QtWidgets.QHBoxLayout()
    editor_heading.addWidget(_label('Your message', 'SectionTitle'))
    editor_heading.addStretch()
    editor_heading.addWidget(_label('Ctrl+A to select all', 'EditorHint'))
    editor_layout.addLayout(editor_heading)
    editor = QtWidgets.QPlainTextEdit()
    editor.setAccessibleName('Text to speak')
    editor.setPlaceholderText('What would you like to say?')
    editor.setFixedHeight(100)
    editor.setPlainText('Xin chào mọi người! Đây là giọng đọc từ Discord TTS trên Kubuntu.')
    editor_layout.addWidget(editor)
    ui.text = Text(editor)
    body_layout.addWidget(editor_card)

    speech_card, speech_layout = _card()
    speech_layout.setSpacing(9)
    speech_layout.addWidget(_label('Voice & delivery', 'SectionTitle'))
    speech_layout.addWidget(_label('Speech engine', 'FieldLabel'))
    ui.engine_var = Value(engine_choices[0])
    ui.engine_combo = Combo(ui.engine_var, engine_choices, ui.on_engine_changed)
    ui.engine_combo.widget.setAccessibleName('Speech engine')
    speech_layout.addWidget(ui.engine_combo.widget)
    ui.engine_hint = Value()
    speech_layout.addWidget(_label(name='Hint', variable=ui.engine_hint, wrap=True))
    ui.setup_button = _button('Download offline AI voices', ui.setup_neural, 'Setup')
    speech_layout.addWidget(ui.setup_button.widget)
    ui.setup_button.grid_remove()

    download = QtWidgets.QFrame()
    download.setObjectName('Download')
    download_layout = QtWidgets.QVBoxLayout(download)
    download_layout.setContentsMargins(12, 12, 12, 12)
    download_layout.setSpacing(9)
    ui.download_label_var = Value()
    download_layout.addWidget(_label(variable=ui.download_label_var, wrap=True))
    ui.download_bar = Progress()
    download_layout.addWidget(ui.download_bar.widget)
    speech_layout.addWidget(download)
    ui.download_frame = Widget(download)
    ui.download_frame.grid_remove()

    voice_row = QtWidgets.QWidget()
    voice_layout = QtWidgets.QVBoxLayout(voice_row)
    voice_layout.setContentsMargins(0, 0, 0, 0)
    voice_layout.setSpacing(7)
    voice_layout.addWidget(_label('Language / voice', 'FieldLabel'))
    ui.voice_var = Value()
    ui.voice_combo = Combo(ui.voice_var, command=ui.on_voice_changed)
    ui.voice_combo.widget.setAccessibleName('Language / voice')
    voice_layout.addWidget(ui.voice_combo.widget)
    ui.voice_row = Widget(voice_row)
    speech_layout.addWidget(voice_row)
    speed_row = QtWidgets.QHBoxLayout()
    speed_row.addWidget(_label('Speed', 'FieldLabel'))
    speed_row.addStretch()
    speed = QtWidgets.QSpinBox()
    speed.setRange(80, 320)
    speed.setSingleStep(10)
    speed.setFixedWidth(104)
    speed.setButtonSymbols(_enum(QtWidgets.QAbstractSpinBox, 'ButtonSymbols', 'NoButtons'))
    speed.setAlignment(_enum(QtCore.Qt, 'AlignmentFlag', 'AlignCenter'))
    speed.setAccessibleName('Speech speed')
    ui.speed_var = Value(155)
    ui.speed_var.connect(lambda value: _without_signals(speed, lambda: speed.setValue(int(value))))
    speed.valueChanged.connect(ui.speed_var.set)
    speed_row.addWidget(speed)
    speech_layout.addLayout(speed_row)
    body_layout.addWidget(speech_card)

    settings_card, settings_layout = _card()
    toggle = QtWidgets.QToolButton()
    toggle.setObjectName('SettingsToggle')
    toggle.setText('Audio & settings')
    toggle.setToolButtonStyle(_enum(QtCore.Qt, 'ToolButtonStyle', 'ToolButtonTextBesideIcon'))
    toggle.setArrowType(_enum(QtCore.Qt, 'ArrowType', 'RightArrow'))
    toggle.setCheckable(True)
    toggle.setSizePolicy(_enum(QtWidgets.QSizePolicy, 'Policy', 'Expanding'),
                         _enum(QtWidgets.QSizePolicy, 'Policy', 'Fixed'))
    settings_layout.addWidget(toggle)
    ui.audio_settings_button = Widget(toggle)
    settings = QtWidgets.QWidget()
    details = QtWidgets.QVBoxLayout(settings)
    details.setContentsMargins(0, 8, 0, 0)
    details.setSpacing(12)
    ui.audio_settings = Widget(settings)
    settings_layout.addWidget(settings)
    settings.hide()

    def toggle_settings(checked):
        settings.setVisible(checked)
        toggle.setArrowType(_enum(QtCore.Qt, 'ArrowType', 'DownArrow' if checked else 'RightArrow'))

    toggle.toggled.connect(toggle_settings)
    ui.preview_var = Value(False)
    ui.preview_checkbox = _checkbox('Hear speech in my speakers', ui.preview_var, ui.update_preview)
    details.addWidget(ui.preview_checkbox)
    details.addWidget(_label('Speaker', 'FieldLabel'))
    ui.speaker_var = Value()
    ui.speaker_combo = Combo(ui.speaker_var, command=ui.update_preview)
    ui.speaker_combo.widget.setAccessibleName('Speaker')
    details.addWidget(ui.speaker_combo.widget)
    ui.mix_var = Value(False)
    ui.mix_checkbox = _checkbox('Mix real microphone', ui.mix_var, ui.update_mix)
    details.addWidget(ui.mix_checkbox)
    details.addWidget(_label('Microphone', 'FieldLabel'))
    ui.mic_var = Value()
    ui.mic_combo = Combo(ui.mic_var, command=ui.update_mix)
    ui.mic_combo.widget.setAccessibleName('Microphone')
    details.addWidget(ui.mic_combo.widget)
    audio_actions = QtWidgets.QHBoxLayout()
    ui.remove_button = _button('Remove virtual mic', ui.remove_virtual)
    audio_actions.addWidget(ui.remove_button.widget)
    audio_actions.addWidget(_button('Refresh devices', ui.refresh_devices).widget)
    audio_actions.addStretch()
    details.addLayout(audio_actions)
    ui.repair_button = _button('Repair / download AI voices', ui.setup_neural)
    details.addWidget(ui.repair_button.widget)
    ui.repair_button.grid_remove()
    body_layout.addWidget(settings_card)
    body_layout.addStretch()

    footer = QtWidgets.QFrame()
    footer.setObjectName('Footer')
    footer_layout = QtWidgets.QVBoxLayout(footer)
    footer_layout.setContentsMargins(24, 12, 24, 12)
    footer_layout.setSpacing(6)
    actions = QtWidgets.QHBoxLayout()
    actions.setSpacing(10)
    ui.speak_button = _button('Speak', ui.speak, 'Speak')
    ui.speak_button.widget.setMinimumWidth(125)
    actions.addWidget(ui.speak_button.widget, 1)
    ui.stop_button = _button('Stop', ui.stop, 'Stop')
    ui.stop_button.widget.setMinimumWidth(72)
    ui.stop_button.configure(state='disabled')
    actions.addWidget(ui.stop_button.widget)
    ui.start_button = _button('Create virtual mic', ui.create_virtual)
    actions.addWidget(ui.start_button.widget)
    footer_layout.addLayout(actions)
    ui.status = Value('Ready. Create a virtual microphone to connect Discord.')
    ui.status_label = _label(variable=ui.status, wrap=True)
    ui.status_label.setAccessibleName('Speech status')
    ui.status_label.setAlignment(_enum(QtCore.Qt, 'AlignmentFlag', 'AlignTop'))
    ui.status_label.ensurePolished()
    ui.status_label.setFixedHeight(ui.status_label.fontMetrics().lineSpacing() * 2 + 3)
    footer_layout.addWidget(ui.status_label)
    footer_layout.addWidget(_label('Discord input · Discord TTS Microphone', 'ConnectionHint'))
    ui.footer = Widget(footer)
    shell.addWidget(footer)
