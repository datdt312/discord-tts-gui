# Discord TTS GUI — Linux, Windows & macOS

A Qt desktop app that reads typed text into Discord on Linux, Windows and macOS. **VieNeu-TTS offline AI is the default engine.** Microsoft Edge online voices and eSpeak NG are also available. No Discord token, bot, or API key is needed.

Online speech requires Internet access and sends the text you enter to Microsoft's TTS service. Offline eSpeak speech stays on your computer but Vietnamese pronunciation can sound robotic and unclear.

## Choose your platform

| Platform | Audio route | Run / package |
| --- | --- | --- |
| Linux | PipeWire/PulseAudio virtual mic created by the app | Native `.deb`; `install.sh` for source |
| Windows | Select **CABLE Input** in the app, **CABLE Output** in Discord | Native `.exe` folder ZIP; `start-windows.bat` for source |
| macOS (Apple Silicon / Intel) | Select **BlackHole** in the app and Discord | Native `.app` ZIP for your architecture; `start-macos.command` for source |

Windows and macOS use a virtual audio driver installed once by the user.
The app connects to that driver; disconnecting/closing the app does not uninstall
it or change your system's default audio devices. Install drivers from the
[VB-CABLE official page](https://vb-audio.com/Cable/) or
[BlackHole official page](https://existential.audio/blackhole/). BlackHole can
also be installed with `brew install blackhole-2ch`.

### Windows / macOS from source

Download/extract the complete cross-platform source archive. Install Python
3.12 (3.10+ supported for the app), then double-click **start-windows.bat** on
Windows or **start-macos.command** on macOS. First launch creates
`.venv-desktop` and installs Qt, the TTS client, FFmpeg and PortAudio dependencies;
an Internet connection is needed. If a Mac archive extractor drops executable
permissions, run `chmod +x start-macos.command` in the extracted folder.

Select the virtual audio output, click **Connect audio**, select its matching
input in Discord and press **Speak**. **Get VB-CABLE / BlackHole driver** opens
the official vendor page if no virtual endpoint is installed. The app never
selects system speakers automatically. Speaker preview is optional; select a
separate speaker in Audio & settings. Mixing a physical microphone is built in
on Linux; Windows/macOS users can combine it through an external audio mixer.

### Native Windows / macOS bundles

`packaging/build_desktop.py` creates a Windows folder containing
`Discord TTS GUI.exe`, or a macOS `Discord TTS GUI.app`. The native bundle
includes Qt, FFmpeg, PortAudio and uv. Optional VieNeu setup uses bundled uv to
create a private managed Python 3.12 environment on the first **Download** click;
normal launch/reading does not provision Python or download model weights.

Windows/macOS bundles must be built on their target OS. The GitHub Actions
workflow in `.github/workflows/build.yml` builds Linux `.deb`, Windows x86_64,
macOS ARM64 and macOS Intel artifacts on `workflow_dispatch` or a `v*` tag.
These are CI artifacts, not automatically published GitHub Releases. A real
GitHub repository and a successful workflow run are required before those
native archives exist. The Linux environment used for this change cannot
produce or verify Windows/macOS binaries. Source launchers are included now.

Build natively after installing `requirements-build.txt`:

```bash
python packaging/build_desktop.py
```

Inspect a plan on any OS without build dependencies:

```bash
python packaging/build_desktop.py --target windows --plan
python packaging/build_desktop.py --target macos --plan
```

Native artifacts are unsigned; signing/notarization credentials are not configured.
On macOS use Apple's documented
[opening procedure for apps from identified/other developers](https://support.apple.com/en-us/102445)
if the locally built application is blocked.

## Linux installation

For Ubuntu/Kubuntu 22.04+ and Linux Mint 21+, use the single-file installer
`dist/discord-tts-gui_1.3.0_all.deb`. Double-click it, choose **Install**, then
open **Discord TTS GUI (Linux)** from the applications menu. On Kubuntu use
Discover to open the package; on Mint use GDebi/Package Installer. First
installation needs Internet if system dependencies are missing. Online
speech always needs Internet. This is a Debian-family package; other Linux
distributions should use the source installation with equivalent dependencies.

If a package installer is not available, install from the directory containing
the `.deb` with:

```bash
sudo apt install ./discord-tts-gui_1.3.0_all.deb
```

The package includes the current app and unmodified pure Python dependencies.
APT supplies Qt/PyQt, Python/Tk, aiohttp, FFmpeg, eSpeak NG and PulseAudio utilities;
the `.deb` installation does not run pip or download packages from PyPI. Optional
VieNeu neural setup is a separate action: it creates a per-user private venv and
downloads the SDK and model files when you click its download button. The app installs into
`/usr/share/discord-tts-gui` with a command at `/usr/bin/discord-tts-gui`.
Close old app windows before upgrading. A previous `install.sh` launcher may
still appear as **Discord TTS GUI**; use the new **Discord TTS GUI (Linux)**
entry for the packaged version. No package script modifies your home directory.

Check the packaged runtime with `discord-tts-gui --check`, launch with
`discord-tts-gui`, or uninstall with `sudo apt remove discord-tts-gui`.
Vietnamese instructions are included in
`/usr/share/doc/discord-tts-gui/README.vi.txt`.

To build the installer locally (Python 3.10+ and `dpkg-deb` required):

```bash
python3 packaging/build_deb.py
```

This produces the `.deb` and `dist/SHA256SUMS`. Vendored sources, exact versions
and licenses are under `packaging/`; the development virtualenv is excluded.
Packaging tests inspect/extract a real `.deb`, validate desktop metadata and
check Python 3.10 syntax. The app uses PyQt6 when available, with PyQt5 on
Ubuntu 22.04 / Mint 21. APT selects the available binding. The Qt interface is
checked with real offscreen widgets, including layout at 560 × 480. Actual installation and playback on each supported
Kubuntu/Mint release still need verification on those systems.

### Install from source

```bash
unzip discord-tts-gui.zip
cd discord-tts-gui
chmod +x install.sh
./install.sh
```

Launch **Discord TTS GUI** from the KDE app menu, or run:

```bash
"$HOME/.local/share/discord-tts-gui/.venv/bin/python" "$HOME/.local/share/discord-tts-gui/app.py"
```

To upgrade from the old offline-only version, run `./install.sh` again. It installs FFmpeg and `edge-tts` in a private Python virtual environment and updates the KDE launcher. Copying `app.py` alone is insufficient for this upgrade.

Close existing app windows after an upgrade. The installer verifies that its Python can import `edge_tts` and refreshes the KDE menu cache. The application also switches to the `.venv` beside it when started with system Python, to handle cached older launchers. If an old window still reports that online TTS is not installed, close it and use the installed venv launch command above. Import failures include the interpreter path and underlying error for diagnosis.

For development, after installing the system dependencies from `install.sh`:

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

## Linux GUI does not open from the KDE menu

The Qt interface uses your X11/XWayland or Wayland desktop session. Some menu
launches omit `DISPLAY`; the app recovers it from the current user's Xauthority
file when there is a single unambiguous local display. It keeps an explicitly
supplied `DISPLAY`.

If it still fails, run `discord-tts-gui` in Konsole or Terminal to see the error
for a `.deb` installation. For a source installation, use the installed venv
command above. Startup errors
are also written to `~/.local/state/discord-tts-gui/startup.log` (or
`$XDG_STATE_HOME/discord-tts-gui/startup.log` if configured). Ensure XWayland is
enabled in your desktop session; do not run the app with `sudo`.

## Usage

1. Press **Create virtual mic**. The app creates a null sink and a remapped microphone source.
2. In Discord > **User Settings > Voice & Video**, set Input Device to **Discord_TTS_Microphone**. You may need to reopen Discord's device selector or reconnect your voice call.
3. VieNeu-TTS is selected by default. On first use, click **Download offline AI voices** and wait for setup to finish. Select a voice, enter text and press **Speak**. To use online voices, choose **Microsoft Edge (online)** and Hoài My or Nam Minh. **Speed 155** is normal speed.
4. Expand **Audio & settings** to enable speaker preview or mix a physical microphone; select the matching output/capture devices there.
5. Press **Stop** to terminate playback. Online speech also cancels an active service request, including before the first audio arrives. **Remove virtual mic** waits for playback to stop, then unloads only modules created by this app.

The editor/settings area scrolls above the fixed **Speak / Stop /
Create virtual mic** footer. Download information disappears when setup ends;
after successful setup the download button is hidden. Use **Repair / download
AI voices** inside Audio & settings to repair an incomplete installation.

Press **Speak** again while reading to stop the old audio and read the latest
text. Changing engine or voice during speech restarts with your current text.
Rapid requests keep only the newest selection; playback waits for the previous
worker to stop, so voices do not overlap. **Stop**, removing the virtual mic,
and closing the app discard any pending restart. Changing a model while idle
does not start reading.

In the text box, **Ctrl+A** selects all text. **Ctrl+V** replaces highlighted
text, or inserts at the cursor if nothing is selected. Pasting from an empty
or unavailable clipboard preserves your text. Replacement pastes are grouped
as one Undo operation.

Online speech now plays as audio chunks arrive, rather than waiting for the
complete MP3 and a WAV conversion. The player requests a 40 ms audio buffer.
This reduces local startup delay, especially for longer messages; the time
Microsoft takes to return the first audio still depends on its service and
the connection. The status line shows when the app connects, receives audio,
or retries an empty response. No requests are sent while you type.

For offline operation, select **eSpeak NG (offline)** and a voice such as `vi`. An online error is shown explicitly; the app does not silently switch back to the less intelligible offline voice.

### Higher-quality Vietnamese offline voices

Select **VieNeu-TTS v3 Turbo (offline AI)** and click **Download offline AI
voices**. This installs the optional `vieneu==3.8.4` runtime and downloads the
models into your user data directory. First setup needs Internet, disk space
(allow several GB), and time to install native Python dependencies. It uses a
private venv, not global Python. No model is downloaded by an ordinary Speak
request. The small `.deb` does not contain the weights.

The current fp32 model graphs and weights total about **475 MB**; the cached
MOSS codec adds about **91 MB** (about **566 MB** together, excluding runtime,
optional auxiliary assets and caches). The installed runtime/cache and private
ONNX copies can occupy roughly **2–3 GB**, depending on dependency versions.
The UI now shows a real **current-file percentage**, downloaded/total MB or GB,
and filename during model downloads. Cached files are identified explicitly.
If the server does not supply a total size, it shows the received bytes and a
busy indicator instead of inventing a percentage. Installing packages and
loading/verifying the model are separate busy stages; 100% for a file is not
100% for the full setup.

If version 1.1.0 reported **External data path escapes model directory**, close
the app, install 1.3.0 and click Download (or Repair in Audio & settings) again. Do not delete the existing cache.
This release copies each snapshot's ONNX graphs and companion weights into an
application-owned folder of regular files before loading them. This avoids
ONNX Runtime's rejection of Hugging Face snapshot symlinks into different blob
shards, preserves the Hub cache, and reuses completed downloads. Private copies
are refreshed only if their source or contents changed.

Setup tests model loading and a short utterance again with Hugging Face offline
mode and Python networking disabled. Only after that succeeds are the actual
installed preset voices offered in the app. Select a preset, create the
virtual mic, and press Speak. No API key is required. Speech then uses the
downloaded model locally, with CPU ONNX/fp32 inference at 48 kHz, streamed to
the virtual mic. The model stays loaded between messages; Stop or closing the
app releases the worker. The first request after a Stop/app restart must load
the model again. Changing Speed uses FFmpeg tempo processing.

Model data is platform-specific:

- Linux: `$XDG_DATA_HOME/discord-tts-gui`, normally `~/.local/share/discord-tts-gui`.
- Windows: `%LOCALAPPDATA%/discord-tts-gui`.
- macOS: `~/Library/Application Support/discord-tts-gui`.

The neural environment is under `neural/v3turbo-onnx-fp32` within that directory.
Startup logs use XDG state on Linux, the same local data root on Windows, and
`~/Library/Logs/discord-tts-gui` on macOS.

For existing Linux installations the model/runtime/cache remain under
`$XDG_DATA_HOME/discord-tts-gui/neural/v3turbo-onnx-fp32` or
`~/.local/share/discord-tts-gui/neural/v3turbo-onnx-fp32`. Downloaded voices remain
there across package upgrades. Missing/incomplete setup produces an explicit
setup error; the app never switches to eSpeak or an online engine automatically.

VieNeu is a neural alternative aimed at more natural Vietnamese speech than
the lightweight eSpeak synthesizer. Quality and actual latency still need to
be evaluated by listening on the target machine. Piper is another smaller
CPU-friendly neural option, with Vietnamese voices, but is not integrated in
this release. References: [VieNeu SDK](https://github.com/pnnbao97/VieNeu-TTS),
[v3 Turbo model](https://huggingface.co/pnnbao-ump/VieNeu-TTS-v3-Turbo),
[Piper voices](https://huggingface.co/rhasspy/piper-voices/tree/main/vi/vi_VN).

### Microsoft returns “No audio was received”

This response can occur even with a working Internet connection: Microsoft's
service may fail to generate audio for a voice. An empty response alone does
not establish that a rate limit is the cause. **Three attempts means retries
for one failed message, not a quota of three uses.** There is no local usage
counter: you can submit more messages, including more than three successful
requests. Increasing retries cannot guarantee the external service will work.
The app now retries this response up to three times with a fresh request and
short delays, with a 60-second budget for network waits and retry delays.
Time spent playing audio does not consume this budget. It keeps your selected
voice; if a later part fails after speech starts, playback stops and the app
does not retry the message or repeat its spoken beginning. If all attempts
fail before any audio arrives, select another voice
(for example, Nam Minh instead of Hoài My) or try again later. Offline eSpeak
remains an explicit choice. Connection, timeout, and FFmpeg decoding errors are
reported separately.

`edge-tts` exposes Microsoft's online service; it does not offer downloads of
Hoài My/Nam Minh model weights for offline use. Use a downloadable model such
as VieNeu instead. The app requires `edge-tts` 7.3.1 or newer. Upgrade via the
new `.deb`, or run `./install.sh` for a source installation, then close old app
windows and reopen. Copying only `app.py` is insufficient because this release
also includes the local neural backend and runtime helpers.

Installing the app does not create a microphone. Keep the GUI open and create
the virtual mic before selecting it in Discord. Closing the GUI removes it.
To check whether creation succeeded, run:

```bash
pactl list sources short
```

Look for `discord_tts_mic`; Discord displays its description as
`Discord_TTS_Microphone`. If it exists but Discord does not list it, reopen the
device selector or restart Discord.

## Notes

- The online engine uses [edge-tts](https://github.com/rany2/edge-tts). Its availability depends on the external service and network access. FFmpeg decodes streamed MP3 directly to PCM, which paplay sends to the virtual microphone.
- The app does **not** modify your default audio devices. It only creates temporary virtual devices; closing the GUI removes them.
- When using Discord voice activity detection, disable aggressive noise suppression/automatic gain controls if it cuts off synthetic voice. Alternatively use push-to-talk.
- Preview plus physical microphone mixing can cause acoustic echo if speakers play near the microphone. Use headphones.
- The installer uses the current user's KDE account; do **not** run the GUI with sudo.
- If PulseAudio emulation or `module-remap-source` fails on your setup, check `pactl info`, `pactl list modules short`, and PipeWire services.
- No direct integration with Discord is required; Discord simply reads an OS microphone device.

## Verification

Cross-platform tests cover VB-CABLE/BlackHole device selection, no implicit
speaker fallback, real FFmpeg streaming and cancellation with a PortAudio
boundary double, Qt Windows/macOS routing controls, frozen worker isolation,
managed Python bootstrap commands, Windows process handling and OS data paths.
Native Windows/macOS builds, SDK installation and real audio hardware still
require verification on those systems; passing mocked platform tests does not
establish hardware compatibility.


Run `python3 -m unittest -v`. Tests use local MP3 fixtures, the real FFmpeg decoder,
a stand-in for the remote TTS provider and a recording subprocess in place of
the audio server. Streaming tests verify that decoded audio arrives before
the provider finishes, retries do not repeat a spoken prefix, Stop interrupts
remote waits, and failures/shutdown clean up playback processes. They do not
contact Microsoft or require an audio server. A live online synthesis test is
still needed to measure actual first-audio latency and listen to voice quality.
Offline neural tests use a stand-in SDK to exercise subprocess streaming,
setup, readiness, cancellation and offline guards without fetching weights.
Live HTTP download progress and hardware playback remain unverified in
this restricted environment. Qt layout, progress visibility, editor shortcuts
and controller integration are checked using real offscreen Qt widgets. The
legacy Tk widget tests skip when no display is available. Using the already-downloaded real SDK/cache,
version 1.1.1 reproduced the original ONNX path failure, then loaded all six
graphs after materialization and successfully ran the actual offline worker:
model warm-up, 25 presets, resident-process synthesis to a 48 kHz PCM WAV, and
process cleanup. Audible quality and hardware playback still need listening
on the target machine.
