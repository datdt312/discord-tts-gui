> Historical implementation record. Current instructions are in [the documentation index](../../README.md).

# Streaming TTS playback

**Goal:** Start online speech before the complete message has downloaded, preserving the selected voice and explicit offline mode.

**Architecture:** Consume edge-tts audio chunks directly. Feed FFmpeg through a pipe and play its PCM output with paplay using a small audio buffer. Share the provider retry/error handling with file synthesis. A cancellation watcher interrupts network waits and playback. Retry only before audio has been delivered, to prevent replaying spoken text.

**Constraints:** No new dependencies, no additional service requests while typing, no automatic voice/engine switch. Preserve offline synthesis and virtual mic routing. The service's first-audio latency cannot be eliminated locally. Network waits are bounded independently of playback of long messages.

- [x] Write failing integration tests using a local MP3 stream, real FFmpeg and a recording subprocess in place of the audio server. Prove PCM arrives before the provider finishes.
- [x] Cover stopping before/during streaming, provider failures before/after audio, subprocess cleanup and worker routing.
- [x] Implement shared online transport and streaming playback, then connect the worker and status feedback.
- [x] Update usage notes and run the complete unittest suite and syntax checks.

**Verification:** 35 tests pass with `python3 -m unittest -v`; `bash -n install.sh` and Python compilation pass. Code review identified a close-window race with the daemon worker; the GUI now waits asynchronously for worker cleanup before unloading the sink or exiting, with shutdown regression coverage. The same ordering is used when removing the virtual mic during playback.

**Local measurement:** With installed edge-tts 7.3.1, a simulated stream, real FFmpeg and a recording subprocess, first PCM arrived in 30 ms while the complete simulated download took 486 ms. This proves overlapping decode/playback, not actual service or PulseAudio latency. Live Microsoft synthesis and audible output remain unverified in the restricted environment.

No Git metadata is available. The installed copy is outside the writable workspace; provide the existing single-file update command after verification.
