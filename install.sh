#!/usr/bin/env bash
set -euo pipefail
sudo apt update
sudo apt install -y python3-tk python3-venv libsndfile1 xauth espeak-ng ffmpeg pulseaudio-utils pavucontrol
# Qt 6 is preferred; Ubuntu 22.04 / Mint 21 provide Qt 5 instead.
if apt-cache show python3-pyqt6 >/dev/null 2>&1; then
    sudo apt install -y python3-pyqt6
else
    sudo apt install -y python3-pyqt5
fi
APPDIR="$HOME/.local/share/discord-tts-gui"
SRCDIR="$(dirname "$(realpath "$0")")"
mkdir -p "$APPDIR" "$HOME/.local/share/applications"
cp "$SRCDIR/requirements.txt" "$APPDIR/requirements.txt"
/usr/bin/python3 -m venv --system-site-packages "$APPDIR/.venv"
"$APPDIR/.venv/bin/python" -m pip install -r "$APPDIR/requirements.txt"
"$APPDIR/.venv/bin/python" -c 'import edge_tts; import tkinter; from importlib.util import find_spec; assert find_spec("PyQt6") or find_spec("PyQt5"), "Qt binding missing"; print("Python dependencies verified.")'
for source_file in app.py neural_backend.py neural_runtime.py neural_playback.py neural_model_files.py desktop_ui.py qt_ui.py; do
    cp "$SRCDIR/$source_file" "$APPDIR/$source_file"
done
chmod +x "$APPDIR/app.py"
cat > "$HOME/.local/share/applications/discord-tts-gui.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Discord TTS GUI
Comment=Send text-to-speech to Discord via virtual microphone
Exec="$APPDIR/.venv/bin/python" "$APPDIR/app.py"
Icon=audio-input-microphone
Terminal=false
Categories=AudioVideo;Audio;
EOF
chmod +x "$HOME/.local/share/applications/discord-tts-gui.desktop"
if command -v kbuildsycoca6 >/dev/null 2>&1; then
    kbuildsycoca6 --noincremental || echo 'KDE menu cache was not refreshed. Use the launch command below.'
fi
echo 'Installed. Close existing Discord TTS GUI windows, then reopen from the KDE menu.'
printf 'Or launch directly: %q %q\n' "$APPDIR/.venv/bin/python" "$APPDIR/app.py"
