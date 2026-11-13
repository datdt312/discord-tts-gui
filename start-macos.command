#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
APPDIR="$PWD"
VENV="$APPDIR/.venv-desktop"
failed() {
    echo
    echo 'Setup failed. Read the error above, check your connection and Python installation, then retry.'
    read -r -p 'Press Return to close this window. ' _ || true
}
trap failed ERR
if [ ! -x "$VENV/bin/python" ]; then
    PYTHON_CMD="$(command -v python3.12 || command -v python3 || true)"
    if [ -z "$PYTHON_CMD" ] || ! "$PYTHON_CMD" -c 'import sys; assert sys.version_info >= (3, 10)'; then
        echo 'Install Python 3.12 from https://www.python.org/downloads/macos/ and run this file again.'
        failed
        exit 1
    fi
    echo 'Preparing the desktop Python environment...'
    "$PYTHON_CMD" -m venv "$VENV"
fi
echo 'Checking desktop dependencies. First launch requires an Internet connection.'
"$VENV/bin/python" -m pip install -r "$APPDIR/requirements-desktop.txt"
"$VENV/bin/python" -c 'import PyQt6.QtWidgets, edge_tts, sounddevice, imageio_ffmpeg'
"$VENV/bin/python" "$APPDIR/app.py"
