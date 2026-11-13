"""Entry point used by the native desktop bundles."""
import json
from pathlib import Path
import shutil
import sys


def check_bundle():
    """Validate packaged dependencies without a window, audio device or network."""
    import PyQt6.QtWidgets
    import edge_tts
    import imageio_ffmpeg
    import sounddevice
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
    uv_name = 'uv.exe' if sys.platform == 'win32' else 'uv'
    uv = root / 'tools' / uv_name
    if not uv.is_file():
        candidate = shutil.which('uv') if not getattr(sys, 'frozen', False) else None
        if not candidate:
            raise RuntimeError('Bundled uv executable is missing: ' + str(uv))
        uv = Path(candidate)
    for name in ('neural_runtime.py', 'neural_model_files.py'):
        worker_root = root / 'workers' if getattr(sys, 'frozen', False) else root
        if not (worker_root / name).is_file():
            raise RuntimeError('Bundled worker source is missing: ' + name)
    ffmpeg = Path(imageio_ffmpeg.get_ffmpeg_exe())
    if not ffmpeg.is_file():
        raise RuntimeError('Bundled FFmpeg executable is missing: ' + str(ffmpeg))
    return {'application': 'Discord TTS GUI', 'version': '1.3.0', 'ui': 'PyQt6',
            'edge_tts': edge_tts.__version__, 'ffmpeg': str(ffmpeg), 'uv': str(uv),
            'portaudio': sounddevice.get_portaudio_version()[1]}


def main():
    if sys.argv[1:] == ['--check']:
        try:
            metadata = check_bundle()
            if sys.stdout is not None:
                print(json.dumps(metadata))
            return 0
        except Exception as error:
            if sys.stderr is not None:
                print('Discord TTS GUI bundle check failed: ' + str(error), file=sys.stderr)
            return 1
    # Import here so PyInstaller can discover the application's normal imports.
    import app
    return app.main()


if __name__ == '__main__':
    raise SystemExit(main())
