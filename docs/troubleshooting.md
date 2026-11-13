# Troubleshooting

Start with the launch command for your installation and read the full error
details. Source environments and packaged runtimes have different dependency
paths; see [development](./development.md) and [releasing](./releasing.md).

## The window does not open

For a Linux `.deb`, run `discord-tts-gui` from the desktop terminal and try
`discord-tts-gui --check` for imports and native tools. For a source install:

```bash
"$HOME/.local/share/discord-tts-gui/.venv/bin/python" "$HOME/.local/share/discord-tts-gui/app.py"
```

Linux needs an X11/XWayland or Wayland desktop session. Startup preserves an
explicit `DISPLAY` and recovers a missing display only when the current user's
Xauthority data identifies a single local session. Check `DISPLAY`,
`WAYLAND_DISPLAY` and `XAUTHORITY` if the menu launch differs from the terminal.
Enable XWayland where required. Run the GUI as your desktop user, without sudo.

Startup errors are written to `startup.log` under these state directories:

| Platform | State directory |
| --- | --- |
| Linux | `$XDG_STATE_HOME/discord-tts-gui`, normally `~/.local/state/discord-tts-gui` |
| Windows | `%LOCALAPPDATA%/discord-tts-gui` |
| macOS | `~/Library/Logs/discord-tts-gui` |

On Windows/macOS, rerun the source launcher to see dependency installation
errors. On macOS, `chmod +x start-macos.command` restores a missing executable
permission. For frozen bundles, run their executable with `--check`; it checks
bundled resources without opening an audio device or downloading models.

## Discord cannot see the microphone

Linux installation alone does not create a microphone. Keep the GUI open,
press Create virtual mic and inspect:

```bash
pactl info
pactl list sources short
pactl list modules short
```

Look for source `discord_tts_mic`, displayed as `Discord_TTS_Microphone`.
If it exists, reopen Discord's input selector or reconnect the voice call.
If module creation fails, check the user's PulseAudio/PipeWire service and
support for null-sink/remap-source modules.

Windows needs VB-CABLE installed: select CABLE Input in the app and CABLE
Output in Discord. macOS needs BlackHole selected in both applications.
Refresh devices after driver installation or device changes, then Connect
audio again. The app does not route to system speakers as a fallback. To hear
speech locally, enable preview and select a separate speaker output.

If Discord cuts off synthetic speech, check its noise suppression and automatic
gain settings, or try push-to-talk. Use headphones when mixing a microphone
with speaker preview to avoid acoustic feedback.

## Online speech fails or produces no audio

Check the Internet connection and FFmpeg availability. An empty service reply
can happen with a working connection and does not prove a rate limit. The app
tries up to three attempts before first audio, keeping the selected voice;
these attempts are per message, not a quota of successful uses. Try another
voice or retry later. Once audio has started, failures stop playback instead
of repeating the beginning. Other connection/decoder errors remain explicit.

For missing `edge_tts`, update the complete app and its environment, then close
old windows. A source installation can be refreshed with `./install.sh`.
Copying only `app.py` omits required modules. Linux startup uses a valid `.venv`
next to the script, so check which interpreter your launcher actually selects.

## Offline AI setup or model loading fails

Use Repair / download AI voices in Audio & settings. Check the complete error,
network access and available disk space; Linux source installs also need
working Python venv support and libsndfile. Frozen bundles need their bundled
uv and worker files. A per-file 100% indicator is followed by other downloads
and model verification; it is not completion of the whole setup.

Keep the existing cache when retrying. For an ONNX error such as “External
data path escapes model directory”, update the complete app and repair. The
runtime creates private regular copies of graphs and external weights while
preserving the original Hugging Face cache.

Neural data lives under `neural/v3turbo-onnx-fp32` within Linux
`$XDG_DATA_HOME/discord-tts-gui` (normally `~/.local/share/discord-tts-gui`),
Windows `%LOCALAPPDATA%/discord-tts-gui`, or macOS
`~/Library/Application Support/discord-tts-gui`. Preserve it across upgrades.
Stop releases the resident model worker, so the next utterance reloads models.
The app never selects another engine to conceal setup or synthesis failures.

When reporting a problem, include OS/architecture, install method, selected
engine and device, reproduction steps and full error details. Remove private
text and local identifiers from logs before sharing them.
