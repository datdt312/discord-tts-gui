"""Responsive Tk layout; speech, setup and audio routing stay in the controller."""
import tkinter as tk
from tkinter import font as tkfont, ttk


def build_ui(ui, bind_text_shortcuts, engine_choices):
    """Build a scrollable editor and settings with persistent speech controls."""
    root = ui.root
    style = ttk.Style(root)
    if 'clam' in style.theme_names():
        style.theme_use('clam')
    background = '#f5f7fb'
    style.configure('TFrame', background=background)
    style.configure('TLabel', background=background, foreground='#172033')
    style.configure('TLabelframe', background=background)
    style.configure('TLabelframe.Label', background=background, foreground='#172033')
    style.configure('TCheckbutton', background=background)
    style.configure('Header.TLabel', font=('Sans', 18, 'bold'))
    style.configure('Sub.TLabel', foreground='#526174')
    style.configure('TButton', padding=(12, 8))
    style.configure('TCombobox', padding=4)
    style.configure('Primary.TButton', background='#2563eb', foreground='white',
                    padding=(16, 10), font=('Sans', 10, 'bold'))
    style.map('Primary.TButton', background=[('disabled', '#cbd5e1'),
                                           ('pressed', '#1e40af'), ('active', '#1d4ed8')],
              foreground=[('disabled', '#526174')])

    outer = ttk.Frame(root, padding=16)
    outer.pack(fill='both', expand=True)
    outer.columnconfigure(0, weight=1)
    outer.rowconfigure(0, weight=1)

    viewport = ttk.Frame(outer)
    viewport.grid(row=0, column=0, sticky='nsew')
    viewport.columnconfigure(0, weight=1)
    viewport.rowconfigure(0, weight=1)
    ui.body_canvas = tk.Canvas(viewport, width=1, height=1, background=background,
                               borderwidth=0, highlightthickness=0, yscrollincrement=24)
    ui.body_canvas.grid(row=0, column=0, sticky='nsew')
    body_scroll = ttk.Scrollbar(viewport, orient='vertical', command=ui.body_canvas.yview)
    body_scroll.grid(row=0, column=1, sticky='ns')
    ui.body_canvas.configure(yscrollcommand=body_scroll.set)
    body = ttk.Frame(ui.body_canvas, padding=(0, 0, 12, 8))
    body.columnconfigure(0, weight=1)
    body_window = ui.body_canvas.create_window((0, 0), window=body, anchor='nw')
    wrapping_labels = []

    ttk.Label(body, text='Discord TTS', style='Header.TLabel').grid(
        row=0, column=0, sticky='w')
    subtitle = ttk.Label(body, text='Turn your text into speech in Discord.',
                         style='Sub.TLabel', width=1)
    subtitle.grid(row=1, column=0, sticky='ew', pady=(2, 14))
    wrapping_labels.append(subtitle)
    ttk.Label(body, text='Text to speak').grid(row=2, column=0, sticky='w')
    editor = ttk.Frame(body)
    editor.grid(row=3, column=0, sticky='ew', pady=(6, 14))
    editor.columnconfigure(0, weight=1)
    ui.text = tk.Text(editor, width=1, height=7, wrap='word', font=('Sans', 12),
                      undo=True, relief='solid', borderwidth=1,
                      highlightthickness=1, highlightbackground='#cbd5e1',
                      highlightcolor='#2563eb', padx=9, pady=8)
    ui.text.grid(row=0, column=0, sticky='nsew')
    text_scroll = ttk.Scrollbar(editor, orient='vertical', command=ui.text.yview)
    text_scroll.grid(row=0, column=1, sticky='ns')
    ui.text.configure(yscrollcommand=text_scroll.set)
    bind_text_shortcuts(ui.text)
    ui.text.insert('1.0', 'Xin chào mọi người! Đây là giọng đọc từ Discord TTS trên Kubuntu.')

    engine_row = ttk.Frame(body)
    engine_row.grid(row=4, column=0, sticky='ew')
    engine_row.columnconfigure(0, weight=1)
    ttk.Label(engine_row, text='Speech engine').grid(row=0, column=0, sticky='w')
    ui.engine_var = tk.StringVar(root, value=engine_choices[0])
    ui.engine_combo = ttk.Combobox(engine_row, textvariable=ui.engine_var,
                                   values=engine_choices, state='readonly', width=1)
    ui.engine_combo.grid(row=1, column=0, sticky='ew', pady=(5, 0))
    ui.engine_combo.bind('<<ComboboxSelected>>', ui.on_engine_changed)
    ui.engine_hint = tk.StringVar(root)
    hint = ttk.Label(body, textvariable=ui.engine_hint, style='Sub.TLabel', width=1)
    hint.grid(row=5, column=0, sticky='ew', pady=(5, 6))
    wrapping_labels.append(hint)
    ui.setup_button = ttk.Button(body, text='Download offline AI voices',
                                  command=ui.setup_neural, state='disabled')
    ui.setup_button.grid(row=6, column=0, sticky='w', pady=(0, 10))
    ui.setup_button.grid_remove()

    ui.download_frame = ttk.Frame(body)
    ui.download_frame.grid(row=7, column=0, sticky='ew', pady=(0, 12))
    ui.download_frame.columnconfigure(0, weight=1)
    ui.download_label_var = tk.StringVar(root)
    download_label = ttk.Label(ui.download_frame, textvariable=ui.download_label_var, width=1)
    download_label.grid(row=0, column=0, sticky='ew')
    wrapping_labels.append(download_label)
    ui.download_bar = ttk.Progressbar(ui.download_frame, maximum=100, mode='determinate')
    ui.download_bar.grid(row=1, column=0, sticky='ew', pady=(5, 0))
    ui.download_frame.grid_remove()

    ui.voice_row = ttk.Frame(body)
    ui.voice_row.grid(row=8, column=0, sticky='ew', pady=(0, 12))
    ui.voice_row.columnconfigure(0, weight=1)
    ttk.Label(ui.voice_row, text='Language / voice').grid(row=0, column=0, sticky='w')
    ui.voice_var = tk.StringVar(root)
    ui.voice_combo = ttk.Combobox(ui.voice_row, textvariable=ui.voice_var,
                                  state='readonly', width=1)
    ui.voice_combo.grid(row=1, column=0, sticky='ew', pady=(5, 0))
    ui.voice_combo.bind('<<ComboboxSelected>>', ui.on_voice_changed)
    speed_row = ttk.Frame(body)
    speed_row.grid(row=9, column=0, sticky='ew', pady=(0, 12))
    ttk.Label(speed_row, text='Speed').grid(row=0, column=0, sticky='w', padx=(0, 10))
    ui.speed_var = tk.IntVar(root, value=155)
    ttk.Spinbox(speed_row, from_=80, to=320, increment=10, textvariable=ui.speed_var,
                width=6).grid(row=0, column=1, sticky='w')

    ui.audio_settings = ttk.LabelFrame(body, text='Audio routing', padding=12)
    ui.audio_settings.grid(row=11, column=0, sticky='ew', pady=(6, 0))
    ui.audio_settings.columnconfigure(0, weight=1)
    ui.audio_settings.grid_remove()

    def toggle_audio_settings():
        if ui.audio_settings.winfo_manager():
            ui.audio_settings.grid_remove()
            ui.audio_settings_button.configure(text='▸ Audio & settings')
        else:
            ui.audio_settings.grid()
            ui.audio_settings_button.configure(text='▾ Audio & settings')

    ui.audio_settings_button = ttk.Button(body, text='▸ Audio & settings',
                                           command=toggle_audio_settings)
    ui.audio_settings_button.grid(row=10, column=0, sticky='w')
    ui.preview_var = tk.BooleanVar(root, value=False)
    ttk.Checkbutton(ui.audio_settings, text='Hear speech in my speakers',
                    variable=ui.preview_var, command=ui.update_preview).grid(
                        row=0, column=0, sticky='w')
    ttk.Label(ui.audio_settings, text='Speaker').grid(row=1, column=0, sticky='w', pady=(6, 0))
    ui.speaker_var = tk.StringVar(root)
    ui.speaker_combo = ttk.Combobox(ui.audio_settings, textvariable=ui.speaker_var,
                                    state='readonly', width=1)
    ui.speaker_combo.grid(row=2, column=0, sticky='ew', pady=(4, 12))
    ui.speaker_combo.bind('<<ComboboxSelected>>', lambda event: ui.update_preview())
    ui.mix_var = tk.BooleanVar(root, value=False)
    ttk.Checkbutton(ui.audio_settings, text='Mix real microphone', variable=ui.mix_var,
                    command=ui.update_mix).grid(row=3, column=0, sticky='w')
    ttk.Label(ui.audio_settings, text='Microphone').grid(row=4, column=0, sticky='w', pady=(6, 0))
    ui.mic_var = tk.StringVar(root)
    ui.mic_combo = ttk.Combobox(ui.audio_settings, textvariable=ui.mic_var,
                                state='readonly', width=1)
    ui.mic_combo.grid(row=5, column=0, sticky='ew', pady=(4, 12))
    ui.mic_combo.bind('<<ComboboxSelected>>', lambda event: ui.update_mix())
    audio_actions = ttk.Frame(ui.audio_settings)
    audio_actions.grid(row=6, column=0, sticky='ew')
    ui.remove_button = ttk.Button(audio_actions, text='Remove virtual mic', command=ui.remove_virtual)
    ui.remove_button.grid(row=0, column=0, sticky='w', padx=(0, 8))
    ttk.Button(audio_actions, text='Refresh devices', command=ui.refresh_devices).grid(
        row=0, column=1, sticky='w')
    ui.repair_button = ttk.Button(ui.audio_settings, text='Repair / download AI voices',
                                   command=ui.setup_neural, state='disabled')
    ui.repair_button.grid(row=7, column=0, sticky='w', pady=(10, 0))
    ui.repair_button.grid_remove()

    ui.footer = ttk.Frame(outer)
    ui.footer.grid(row=1, column=0, sticky='ew', pady=(12, 0))
    ui.footer.columnconfigure(0, weight=1)
    ttk.Separator(ui.footer).grid(row=0, column=0, sticky='ew', pady=(0, 12))
    actions = ttk.Frame(ui.footer)
    actions.grid(row=1, column=0, sticky='ew')
    actions.columnconfigure(0, weight=1)
    ui.speak_button = ttk.Button(actions, text='Speak to Discord', style='Primary.TButton',
                                  command=ui.speak)
    ui.speak_button.grid(row=0, column=0, sticky='ew', padx=(0, 8))
    ui.stop_button = ttk.Button(actions, text='Stop', command=ui.stop)
    ui.stop_button.grid(row=0, column=1, padx=(0, 8))
    ui.start_button = ttk.Button(actions, text='Create virtual mic', command=ui.create_virtual)
    ui.start_button.grid(row=0, column=2)

    # Reserve two status lines so even verbose errors cannot grow the footer.
    line_height = tkfont.nametofont('TkDefaultFont', root=root).metrics('linespace')
    status_area = ttk.Frame(ui.footer, height=line_height * 2 + 4)
    status_area.grid(row=2, column=0, sticky='ew', pady=(9, 0))
    status_area.grid_propagate(False)
    status_area.columnconfigure(0, weight=1)
    status_area.rowconfigure(0, weight=1)
    ui.status = tk.StringVar(root, value='Ready. Create a virtual microphone to connect Discord.')
    ui.status_label = ttk.Label(status_area, textvariable=ui.status, width=1, anchor='nw')
    ui.status_label.grid(row=0, column=0, sticky='nsew')
    ui.status_label.bind('<Configure>', lambda event: ui.status_label.configure(
        wraplength=max(1, event.width)))
    ttk.Label(ui.footer, text='Discord input: Discord TTS Microphone', style='Sub.TLabel').grid(
        row=3, column=0, sticky='w', pady=(3, 0))

    def update_body_width(event):
        ui.body_canvas.itemconfigure(body_window, width=event.width)
        for label in wrapping_labels:
            label.configure(wraplength=max(1, event.width - 16))

    ui.body_canvas.bind('<Configure>', update_body_width)
    body.bind('<Configure>', lambda event: ui.body_canvas.configure(
        scrollregion=ui.body_canvas.bbox('all')))

    def scroll_body(event):
        if getattr(event, 'num', None) == 4:
            steps = -1
        elif getattr(event, 'num', None) == 5:
            steps = 1
        else:
            steps = -1 if event.delta > 0 else 1
        ui.body_canvas.yview_scroll(steps, 'units')
        return 'break'

    def reveal_focused_control(event):
        canvas = ui.body_canvas
        visible_top = canvas.canvasy(0)
        top = event.widget.winfo_rooty() - canvas.winfo_rooty() + visible_top
        bottom = top + event.widget.winfo_height()
        height = canvas.winfo_height()
        content_height = max(1, body.winfo_height())
        if top < visible_top:
            canvas.yview_moveto(max(0, top - 8) / content_height)
        elif bottom > visible_top + height:
            canvas.yview_moveto(max(0, bottom - height + 8) / content_height)

    # Bind only passive body surfaces. Text, selectors and numeric controls
    # retain their own wheel behavior; no application-wide binding is added.
    def bind_body_scrolling(widget):
        if isinstance(widget, (ttk.Frame, ttk.LabelFrame, ttk.Label, tk.Canvas)):
            for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                widget.bind(sequence, scroll_body)
        if isinstance(widget, (tk.Text, ttk.Combobox, ttk.Spinbox,
                               ttk.Button, ttk.Checkbutton)):
            widget.bind('<FocusIn>', reveal_focused_control, add='+')
        for child in widget.winfo_children():
            bind_body_scrolling(child)

    bind_body_scrolling(ui.body_canvas)
