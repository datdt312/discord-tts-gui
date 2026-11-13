"""Private VieNeu worker. Run only with the optional neural virtualenv's Python.

JSON lines travel on a duplicate of stdout; fd 1 goes to stderr so SDK/native
logging cannot corrupt audio. Only --download allows Hugging Face access.
"""
import array
import base64
import json
import math
import os
from pathlib import Path
import sys
import threading
import time


def install_download_progress(send):
    """Keep Hub's cache/resume downloader; expose its actual per-file byte counts."""
    os.environ.pop('HF_HUB_DISABLE_PROGRESS_BARS', None)
    import huggingface_hub
    from tqdm.auto import tqdm

    download = huggingface_hub.hf_hub_download

    def with_progress(*args, **kwargs):
        filename = kwargs.get('filename') or (args[1] if len(args) > 1 else 'model')
        if kwargs.get('subfolder'):
            filename = kwargs['subfolder'].rstrip('/') + '/' + filename
        used_progress = False

        class DownloadProgress(tqdm):
            def __init__(self, *bar_args, **bar_kwargs):
                nonlocal used_progress
                used_progress = True
                self._report_lock = threading.RLock()
                self._report_initialized = False
                self._report_closed = False
                self._last_report = 0.0
                # Explicit setup owns this bar, even if inherited settings hide bars.
                bar_kwargs['disable'] = False
                super().__init__(*bar_args, **bar_kwargs)
                self._report_initialized = True
                self._report(force=True)

            def _report(self, force=False):
                if not self._report_initialized:
                    return
                with self._report_lock:
                    now = time.monotonic()
                    if not force and now - self._last_report < .1:
                        return
                    downloaded = max(0, int(self.n))
                    total = self.total
                    if total is not None:
                        total = int(total) if math.isfinite(total) and total >= downloaded else None
                    self._last_report = now
                    send('progress', filename=filename, downloaded=downloaded, total=total)

            def display(self, *args, **kwargs):
                self._report()

            def update(self, n=1):
                result = super().update(n)
                self._report()
                return result

            def close(self):
                if not self._report_closed:
                    self._report_closed = True
                    # Closing an interrupted transfer reports n, never total.
                    self._report(force=True)
                super().close()

        kwargs['tqdm_class'] = DownloadProgress
        path = download(*args, **kwargs)
        # A cache hit may not instantiate tqdm. A successful return is the point
        # where actual on-disk bytes can safely be marked complete.
        if isinstance(path, (str, os.PathLike)):
            size = Path(path).stat().st_size
            send('progress', filename=filename, downloaded=size, total=size,
                 cached=not used_progress)
        return path

    huggingface_hub.hf_hub_download = with_progress


def deny_network():
    """Block Python socket DNS/connect/send operations, including SDK helpers.

    Offline cache flags handle Hugging Face's own cache resolution. This guard
    is an extra Python boundary, not an OS sandbox for arbitrary native code.
    """
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'

    def audit(event, args):
        if event in {'socket.connect', 'socket.getaddrinfo', 'socket.gethostbyname',
                     'socket.gethostbyaddr', 'socket.sendto', 'socket.sendmsg'}:
            raise PermissionError('Network access is disabled for offline neural speech')
    sys.addaudithook(audit)


def pcm16(chunk):
    """Convert a mono float waveform to clipped signed little-endian PCM."""
    if getattr(chunk, 'ndim', 1) != 1:
        raise RuntimeError('Neural SDK returned audio that is not mono')
    values = array.array('h')
    for sample in chunk:
        value = float(sample)
        if not math.isfinite(value):
            raise RuntimeError('Neural SDK returned non-finite audio')
        values.append(max(-32768, min(32767, int(value * 32768))))
    if sys.byteorder != 'little':
        values.byteswap()
    return values.tobytes()


def discover_voices(model):
    voices = {}
    for entry in model.list_preset_voices():
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise RuntimeError('Neural SDK returned an invalid preset voice')
        label, voice_id = entry
        if (not isinstance(label, str) or not label.strip()
                or not isinstance(voice_id, str) or not voice_id.strip()
                or label in voices):
            raise RuntimeError('Neural SDK returned invalid or duplicate preset voices')
        voices[label] = voice_id
    if not voices:
        raise RuntimeError('Neural SDK has no preset voices; run model setup again')
    return voices


def warm_up(model, voice):
    """Force lazy tokenizer/vocoder assets to resolve before claiming readiness."""
    received = False
    for chunk in model.infer_stream('Xin chào.', voice=voice, apply_watermark=False):
        received = bool(pcm16(chunk)) or received
    if not received:
        raise RuntimeError('Neural model verification produced no audio')


def main():
    protocol = os.fdopen(os.dup(sys.stdout.fileno()), 'w', encoding='utf-8', buffering=1)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    protocol_lock = threading.Lock()

    def send(event, **data):
        with protocol_lock:
            protocol.write(json.dumps(dict(event=event, **data), ensure_ascii=False) + '\n')
            protocol.flush()

    try:
        if len(sys.argv) != 2 or sys.argv[1] not in ('--download', '--offline'):
            raise RuntimeError('Expected --download or --offline')
        offline = sys.argv[1] == '--offline'
        if offline:
            deny_network()
        else:
            os.environ.pop('HF_HUB_OFFLINE', None)
            os.environ.pop('TRANSFORMERS_OFFLINE', None)
            install_download_progress(send)
        from neural_model_files import install_local_model_files
        install_local_model_files()
        from vieneu import Vieneu
        model = Vieneu(mode='v3turbo', backend='onnx', device='cpu', precision='fp32')
        if getattr(model, 'sample_rate', None) != 48000:
            raise RuntimeError('Neural SDK sample rate must be 48000 Hz')
        voices = discover_voices(model)
        warm_up(model, next(iter(voices.values())))
        send('ready', voices=voices)
        if not offline:
            return 0
        for line in sys.stdin:
            try:
                request = json.loads(line)
                if request.get('command') != 'speak':
                    raise RuntimeError('Unknown neural worker command')
                voice = request.get('voice')
                if voice not in voices.values():
                    raise RuntimeError('Requested neural preset voice is not installed')
                text = request.get('text')
                if not isinstance(text, str) or not text.strip():
                    raise RuntimeError('Speech text must not be empty')
                received = False
                for chunk in model.infer_stream(text, voice=voice, apply_watermark=False):
                    data = pcm16(chunk)
                    if data:
                        received = True
                        send('audio', data=base64.b64encode(data).decode('ascii'))
                if not received:
                    raise RuntimeError('Neural model produced no audio')
                send('done')
            except Exception as exc:
                send('error', message=str(exc))
        return 0
    except Exception as exc:
        send('error', message=str(exc))
        return 1
    finally:
        protocol.close()


if __name__ == '__main__':
    raise SystemExit(main())
