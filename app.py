#!/usr/bin/env python3
"""Discord TTS GUI: online/offline speech into a virtual microphone."""
import asyncio
import json
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import webbrowser
from pathlib import Path
try:
    import tkinter as tk
    from tkinter import messagebox
    TclError = tk.TclError
except ImportError:
    # The Qt frontend does not require a separate Tk installation on macOS.
    tk = None
    class TclError(Exception):
        pass
    from qt_ui import dialogs as messagebox

from media_tools import current_platform, ffmpeg_executable, espeak_executable, subprocess_options

from neural_playback import play_neural_audio

APP = 'Discord TTS GUI'
SINK = 'discord_tts_sink'
SOURCE = 'discord_tts_mic'
ONLINE_ENGINE = 'Microsoft Edge (online)'
NEURAL_ENGINE = 'VieNeu-TTS v3 Turbo (offline AI)'
OFFLINE_ENGINE = 'eSpeak NG (offline)'
ONLINE_VOICES = {
    'Tiếng Việt — Hoài My (nữ)': 'vi-VN-HoaiMyNeural',
    'Tiếng Việt — Nam Minh (nam)': 'vi-VN-NamMinhNeural',
    'English — Jenny (female)': 'en-US-JennyNeural',
    'English — Guy (male)': 'en-US-GuyNeural',
}


def use_app_venv():
    """Use installed dependencies even if an old KDE launcher calls system Python."""
    if getattr(sys, 'frozen', False) or current_platform() != 'linux':
        return
    script = Path(__file__).resolve()
    environment = script.parent / '.venv'
    python = environment / 'bin/python'
    if (python.is_file() and (environment / 'pyvenv.cfg').is_file()
            and Path(sys.prefix).resolve() != environment.resolve()):
        # Keep the venv executable path: resolving its symlink selects system Python.
        os.execv(str(python), [str(python), str(script), *sys.argv[1:]])


def restore_display():
    """Recover KDE's XWayland display when a menu launch omits DISPLAY."""
    if os.environ.get('DISPLAY') or shutil.which('xauth') is None:
        return
    authority = os.environ.get('XAUTHORITY')
    if authority:
        candidates = [Path(authority)]
    else:
        runtime = os.environ.get('XDG_RUNTIME_DIR')
        candidates = sorted(Path(runtime).glob('xauth_*')) if runtime else []
        candidates.append(Path.home() / '.Xauthority')
    displays = set()
    for path in candidates:
        try:
            if not path.is_file() or path.stat().st_uid != os.getuid():
                continue
            # -i avoids creating a lock beside KDE's session authority file.
            result = command(['xauth', '-i', '-f', str(path), 'list'],
                             check=False, timeout=2)
            if result.returncode:
                continue
            # Read only display addresses; never log authentication cookies.
            for line in result.stdout.splitlines():
                address = line.split()[0] if line.split() else ''
                host, separator, number = address.rpartition(':')
                if (separator and number.isdigit()
                        and host in (socket.gethostname() + '/unix', 'unix', '#ffff##')):
                    displays.add((':' + number, str(path)))
        except (OSError, subprocess.TimeoutExpired):
            continue
    # Multiple sessions require an explicit DISPLAY rather than a guess.
    if len(displays) == 1:
        os.environ['DISPLAY'], os.environ['XAUTHORITY'] = displays.pop()


def command(args, *, check=True, **kw):
    options = subprocess_options()
    options.update(kw)
    return subprocess.run(args, capture_output=True, text=True, check=check, **options)


def pulse_list(kind):
    result = command(['pactl', '-f', 'json', 'list', kind])
    return json.loads(result.stdout)


def shorten_error(error):
    if isinstance(error, subprocess.CalledProcessError):
        return (error.stderr or error.stdout or str(error)).strip()
    return str(error)


async def receive_online_audio(text, voice, speed, write_audio, events=None):
    """Deliver MP3 chunks, retrying only before any audio has been delivered."""
    try:
        import edge_tts
    except ImportError as error:
        raise RuntimeError('Cannot import online TTS using ' + sys.executable + ': '
                           + str(error) + '\nRun ./install.sh, close existing app windows, '
                           'and reopen using the installed .venv/bin/python.') from error
    ffmpeg_executable()
    rate = f'{round((speed / 155 - 1) * 100):+d}%'
    received_audio = False
    remaining = 60

    async def remote_wait(awaitable):
        # Bound network waits and retry delays, but don't count time spent playing
        # a long message when the decoder's input pipe applies backpressure.
        nonlocal remaining
        started = asyncio.get_running_loop().time()
        try:
            return await asyncio.wait_for(awaitable, timeout=max(0, remaining))
        finally:
            remaining -= asyncio.get_running_loop().time() - started

    try:
        for attempt in range(3):
            speech = edge_tts.Communicate(text, voice, rate=rate,
                                         connect_timeout=10, receive_timeout=30)
            stream = speech.stream()
            try:
                while True:
                    try:
                        chunk = await remote_wait(anext(stream))
                    except StopAsyncIteration:
                        break
                    if chunk['type'] == 'audio' and chunk['data']:
                        received_audio = True
                        await write_audio(chunk['data'])
                if not received_audio:
                    raise edge_tts.exceptions.NoAudioReceived('Empty audio stream')
                return
            except edge_tts.exceptions.NoAudioReceived:
                if received_audio:
                    raise RuntimeError('Online speech was interrupted after audio started. '
                                       'The message was not repeated. Try again later.')
                if attempt == 2:
                    raise
                if events is not None:
                    events.put(('status', f'No audio returned; retrying this message '
                                f'(attempt {attempt + 2} of 3)...'))
                await remote_wait(asyncio.sleep(attempt + 1))
            finally:
                await stream.aclose()
    except edge_tts.exceptions.NoAudioReceived as error:
        raise RuntimeError(
            f'Microsoft returned no audio for {voice} after 3 attempts. '
            'These are retries for this message, not a usage limit. '
            'You can press Speak again; the app has no 3-use quota. '
            'This response does not confirm a rate limit: the voice or service may be unavailable. '
            'Select another voice under Language / voice, try later, or download '
            'VieNeu-TTS offline AI voices to avoid depending on this service.') from error
    except asyncio.TimeoutError as error:
        raise RuntimeError('Online TTS request timed out. The service did not finish in time. '
                           'Try a shorter message, another voice, or try again later.') from error
    except Exception as error:
        detail = shorten_error(error) or type(error).__name__
        raise RuntimeError('Online TTS failed: ' + detail) from error


async def play_online_speech(text, voice, speed, cancel_event, events):
    """Stream MP3 through FFmpeg to a low-latency PulseAudio player."""
    if cancel_event.is_set():
        return
    processes = []
    tasks = []
    job = None
    stopped = None
    with tempfile.TemporaryFile() as decoder_errors, tempfile.TemporaryFile() as player_errors:
        decoder = None

        async def transfer():
            started = False

            async def write_audio(data):
                nonlocal started
                decoder.stdin.write(data)
                await decoder.stdin.drain()
                if not started:
                    events.put(('status', 'Receiving and playing speech to Discord...'))
                    started = True

            await receive_online_audio(text, voice, speed, write_audio, events)
            decoder.stdin.close()
            await decoder.stdin.wait_closed()

        async def check_process(process, label, errors):
            if await process.wait() != 0:
                errors.seek(0)
                detail = errors.read().decode(errors='replace').strip()
                raise RuntimeError(label + ' failed: ' + (detail or str(process.returncode)))

        async def watch_stop():
            while not cancel_event.is_set():
                await asyncio.sleep(0.02)

        try:
            read_fd, write_fd = os.pipe()
            try:
                decoder = await asyncio.create_subprocess_exec(
                    ffmpeg_executable(), '-nostdin', '-hide_banner', '-loglevel', 'error',
                    '-f', 'mp3', '-probesize', '32', '-analyzeduration', '0',
                    '-i', 'pipe:0', '-ac', '1', '-ar', '24000', '-c:a', 'pcm_s16le',
                    '-f', 's16le', '-flush_packets', '1', 'pipe:1',
                    stdin=asyncio.subprocess.PIPE, stdout=write_fd, stderr=decoder_errors)
                processes.append(decoder)
                player = await asyncio.create_subprocess_exec(
                    'paplay', '--device', SINK, '--raw', '--format=s16le',
                    '--rate=24000', '--channels=1', '--latency-msec=40',
                    stdin=read_fd, stdout=asyncio.subprocess.DEVNULL, stderr=player_errors)
                processes.append(player)
            finally:
                os.close(read_fd)
                os.close(write_fd)
            if cancel_event.is_set():
                return
            tasks = [asyncio.create_task(transfer()),
                     asyncio.create_task(check_process(decoder, 'FFmpeg decoder', decoder_errors)),
                     asyncio.create_task(check_process(player, 'Audio playback', player_errors))]
            job = asyncio.gather(*tasks)
            stopped = asyncio.create_task(watch_stop())
            await asyncio.wait((job, stopped), return_when=asyncio.FIRST_COMPLETED)
            if not cancel_event.is_set():
                await job
        finally:
            # Stop must interrupt remote waits, full pipes and playback alike.
            for task in tasks:
                task.cancel()
            if stopped is not None:
                stopped.cancel()
            for process in processes:
                if process.returncode is None:
                    try:
                        process.terminate()
                    except ProcessLookupError:
                        pass
            if decoder is not None and decoder.stdin is not None:
                decoder.stdin.close()
            await asyncio.gather(*tasks, *([stopped] if stopped else []), return_exceptions=True)
            if job is not None:
                await asyncio.gather(job, return_exceptions=True)
            for process in processes:
                try:
                    await asyncio.wait_for(process.wait(), timeout=2)
                except asyncio.TimeoutError:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                    await process.wait()


def synthesize_speech(text, voice, speed, path, engine, cancel_event=None):
    """Write PCM WAV for offline playback or file-based synthesis."""
    if engine == OFFLINE_ENGINE:
        args = [espeak_executable(), '-v', voice, '-s', str(speed), '-w', path, '--stdin']
        if cancel_event is None:
            subprocess.run(args, input=text, encoding='utf-8', capture_output=True,
                           check=True, timeout=60, **subprocess_options())
            return
        if cancel_event.is_set():
            return
        process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, encoding='utf-8', **subprocess_options())
        deadline = time.monotonic() + 60
        pending_input = text
        try:
            while not cancel_event.is_set():
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(args, 60)
                try:
                    output, error = process.communicate(pending_input, timeout=0.05)
                    if process.returncode:
                        raise subprocess.CalledProcessError(process.returncode, args, output, error)
                    return
                except subprocess.TimeoutExpired:
                    pending_input = None
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.communicate(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()
        return
    if engine != ONLINE_ENGINE:
        raise ValueError('Unknown speech engine: ' + engine)
    with tempfile.TemporaryDirectory(prefix='discord_tts_online_') as directory:
        mp3 = str(Path(directory) / 'speech.mp3')

        async def download():
            with open(mp3, 'wb') as output:
                async def write_audio(data):
                    output.write(data)
                await receive_online_audio(text, voice, speed, write_audio)

        asyncio.run(download())

        # Edge returns MP3; paplay expects a supported PCM audio container.
        try:
            command([ffmpeg_executable(), '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                     '-i', mp3, '-ac', '1', '-ar', '48000', '-c:a', 'pcm_s16le', path],
                    timeout=30)
        except Exception as error:
            detail = shorten_error(error) or type(error).__name__
            raise RuntimeError('FFmpeg could not decode online speech: ' + detail) from error


def bind_text_shortcuts(widget):
    """Use familiar select-all and replace-selection paste behavior on Linux."""
    def select_all(event=None):
        widget.tag_add('sel', '1.0', 'end-1c')
        widget.mark_set('insert', 'end-1c')
        widget.see('insert')
        return 'break'

    def paste(event=None):
        # Read the clipboard first: an unavailable clipboard must not delete
        # the highlighted text. <<Paste>> also covers Tk's virtual paste action.
        try:
            value = widget.clipboard_get()
        except TclError:
            return 'break'
        if not value:
            return 'break'
        selection = widget.tag_ranges('sel')
        widget.edit_separator()
        if selection:
            widget.mark_set('insert', selection[0])
            # Tk replace keeps deletion + insertion as one undoable operation.
            widget.replace(selection[0], selection[1], value)
        else:
            widget.insert('insert', value)
        widget.tag_remove('sel', '1.0', 'end')
        widget.edit_separator()
        widget.see('insert')
        # Prevent the Text class binding from inserting the clipboard again.
        return 'break'

    for sequence in ('<Control-a>', '<Control-A>', '<<SelectAll>>'):
        widget.bind(sequence, select_all)
    widget.bind('<<Paste>>', paste)


class RequestEvents:
    """Keep a cancelled worker's late messages out of the current UI state."""
    def __init__(self, events, generation):
        self.events = events
        self.generation = generation

    def put(self, item):
        self.events.put((*item, self.generation))


class DiscordTTS:
    def __init__(self, root):
        self.root = root
        self.root.title(APP)
        self.root.geometry('820x720')
        self.root.minsize(560, 480)
        self.platform = current_platform()
        self.portable_audio = None
        self.active_output = None
        self.active_output_label = None
        self.target_devices = {}
        if self.platform in ('win32', 'darwin'):
            from portable_audio import PortableAudio
            self.portable_audio = PortableAudio(system='Windows' if self.platform == 'win32' else 'Darwin')
        self.events = queue.Queue()
        self.modules = []
        self.sink_active = False
        self.playing = False
        self.proc = None
        self.cancel_event = None
        self.preparing = False
        from neural_backend import NeuralEngine
        self.neural = NeuralEngine()
        self.worker_thread = None
        self._speech_generation = 0
        self.pending_speech = None
        self._restart_scheduled = False
        self.neural_ready = bool(self.neural.voices())
        self.closing = False
        self.removing = False
        self.preview_module = None
        self.mic_module = None
        self.speaker_names = {}
        self.mic_names = {}
        self.voice_names = {}
        self.build()
        self.refresh_devices()
        self.load_voices()
        self.root.after(100, self.poll)
        self.root.protocol('WM_DELETE_WINDOW', self.close)

    def build(self):
        if hasattr(self.root, 'window'):
            from qt_ui import build_ui, dialogs
            global messagebox
            messagebox = dialogs
        else:
            from desktop_ui import build_ui
        build_ui(self, bind_text_shortcuts, (NEURAL_ENGINE, ONLINE_ENGINE, OFFLINE_ENGINE))

    def note(self, message):
        compact = ' '.join(str(message).split())
        self.status.set(compact if len(compact) <= 160 else compact[:157] + '...')

    def poll(self):
        while True:
            try:
                item = self.events.get_nowait()
                event, payload = item[:2]
                if len(item) == 3 and item[2] != getattr(self, '_speech_generation', 0):
                    continue
            except queue.Empty:
                break
            if event == 'done':
                if getattr(self, 'preparing', False):
                    self.download_stage(payload, finished=True)
                self.playing = False
                self.preparing = False
                self.proc = None
                self.update_setup_button()
                self.note(payload)
            elif event == 'error':
                if getattr(self, 'preparing', False):
                    self.download_stage('Tải/cài đặt chưa hoàn tất: ' + payload, finished=True)
                self.playing = False
                self.preparing = False
                self.proc = None
                self.update_setup_button()
                self.note('Error: ' + payload)
                messagebox.showerror(APP, payload)
            elif event == 'neural_ready':
                self.neural_ready = True
                self.download_stage('Đã tải và kiểm tra offline — sẵn sàng.',
                                    finished=True, success=True)
                self.playing = False
                self.preparing = False
                if self.engine_var.get() == NEURAL_ENGINE:
                    self.load_voices()
                self.update_setup_button()
                self.note('Offline AI voices ready. Select a voice and press Speak.')
            elif event == 'status':
                self.note(payload)
                if getattr(self, 'preparing', False):
                    self.download_stage(payload)
            elif event == 'download_progress' and getattr(self, 'preparing', False):
                self.show_download_progress(payload)
        self.update_action_buttons()
        self.root.after(100, self.poll)

    def refresh_devices(self):
        if getattr(self, 'portable_audio', None) is not None:
            self.refresh_portable_devices()
            return
        try:
            sinks = pulse_list('sinks')
            sources = pulse_list('sources')
            self.speaker_names = {f"{x.get('description', x['name'])} ({x['name']})": x['name']
                                  for x in sinks if x['name'] != SINK}
            self.mic_names = {f"{x.get('description', x['name'])} ({x['name']})": x['name']
                              for x in sources if not x['name'].endswith('.monitor') and x['name'] != SOURCE}
            self.speaker_combo['values'] = list(self.speaker_names)
            self.mic_combo['values'] = list(self.mic_names)
            if self.speaker_var.get() not in self.speaker_names and self.speaker_names:
                self.speaker_var.set(next(iter(self.speaker_names)))
            if self.mic_var.get() not in self.mic_names and self.mic_names:
                self.mic_var.set(next(iter(self.mic_names)))
        except Exception as error:
            self.note('Audio not available: ' + shorten_error(error))

    def refresh_portable_devices(self):
        try:
            self.target_devices = self.portable_audio.devices()
            self.target_combo['values'] = list(self.target_devices)
            self.speaker_names = dict(self.target_devices)
            self.speaker_combo['values'] = list(self.speaker_names)
            if self.target_var.get() not in self.target_devices:
                self.target_var.set(self.portable_audio.suggested_device(self.target_devices) or '')
            if self.speaker_var.get() not in self.speaker_names:
                self.speaker_var.set('')
            if self.sink_active and (
                    self.target_devices.get(self.active_output_label) != self.active_output
                    or self.target_var.get() != self.active_output_label):
                if not self.preparing:
                    self.stop()
                self.sink_active = False
                self.active_output = None
                self.active_output_label = None
                self.note('Selected audio device disconnected. Refresh and connect again.')
            self.update_action_buttons()
        except Exception as error:
            self.note('Audio not available: ' + shorten_error(error))

    def open_driver_help(self):
        url = ('https://vb-audio.com/Cable/' if self.platform == 'win32'
               else 'https://existential.audio/blackhole/')
        webbrowser.open(url)

    def on_output_changed(self):
        restart = self.playing and not self.preparing
        if not self.preparing:
            self.stop()
        self.sink_active = False
        self.active_output = None
        self.active_output_label = None
        self.update_action_buttons()
        if restart:
            self.create_virtual()
            if self.sink_active:
                self.speak()
        else:
            self.note('Output selected. Press Connect audio before speaking.')

    def load_voices(self):
        self.voice_names = {}
        self.voice_var.set('')
        self.voice_combo['values'] = []
        self.update_setup_button()
        if self.engine_var.get() == ONLINE_ENGINE:
            self.voice_names = dict(ONLINE_VOICES)
            self.voice_combo['values'] = list(self.voice_names)
            self.voice_var.set(next(iter(self.voice_names)))
            self.engine_hint.set('Online · Microsoft voices · requires internet')
            return
        if self.engine_var.get() == NEURAL_ENGINE:
            self.voice_names = self.neural.voices()
            self.neural_ready = bool(self.voice_names)
            self.update_setup_button()
            self.voice_combo['values'] = list(self.voice_names)
            if self.voice_names:
                self.voice_var.set(next(iter(self.voice_names)))
                self.engine_hint.set('Offline AI · VieNeu v3 Turbo · 48 kHz · ready')
            else:
                self.engine_hint.set('Download once: ~566 MB of models; allow 2–3 GB for setup.')
            return
        self.engine_hint.set('Offline: eSpeak NG. Vietnamese speech can sound robotic and unclear.')
        try:
            lines = command([espeak_executable(), '--voices']).stdout.splitlines()[1:]
            voices = []
            for line in lines:
                parts = line.split()
                if len(parts) >= 4:
                    lang = parts[1]
                    name = parts[3]
                    entry = f'{lang} — {name}'
                    self.voice_names[entry] = lang
                    voices.append(entry)
            self.voice_combo['values'] = voices
            preferred = next((x for x in voices if x.startswith('vi ')), None)
            self.voice_var.set(preferred or next((x for x in voices if x.startswith('en ')), voices[0] if voices else ''))
        except Exception as error:
            self.note('Install espeak-ng: ' + shorten_error(error))

    def _worker_alive(self):
        worker = getattr(self, 'worker_thread', None)
        return worker is not None and worker.is_alive()

    def update_setup_button(self):
        neural_selected = self.engine_var.get() == NEURAL_ENGINE
        busy = (getattr(self, 'playing', False) or self._worker_alive()
                or getattr(self, 'closing', False) or getattr(self, 'removing', False))
        button = getattr(self, 'setup_button', None)
        if button is not None:
            if neural_selected and not getattr(self, 'neural_ready', False):
                button.grid()
            else:
                button.grid_remove()
            button.configure(state='normal' if neural_selected and not busy else 'disabled')
        repair = getattr(self, 'repair_button', None)
        if repair is not None:
            if neural_selected:
                repair.grid()
            else:
                repair.grid_remove()
            repair.configure(state='normal' if neural_selected and not busy else 'disabled')

    def update_action_buttons(self):
        blocked = (getattr(self, 'closing', False) or getattr(self, 'removing', False)
                   or getattr(self, 'preparing', False))
        active = (getattr(self, 'playing', False) or self._worker_alive()
                  or getattr(self, 'pending_speech', None) is not None)
        speak = getattr(self, 'speak_button', None)
        if speak is not None:
            speak.configure(text='Restart speech' if active and not blocked else 'Speak',
                            state='disabled' if blocked else 'normal')
        stop = getattr(self, 'stop_button', None)
        if stop is not None:
            stop.configure(state='normal' if active else 'disabled')
        create = getattr(self, 'start_button', None)
        if create is not None:
            ready = getattr(self, 'sink_active', False)
            portable = getattr(self, 'portable_audio', None) is not None
            create.configure(text=('Connected' if ready else 'Connect audio') if portable
                             else ('Mic ready' if ready else 'Create virtual mic'),
                             state='disabled' if ready or blocked else 'normal')
        self.update_setup_button()

    def _show_download_widgets(self):
        frame = getattr(self, 'download_frame', None)
        if frame is not None:
            frame.grid()

    def download_stage(self, text, *, finished=False, success=False):
        bar = getattr(self, 'download_bar', None)
        if bar is None:
            return
        bar.stop()
        if finished:
            frame = getattr(self, 'download_frame', None)
            if frame is not None:
                frame.grid_remove()
            self.download_label_var.set('')
            bar.configure(mode='determinate', value=100 if success else 0)
        else:
            self._show_download_widgets()
            self.download_label_var.set(' '.join(str(text).split())[:160])
            bar.configure(mode='indeterminate', value=0)
            bar.start(15)

    def show_download_progress(self, progress):
        bar = getattr(self, 'download_bar', None)
        if bar is None:
            return
        self._show_download_widgets()
        downloaded = max(0, int(progress.get('downloaded', 0)))
        total = progress.get('total')
        filename = str(progress.get('filename', 'model'))

        def size(value):
            for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
                if value < 1000 or unit == 'TB':
                    return f'{value:.1f} {unit}'
                value /= 1000

        bar.stop()
        if total is not None and total > 0:
            percentage = min(100, 100 * downloaded / total)
            bar.configure(mode='determinate', value=percentage)
            prefix = 'Đã có trong cache' if progress.get('cached') else 'Tải file'
            label = (f'{prefix} {filename}: {percentage:.1f}% '
                     f'({size(downloaded)} / {size(total)})')
        else:
            bar.configure(mode='indeterminate', value=0)
            bar.start(15)
            label = f'Tải file {filename}: {size(downloaded)} — chưa biết tổng dung lượng'
        self.download_label_var.set(label)

    def setup_neural(self):
        if self.playing or self.preparing or self._worker_alive() or self.closing or self.removing:
            self.note('Wait for the current operation to finish, or press Stop.')
            return
        self.playing = True
        self.preparing = True
        self.cancel_event = threading.Event()
        self.update_setup_button()
        self.note('Preparing offline AI runtime and downloading models...')
        self.download_stage('Chuẩn bị runtime và tải các file model...')
        self.worker_thread = threading.Thread(target=self.setup_neural_worker,
                                              args=(self.cancel_event,), daemon=True)
        self.worker_thread.start()

    def setup_neural_worker(self, cancel_event):
        try:
            voices = self.neural.prepare(cancel_event,
                                          lambda status: self.events.put(('status', status)),
                                          on_progress=lambda data: self.events.put(('download_progress', data)))
            self.events.put(('done', 'Stopped.') if cancel_event.is_set()
                            else ('neural_ready', voices))
        except Exception as error:
            self.events.put(('done', 'Stopped.') if cancel_event.is_set()
                            else ('error', 'Offline AI setup failed: ' + shorten_error(error)))

    def load_module(self, *args):
        result = command(['pactl', 'load-module', *args])
        module_id = int(result.stdout.strip())
        self.modules.append(module_id)
        return module_id

    def unload_module(self, module_id):
        if module_id is None:
            return
        command(['pactl', 'unload-module', str(module_id)], check=False)
        if module_id in self.modules:
            self.modules.remove(module_id)

    def create_virtual(self):
        if getattr(self, 'portable_audio', None) is not None:
            device = self.target_devices.get(self.target_var.get())
            if device is None:
                messagebox.showwarning(APP, 'Select an audio output first. Install VB-CABLE '
                                       'on Windows or BlackHole on macOS, then refresh devices.')
                return
            try:
                self.portable_audio.validate_device(device)
                self.active_output = device
                self.active_output_label = self.target_var.get()
                self.sink_active = True
                label = self.active_output_label.casefold()
                hint = ('Discord input: CABLE Output' if self.platform == 'win32' and 'cable input' in label
                        else 'Discord input: ' + self.active_output_label if 'blackhole' in label
                        else 'Discord input: select the matching virtual input for this output')
                self.connection_hint_var.set(hint)
                self.note('Audio connected. ' + hint + '. Press Speak.')
                self.update_action_buttons()
            except Exception as error:
                self.sink_active = False
                self.active_output = None
                self.active_output_label = None
                messagebox.showerror(APP, 'Could not connect audio: ' + shorten_error(error))
            return
        if self.sink_active:
            self.note('Virtual mic already active. Select Discord TTS Microphone in Discord.')
            return
        try:
            # Do not steal the system default microphone or speaker.
            existing_sinks = [x['name'] for x in pulse_list('sinks')]
            existing_sources = [x['name'] for x in pulse_list('sources')]
            if SINK in existing_sinks or SOURCE in existing_sources:
                raise RuntimeError('A previous Discord TTS device exists. Remove it using pactl or restart the audio session.')
            self.load_module('module-null-sink', f'sink_name={SINK}',
                             'sink_properties=device.description=Discord_TTS_Output', 'rate=48000', 'channels=2')
            self.load_module('module-remap-source', f'master={SINK}.monitor', f'source_name={SOURCE}',
                             'source_properties=device.description=Discord_TTS_Microphone')
            self.sink_active = True
            self.update_preview()
            self.update_mix()
            self.note('Virtual mic ready: select Discord_TTS_Microphone in Discord Input Device.')
        except Exception as error:
            for module_id in reversed(self.modules[:]):
                self.unload_module(module_id)
            self.sink_active = False
            messagebox.showerror(APP, 'Could not create virtual microphone:\n' + shorten_error(error))

    def update_preview(self):
        if getattr(self, 'portable_audio', None) is not None:
            if self.playing and not self.preparing:
                self.speak()
            return
        self.unload_module(self.preview_module)
        self.preview_module = None
        if not self.sink_active or not self.preview_var.get():
            return
        sink = self.speaker_names.get(self.speaker_var.get())
        if not sink:
            return
        try:
            self.preview_module = self.load_module('module-loopback', f'source={SINK}.monitor',
                                                   f'sink={sink}', 'latency_msec=60')
        except Exception as error:
            self.note('Preview error: ' + shorten_error(error))

    def update_mix(self):
        if getattr(self, 'portable_audio', None) is not None:
            self.mix_var.set(False)
            self.note('Use an external audio mixer to combine your real microphone with TTS.')
            return
        self.unload_module(self.mic_module)
        self.mic_module = None
        if not self.sink_active or not self.mix_var.get():
            return
        source = self.mic_names.get(self.mic_var.get())
        if not source:
            self.note('Select a physical microphone first.')
            return
        try:
            self.mic_module = self.load_module('module-loopback', f'source={source}',
                                               f'sink={SINK}', 'latency_msec=50')
        except Exception as error:
            self.note('Mix error: ' + shorten_error(error))

    def on_engine_changed(self, event=None):
        restart = self.playing and not self.preparing
        if restart:
            self.stop()
        self.load_voices()
        if restart:
            self.speak()

    def on_voice_changed(self, event=None):
        if self.playing and not self.preparing:
            self.speak()

    def speak(self):
        if self.closing or self.removing:
            return
        if self.preparing:
            self.note('Wait for model setup to finish, or press Stop.')
            return
        if not self.sink_active:
            messagebox.showwarning(APP, 'Select an output and press Connect audio first.'
                                   if getattr(self, 'portable_audio', None) is not None
                                   else 'Create the virtual microphone first.')
            return
        text = self.text.get('1.0', 'end').strip()
        if not text:
            self.stop()
            return
        voice = self.voice_names.get(self.voice_var.get())
        if not voice:
            self.stop()
            messagebox.showwarning(APP, 'Download offline AI voices first.'
                                   if self.engine_var.get() == NEURAL_ENGINE
                                   else 'Select an available voice first.')
            return
        try:
            speed = max(80, min(320, int(self.speed_var.get())))
        except (ValueError, TclError):
            messagebox.showwarning(APP, 'Enter a speed between 80 and 320.')
            return
        self._speech_generation = getattr(self, '_speech_generation', 0) + 1
        self.pending_speech = (text, voice, speed, self.engine_var.get())
        self.playing = True
        if self._worker_alive():
            self._cancel_current()
            self.note('Stopping previous speech; preparing the latest text...')
            self._schedule_restart()
            self.update_action_buttons()
            return
        self.start_pending_speech()

    def start_pending_speech(self):
        self._restart_scheduled = False
        if (self.closing or self.removing
                or getattr(self, 'pending_speech', None) is None):
            return
        if self._worker_alive():
            self._schedule_restart()
            return
        request = self.pending_speech
        self.pending_speech = None
        self.proc = None
        self.cancel_event = threading.Event()
        self.playing = True
        self.update_action_buttons()
        self.note('Connecting to online voice...' if request[3] == ONLINE_ENGINE
                  else 'Synthesizing and sending audio to Discord...')
        events = RequestEvents(self.events, self._speech_generation)
        self.worker_thread = threading.Thread(
            target=self.play_worker, args=(*request, self.cancel_event, events), daemon=True)
        self.worker_thread.start()

    def _schedule_restart(self):
        if not getattr(self, '_restart_scheduled', False):
            self._restart_scheduled = True
            self.root.after(20, self.start_pending_speech)

    def play_worker(self, text, voice, speed, engine, cancel_event=None, events=None):
        events = events if events is not None else self.events
        path = None
        try:
            if getattr(self, 'portable_audio', None) is not None:
                self.play_portable_worker(text, voice, speed, engine, cancel_event, events)
                return
            if engine == NEURAL_ENGINE:
                cancellation = cancel_event if cancel_event is not None else threading.Event()
                play_neural_audio(self.neural, text, voice, speed, SINK, cancellation,
                                  lambda status: events.put(('status', status)),
                                  lambda process: setattr(self, 'proc', process))
                events.put(('done', 'Stopped.' if cancellation.is_set()
                                 else 'Finished speaking. Ready for next message.'))
                return
            if engine == ONLINE_ENGINE:
                cancellation = cancel_event if cancel_event is not None else threading.Event()
                asyncio.run(play_online_speech(text, voice, speed, cancellation, events))
                events.put(('done', 'Stopped.' if cancellation.is_set()
                                 else 'Finished speaking. Ready for next message.'))
                return
            with tempfile.NamedTemporaryFile(prefix='discord_tts_', suffix='.wav', delete=False) as tmp:
                path = tmp.name
            synthesize_speech(text, voice, speed, path, engine, cancel_event)
            if cancel_event is not None and cancel_event.is_set():
                events.put(('done', 'Stopped.'))
                return
            self.proc = subprocess.Popen(['paplay', '--device', SINK, path],
                                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            if cancel_event is not None and cancel_event.is_set():
                self.proc.terminate()
            _, error = self.proc.communicate()
            if cancel_event is not None and cancel_event.is_set():
                events.put(('done', 'Stopped.'))
                return
            if self.proc.returncode != 0:
                raise RuntimeError(error.decode(errors='replace'))
            events.put(('done', 'Finished speaking. Ready for next message.'))
        except Exception as error:
            if cancel_event is not None and cancel_event.is_set():
                events.put(('done', 'Stopped.'))
            else:
                events.put(('error', shorten_error(error)))
        finally:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass

    def play_portable_worker(self, text, voice, speed, engine, cancel_event, events):
        from portable_playback import play_online, play_neural, play_file
        cancel = cancel_event if cancel_event is not None else threading.Event()
        device = self.active_output
        preview = self.speaker_names.get(self.speaker_var.get()) if self.preview_var.get() else None
        if self.preview_var.get() and preview is None:
            raise RuntimeError('Select a speaker for audio preview first.')
        options = dict(device=device, preview_device=preview)
        if engine == NEURAL_ENGINE:
            play_neural(self.neural, text, voice, speed, cancel, events, self.portable_audio, **options)
        elif engine == ONLINE_ENGINE:
            asyncio.run(play_online(text, voice, speed, cancel, events,
                                    receive_online_audio, self.portable_audio, **options))
        else:
            with tempfile.TemporaryDirectory(prefix='discord_tts_') as directory:
                path = str(Path(directory) / 'speech.wav')
                synthesize_speech(text, voice, speed, path, engine, cancel)
                if not cancel.is_set():
                    play_file(path, cancel, events, self.portable_audio, **options)
        events.put(('done', 'Stopped.' if cancel.is_set()
                    else 'Finished speaking. Ready for next message.'))

    def _cancel_current(self):
        cancel = getattr(self, 'cancel_event', None)
        already_cancelled = cancel is not None and cancel.is_set()
        if cancel is not None:
            cancel.set()
        process = getattr(self, 'proc', None)
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
        portable = getattr(self, 'portable_audio', None)
        if portable is not None:
            portable.stop()
        neural = getattr(self, 'neural', None)
        if neural is not None and not already_cancelled:
            neural.stop()

    def stop(self):
        self.pending_speech = None
        self._speech_generation = getattr(self, '_speech_generation', 0) + 1
        self._cancel_current()
        self.playing = False
        self.note('Stopping...' if self._worker_alive() else 'Stopped.')
        # Minimal worker fixtures do not own Tk controls.
        if hasattr(self, 'engine_var'):
            self.update_action_buttons()

    def remove_virtual(self):
        if getattr(self, 'removing', False):
            return
        self.removing = True
        self.stop()
        self.after_worker(self.remove_virtual_devices)

    def after_worker(self, callback):
        # Keep Tk responsive, but let streaming cleanup finish before removing
        # its sink or exiting the interpreter with a daemon worker still alive.
        worker = getattr(self, 'worker_thread', None)
        if worker is not None and worker.is_alive():
            self.root.after(25, lambda: self.after_worker(callback))
        else:
            callback()

    def remove_virtual_devices(self):
        if getattr(self, 'portable_audio', None) is not None:
            self.portable_audio.stop()
            self.active_output = None
            self.active_output_label = None
            self.sink_active = False
            self.removing = False
            self.update_action_buttons()
            self.note('Audio disconnected. Your installed virtual audio driver is unchanged.')
            return
        for module_id in reversed(self.modules[:]):
            self.unload_module(module_id)
        self.preview_module = None
        self.mic_module = None
        self.sink_active = False
        self.removing = False
        self.note('Virtual microphone removed. Discord can use your physical microphone again.')

    def close(self):
        if getattr(self, 'closing', False):
            return
        self.closing = True
        self.stop()

        def finish():
            neural = getattr(self, 'neural', None)
            if neural is not None:
                neural.close()
            self.remove_virtual_devices()
            portable = getattr(self, 'portable_audio', None)
            if portable is not None:
                portable.close()
            self.root.destroy()

        self.after_worker(finish)


def main():
    try:
        use_app_venv()
        if current_platform() == 'linux':
            restore_display()
        missing = [tool for tool in ('pactl', 'paplay') if shutil.which(tool) is None]
        if missing and current_platform() == 'linux':
            raise RuntimeError('Missing commands: ' + ', '.join(missing) + '\nRun ./install.sh')
        # Check this before Qt initialization: a missing display can otherwise
        # abort in the platform plugin before Python can write a startup log.
        if (current_platform() == 'linux'
                and not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY')
                and os.environ.get('QT_QPA_PLATFORM') not in ('offscreen', 'minimal')):
            raise RuntimeError('Qt needs an X11/XWayland or Wayland desktop session. '
                               'Open the app from your desktop terminal.')
        from qt_ui import QtRoot
        root = QtRoot()
        DiscordTTS(root)
        root.mainloop()
        return 0
    except Exception as error:
        message = APP + ' could not start: ' + shorten_error(error)
        if isinstance(error, TclError):
            message += ('\nRun from your desktop terminal; check DISPLAY and XAUTHORITY.')
        try:
            from runtime_support import user_state_dir
            log = user_state_dir() / 'startup.log'
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(message + '\n' + traceback.format_exc(), encoding='utf-8')
            message += '\nStartup log: ' + str(log)
        except OSError:
            pass
        print(message, file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
