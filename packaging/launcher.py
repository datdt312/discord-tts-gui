#!/usr/bin/python3
"""Launch the packaged application with its bundled pure Python dependencies."""
import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
# /usr/bin/python3 -I ignores per-user Python packages and PYTHONPATH. Keep the
# shipped libraries local to this app; never install them into system Python.
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'vendor'))


def main():
    if sys.argv[1:] == ['--check']:
        try:
            import edge_tts
            import tkinter
            from qt_ui import QT_BINDING
            from neural_backend import NeuralEngine
            missing = [tool for tool in ('ffmpeg', 'paplay', 'pactl', 'espeak-ng', 'xauth')
                       if shutil.which(tool) is None]
            if missing:
                raise RuntimeError('Missing commands: ' + ', '.join(missing))
            print(json.dumps({'application': 'Discord TTS GUI',
                              'edge_tts': edge_tts.__version__,
                              'ui': QT_BINDING,
                              'offline_ai_ready': bool(NeuralEngine().voices()),
                              'provider_path': edge_tts.__file__,
                              'python': sys.executable}, ensure_ascii=False))
            return 0
        except Exception as error:
            print('Discord TTS GUI: ' + str(error) + '\n'
                  'Reinstall the .deb with its dependencies, or run:\n'
                  'sudo apt install python3-tk python3-pyqt6 python3-venv libsndfile1 python3-aiohttp ffmpeg '
                  'pulseaudio-utils espeak-ng xauth\n'
                  'On Ubuntu 22.04 / Mint 21, use python3-pyqt5 instead of python3-pyqt6.',
                  file=sys.stderr)
            return 1
    import app
    return app.main()


if __name__ == '__main__':
    raise SystemExit(main())
