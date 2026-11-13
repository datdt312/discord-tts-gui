# Testing

The suite uses Python's standard `unittest` runner. Run from the repository
root so `tests` and application modules resolve consistently. Install the
dependencies described in [development](./development.md) before running it.

## Commands

On Linux, run the complete suite with Qt offscreen:

```bash
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -t . -v
```

Use the selected environment's interpreter when necessary, for example
`.venv/bin/python` instead of `python3`. On PowerShell:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m unittest discover -s tests -t . -v
```

Run focused modules while working on a boundary:

```bash
QT_QPA_PLATFORM=offscreen python3 -m unittest -v tests.test_speech_replacement tests.test_qt_controller
python3 -m unittest -v tests.test_neural_backend tests.test_neural_runtime tests.test_neural_model_files
python3 -m unittest -v tests.test_portable_audio tests.test_portable_playback
python3 -m unittest -v tests.test_packaging tests.test_desktop_packaging
```

The explicit discovery root prevents recursion into vendored dependency tests
and makes the `tests.` module prefix consistent between local work and CI.

## Coverage boundaries

| Area | Main evidence |
| --- | --- |
| Controller | Latest request replacement, event generations, Stop, teardown and setup state |
| Streaming | Real FFmpeg decoding with local fixtures and provider/audio stand-ins |
| Qt | Real offscreen widgets, editor behavior, layout and controller adapters |
| Legacy Tk | Editor shortcuts and layout with an available Tk display |
| Neural | Stand-in SDK subprocesses, offline guards, readiness and process cleanup |
| Portable audio | Explicit device selection, callback buffering and cancellation doubles |
| Debian | Real build/extraction, metadata, dependencies and packaged source syntax |
| Native bundles | Build plans, staged contents, worker isolation and bootstrap commands |

Streaming tests avoid the Microsoft service and a live audio server. They
check that PCM arrives before the provider finishes, empty-response retries
occur only before first audio, and cancellation unblocks remote waits.
Neural fixtures avoid SDK/model downloads while exercising the real worker
protocol. These tests must remain usable without credentials or Internet.

## Environment-dependent checks

Qt offscreen mode does not provide a Tk display. Legacy Tk widget tests may
skip on a headless machine; use a desktop display or Xvfb to run them. Qt
tests need a usable PyQt6 or PyQt5 installation. Startup display fixtures use
`xauth`. Debian package tests need Linux and `dpkg-deb`; desktop metadata
validation uses `desktop-file-validate` when available.

Real POSIX descendant cleanup tests use Linux `/proc`. The real Windows Job
Object descendant test requires Windows; platform doubles on Linux cover
command construction and handle behavior but cannot substitute for that test.
Read skip reasons before interpreting a passing result.

The Actions workflow runs the Linux suite and a focused portable subset on
Windows/macOS native runners. Frozen `--check` validates bundled libraries,
FFmpeg, uv and worker sources without opening a window or downloading models.
It does not validate a virtual driver or an audible audio route.

## Manual acceptance

For a target system, verify these behaviors with the actual desktop and audio
devices before claiming installation or hardware support:

1. Launch from the intended source/package entry point and inspect startup
   errors if any. Connect the virtual route and select it in Discord.
2. Listen to online and installed offline voices, with preview both disabled
   and enabled. Check Unicode text and a long utterance.
3. Replace active speech rapidly; check that the latest request wins without
   overlapping voices. Stop before first audio and during playback.
4. Prepare/repair AI voices, cancel setup, retry with the existing cache, then
   test speech without networking. Verify terminal progress is hidden.
5. Disconnect and close while speaking; check workers and owned virtual
   devices disappear. Confirm system default devices remain unchanged.

Record the OS, package architecture, audio driver and manual outcomes alongside
release validation. Keep live service latency and audible quality separate
from automated regression results. See [releasing](./releasing.md).
