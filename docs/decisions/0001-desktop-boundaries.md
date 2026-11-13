# Decision 0001 Desktop boundaries

Status: Accepted

## Context

The app supports Linux virtual microphone creation and Windows/macOS virtual
audio drivers. It also supports online synthesis, a small native offline
engine and an optional neural SDK with substantial dependencies and models.
These paths need the same interactive behavior without importing every native
dependency at startup or coupling speech to a particular audio server.

Packaging has two forms: a Debian package using system dependencies and native
desktop bundles containing their desktop dependencies. Source launchers also
need to remain usable. The existing flat module layout is shared by these
entry points and is retained during repository organization work.

## Decision

Use Qt as the normal desktop frontend, preferring PyQt6 and falling back to
PyQt5. Keep `app.py` as the controller and keep widget construction in
`qt_ui.py`. Retain the Tk adapters/layout for compatibility and legacy tests;
normal startup constructs the Qt root.

Keep speech requests asynchronous with one active worker and one replaceable
pending request. A new request cancels active work and waits for its cleanup.
Generation-tagged events protect the UI from stale speech completion/status
events. Stop, disconnect and close invalidate pending speech. UI widgets are
updated through the event loop rather than directly by speech workers.

Keep platform audio at an explicit boundary. Linux creates a PulseAudio null
sink/remapped source and owns the module IDs it creates. Windows/macOS use
`portable_audio.py` with sounddevice/PortAudio and an explicitly selected
installed output. Optional portable preview requires a separate output.
Physical microphone mixing remains a Linux feature; other platforms use an
external mixer. Default audio devices remain under user control.

Use FFmpeg for streaming decoding and tempo conversion. Portable playback
passes 48 kHz stereo signed 16-bit PCM through bounded callback queues.
Cancellation must propagate through provider waits, worker processes,
decoders and output consumers without leaving overlapping speech.

Keep VieNeu SDK `3.8.4` in a private per-user runtime. Setup/repair is explicit;
ordinary startup and speech do not install dependencies or fetch models.
Readiness requires a versioned manifest and successful offline synthesis.
Offer actual installed voices and report errors without choosing another
engine automatically.

Source setup uses the current interpreter's venv support. Frozen bundles ship
uv to create managed Python 3.12. SDK worker source lives separately under
`_MEIPASS/workers` so external Python does not resolve frozen native extensions.
Sanitize external interpreter library/import paths and terminate descendant
processes using POSIX process groups or Windows Job Objects.

Preserve downloaded Hub cache data. Materialize ONNX graphs and external
weights as private regular files before loading rather than weakening ONNX
path validation or modifying the shared cache layout.

## Consequences

The controller remains shared across frontends and packaging targets, while
device access and the neural SDK can be tested at their boundaries. Native
dependencies can stay lazy where the UI needs to explain missing setup.
Separate private Python increases first-time neural setup cost and disk use
but avoids installing the SDK into system or GUI Python environments.

The retained Tk compatibility surface adds maintenance work. Module moves
must update source launchers, both package builders and test imports together.
The flat layout is not a promise that every module is a public API.

Automated tests can establish request ordering, bounded buffering, process
cleanup, UI state and package contents. They cannot establish audible quality,
real driver compatibility or successful native installation on another OS.
Target-system build and manual playback verification remain release checks.

## References

- [Architecture](../architecture.md)
- [Product contracts](../product.md)
- [Development setup](../development.md)
- [Testing and manual acceptance](../testing.md)
- [Build and release procedures](../releasing.md)
