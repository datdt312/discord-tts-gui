# Discord TTS GUI

Read text into Discord using VieNeu-TTS offline AI, Microsoft Edge online
voices or optional eSpeak NG. This guide accompanies the desktop package;
the source repository contains developer documentation and build instructions.

## Start

- **Windows:** extract the complete ZIP and open `Discord TTS GUI.exe` inside the app folder. Keep its companion files together.
- **macOS:** extract the ZIP matching Apple Silicon or Intel, then open `Discord TTS GUI.app`.
- **Linux DEB:** install the `.deb`, then open **Discord TTS GUI (Linux)** from the applications menu, or run `discord-tts-gui`.

Windows/macOS bundles include Qt, FFmpeg, PortAudio and the private-Python
bootstrap. Model weights and virtual audio drivers are not bundled. Native
desktop builds are unsigned; signing/notarization is not configured.

## Connect Discord

1. Linux: click **Create virtual mic**, then select **Discord TTS Microphone** in Discord's input device settings.
2. Windows: install [VB-CABLE](https://vb-audio.com/Cable/), choose **CABLE Input** in this app and **CABLE Output** in Discord.
3. macOS: install [BlackHole](https://existential.audio/blackhole/), then choose it in both the app and Discord.
4. On Windows/macOS click **Connect audio** after choosing the output.

Drivers are installed separately using the vendor instructions. The app does
not change the system default audio device or uninstall existing drivers.

## Speak

VieNeu is selected by default. On first use click **Download offline AI voices**;
the app installs its private runtime and verifies local model loading. Models
total about 566 MB, with several GB needed for runtime/cache depending on the OS.

Choose a voice, enter text and click **Speak**. Clicking it again or changing a
model/voice during playback replaces the reading with your latest text. **Stop**
cancels playback and any pending restart. Download progress hides after setup.
Open **Audio & settings** for preview speakers, device refresh and model repair.
Physical microphone mixing is built in on Linux; other OSes use an external mixer.

Microsoft voices require Internet and send entered text to Microsoft. Downloaded
VieNeu inference stays local. The app does not silently change engines or choose
system speakers when a virtual output is missing.

## Diagnose

- If online speech says **3 attempts**, those are retries for one failed message, not a three-use quota.
- If model setup fails, retry Download/Repair with the existing cache; do not delete completed downloads first.
- If output is missing, install/check the virtual driver, refresh devices and reconnect the route.
- Keep the entire app folder when moving a Windows bundle.
- Package runtime checks use `discord-tts-gui --check` on Linux or the native executable with `--check`.

Model data lives in `neural/v3turbo-onnx-fp32` under:

- Linux: `~/.local/share/discord-tts-gui`, or the configured XDG data location.
- Windows: `%LOCALAPPDATA%/discord-tts-gui`.
- macOS: `~/Library/Application Support/discord-tts-gui`.

Startup logs are under the Linux XDG state directory, the Windows data directory,
or `~/Library/Logs/discord-tts-gui` on macOS. Package upgrades preserve models.

Hardware playback and native installation still require target-system validation.
Dependency notices accompany the package; no project license has been selected
for the original application sources.
