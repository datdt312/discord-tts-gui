# Product behavior

Discord TTS GUI sends typed speech into an operating system microphone that
Discord can select. It is intended for local interactive use without a bot,
Discord account token or API key. See the [README](../README.md) for setup.

## Engines

| Engine | Preparation | Behavior |
| --- | --- | --- |
| VieNeu-TTS v3 Turbo | Explicit runtime/model download | Default engine; local CPU ONNX fp32 synthesis after setup |
| Microsoft Edge | Internet connection | Sends submitted text to Microsoft's speech service and streams the response |
| eSpeak NG | Installed native executable | Optional lightweight offline speech |

Offline AI setup uses a private runtime and several GB of available disk space
should be allowed for dependencies, model files and caches. An ordinary launch
or Speak request never begins a download. The app lists installed preset
voices only after setup verifies a short utterance with networking disabled.
Missing or incomplete preparation produces an actionable error.

Engine and voice choices are explicit. A failed online request never switches
to eSpeak or VieNeu, and unavailable neural models never trigger online speech.
Microsoft Edge voice weights are not supplied for offline use by this app.

## Connecting audio

| Platform | App output | Discord input |
| --- | --- | --- |
| Linux | App-created virtual sink | `Discord_TTS_Microphone` |
| Windows | Installed VB-CABLE `CABLE Input` endpoint | `CABLE Output` |
| macOS | Installed BlackHole output | Matching BlackHole input |

On Linux, Create virtual mic creates temporary devices while the GUI is open.
Closing or removing them unloads only modules created by the app. On Windows
and macOS, users install the virtual audio driver separately, select its
output and press Connect audio. The app may suggest a recognized virtual
endpoint but never substitutes system speakers when it is absent.

The app leaves system default audio devices unchanged. Speaker preview is
optional on every platform. Portable preview requires a separate selected
speaker. Built-in physical microphone mixing is available only on Linux;
Windows/macOS users need an external mixer for that combination. Headphones
help prevent echo when preview and microphone mixing are both enabled.

## Reading and stopping

1. Connect the audio route and select its input in Discord.
2. Select an engine and available voice; prepare offline AI first if needed.
3. Enter text and press Speak. Speed 155 is the normal setting.
4. Press Stop to interrupt preparation or speech, including a pending online
   response before the first audio arrives.

Speak during playback replaces the current speech with the latest editor
contents. Changing the engine or voice while speaking also requests a restart.
Rapid actions retain one latest pending request; the previous worker must
finish stopping before the next begins. Stop, disconnect and close discard
pending restarts. Changing a model while idle does not start speech.

Typing never sends a request. Ctrl+A selects all editor text; pasting replaces
the selection or inserts at the cursor. Empty/unavailable clipboard data
preserves the editor contents. Replacement paste is one Undo operation.

## Feedback and recovery

The editor and optional settings scroll above persistent speech/audio actions.
The Qt window supports a minimum size of 560 × 480. Download progress describes
the current file, with actual received bytes and a percentage when the server
provides a total. Unknown totals show activity without an invented percentage.
Package installation and model verification are separate busy stages.

Download progress disappears after success, failure or cancellation. After
successful setup, the primary download action is hidden; Repair / download AI
voices remains in Audio & settings. Existing cache files are reused by repair.

Online empty-audio responses can retry before any audio has been delivered.
A failure after playback begins stops the request rather than replaying its
spoken prefix. Retry attempts are per message; there is no local usage quota.
Service availability, first-audio latency and pronunciation depend on the
selected engine and environment.

Native Windows/macOS bundles require their own OS builds and target-device
verification. Offscreen tests and simulated devices do not establish audible
quality or hardware compatibility. See [testing](./testing.md),
[release procedures](./releasing.md) and [troubleshooting](./troubleshooting.md).
