> Historical implementation record. Current instructions are in [the documentation index](../../README.md).

# Higher-quality Vietnamese offline speech

**Goal:** Resolve confusion about online retries and offer downloaded Vietnamese neural voices, because the user clarified eSpeak works but its speech quality is inadequate.

**Evidence:** Every online request initializes its own three-attempt retry loop; there is no three-use quota. NoAudioReceived alone cannot prove a Microsoft rate limit. eSpeak generates valid Vietnamese WAV locally. User explicitly reports inadequate quality, not a playback error.

**Choice:** VieNeu-TTS v3 Turbo via its CPU ONNX backend at fp32 quality. Upstream SDK vieneu 3.8.4 is released on PyPI and documents preset voices and float32 48 kHz infer_stream output. Piper is lighter but not selected for this quality-first request. Edge weights are not downloadable via edge-tts. Never switch engine/voice silently.

**Architecture:** Optional neural backend installed into a per-user private venv by an in-app setup button; setup downloads/caches models and discovers actual preset voices. An isolated runtime process loads CPU models, keeps them resident between utterances, streams 48 kHz PCM to the GUI worker, and disallows network access during inference. GUI feeds decoded PCM to paplay (FFmpeg atempo only when speed differs). Setup and synthesis run off Tk's thread. Stop/close cancel and reap owned processes; no model download during ordinary Speak. Model weights are not embedded in the small `.deb`.

**Backend interface:** `neural_backend.NeuralEngine()`; `voices() -> dict[label, voice_id]` returns installed presets or {}; `prepare(cancel_event, on_status) -> dict` installs/downloads/verifies; `stream(text, voice, cancel_event, on_status) -> iterator[bytes]` yields signed little-endian 16-bit mono PCM at 48000 Hz; `stop()` cancels active owned processes, reusable later; `close()` releases an idle cached model too. Main thread may invoke stop concurrently with preparation/streaming. Runtime/setup paths honor XDG_DATA_HOME. Missing setup yields an actionable error, no auto-download. Only the dedicated setup path permits network.

- [x] Backend and runtime: TDD, install/download/cache/voice manifest, offline enforcement, persistent streaming, Unicode, process cancellation and failure handling.
- [x] GUI integration: new explicit neural engine, setup button/status, actual preset list, worker PCM playback, shutdown, source installer and `.deb` inclusion.
- [x] Online message clarification and regression showing >3 successful requests are allowed.
- [x] Full regression checks, review, versioned `.deb`, documented verification limits. Actual model download/inference cannot be claimed verified if sandbox DNS prevents fetching weights.

**Verification:** `python3 -W error::ResourceWarning -m unittest -v` passes 79 tests, with the real Tk GUI group skipped because the display is inaccessible. Packaging AST checks include Python 3.10 syntax for all shipped modules. Independent code review reran all 31 neural tests and found no critical/important defect. Shell/desktop/Python checks pass. Built `dist/discord-tts-gui_1.1.0_all.deb` (about 231 KB); extraction verifies all helpers and dependency metadata. Extracted launcher diagnostics succeed with available native aiohttp and correctly report offline AI as not yet installed. Installer checksum verified.

**Limits:** Network DNS prevents actual SDK/model downloads in this environment. Neural tests use a simulated SDK at the dependency boundary and real subprocess/audio pipe behavior. They do not establish successful real-model installation, audible quality, real model latency or hardware playback. Python networking guard is additional protection around the offline cache path, not an OS sandbox for native libraries.

Backend implementation can run independently from GUI/packaging against the interface above; changes have disjoint file ownership.
