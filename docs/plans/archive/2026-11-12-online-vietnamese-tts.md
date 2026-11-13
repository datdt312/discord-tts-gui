> Historical implementation record. Current instructions are in [the documentation index](../../README.md).

# Online Vietnamese TTS Implementation Plan

**Goal:** Replace the default eSpeak Vietnamese speech with online neural speech, following the user's choice to prioritize intelligibility over offline operation.

**Architecture:** Keep the existing Tkinter and PulseAudio routing. Add a synthesis function that uses edge-tts for online speech, converts its MP3 output to PCM WAV using FFmpeg, and retains eSpeak as an explicitly selected offline engine. Run synthesis in the existing worker thread.

**Tech Stack:** Python, Tkinter, edge-tts, FFmpeg, eSpeak NG, PulseAudio/PipeWire.

**Constraints:** Text may be sent to the online provider; the user explicitly selected online speech. No automatic fallback to eSpeak on network failure. Installation uses a private virtual environment, not system pip. Keep current virtual mic behavior.

## Implementation

- [x] Add failing synthesis tests for Vietnamese Unicode, voice selection, speed conversion, offline operation, network errors, and PCM WAV conversion.
- [x] Implement `synthesize_speech(text, voice, speed, path, engine)` in `app.py`, with a bounded online request and actionable failures.
- [x] Add engine selection and Vietnamese female/male voices to `DiscordTTS`; pass the chosen engine to the worker without accessing Tk from the worker.
- [x] Update `install.sh`, `requirements.txt`, and `README.md` for the private venv, online default, dependency installation, and limitations.
- [x] Run the complete unittest suite and shell syntax check. All 16 tests pass. Live online synthesis is unverified: this environment cannot fetch edge-tts from PyPI, despite the package being listed by PyPI. GUI/audio-server access is also sandbox-restricted.

## Review focus

Unicode input must reach the provider unchanged. A failed request must not play stale audio. MP3 must be decoded before paplay. Switching engines must clear old voice choices. The desktop launcher must use the installed venv interpreter.

No Git metadata is available in this workspace; no commit is planned.
