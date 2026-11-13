# Discord TTS GUI

Vietnamese text-to-speech for Discord, with a Qt desktop interface for Linux,
Windows and macOS. VieNeu-TTS offline AI is the default; Microsoft Edge online
voices and optional eSpeak NG are also available. No Discord bot or token is needed.

## Features

- Stream speech to a selected virtual microphone/output.
- Restart with the latest text, model or voice; rapid requests keep only the newest one.
- Download offline voices with per-file progress and reuse the existing cache.
- Preview speech through speakers; mix a physical microphone on Linux.
- Keep Speak/Stop visible while settings and long content scroll.

## Platform support

| Platform | Routing | Start from source |
| --- | --- | --- |
| Linux | App-created PulseAudio/PipeWire virtual microphone | `./install.sh` |
| Windows | [VB-CABLE](https://vb-audio.com/Cable/): app → CABLE Input, Discord → CABLE Output | `start-windows.bat` |
| macOS, Intel / Apple Silicon | [BlackHole](https://existential.audio/blackhole/): select it in the app and Discord | `start-macos.command` |

Windows/macOS launchers require Python 3.12, create `.venv-desktop`, and install
dependencies on first use. Install the virtual audio driver separately.
Physical microphone mixing on Windows/macOS uses an external mixer.

**Validation status:** Linux tests and offscreen Qt checks are available.
Windows/macOS routing, process handling and packaging have automated boundary
tests; native builds and real device playback still need validation on those OSes.
No hosted repository, published release or successful native CI run is assumed.

## Quick start

1. Install/start the app using the platform entry above.
2. On Linux, click **Create virtual mic**. On Windows/macOS, select the virtual output and click **Connect audio**.
3. Select the corresponding input device in Discord → Voice & Video.
4. On first VieNeu use, click **Download offline AI voices**; choose a voice when setup finishes.
5. Enter text and click **Speak**. Click it again to replace an active reading; **Stop** also clears pending speech.

VieNeu models total about 566 MB, with additional space needed for the private
Python runtime, dependencies and cache. Online speech sends entered text to
Microsoft; downloaded VieNeu inference stays local. See [product behavior](docs/product.md).

## Development

Use Python 3.12 for the development/test environment. Application sources retain
Python 3.10 syntax compatibility. Native Linux dependencies are documented in
[development setup](docs/development.md).

```bash
python -m venv .venv
# Activate .venv using your shell, then:
python -m pip install -r requirements-desktop.txt
python app.py
```

Check structure/docs and run the regression suite:

```bash
python tools/check_repo.py
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -t . -v
```

For PowerShell and focused test commands, see [testing](docs/testing.md).

## Build and connect a remote

```bash
python packaging/build_deb.py                         # Linux .deb
python packaging/build_desktop.py --target windows --plan
python packaging/build_desktop.py --target macos --plan
python tools/export_source.py                        # Clean source ZIP in dist/
```

Native desktop bundles require `requirements-build.txt` and a build host matching
the target OS. GitHub Actions produces artifacts on manual runs or version tags;
it does not automatically publish releases. See [releasing](docs/releasing.md).

Connect your own remote using the [Git setup guide](docs/GITHUB_SETUP.vi.md).
No credentials or remote URL are embedded in the project.

## Project map

| Location | Responsibility |
| --- | --- |
| `app.py`, `qt_ui.py` | Controller and Qt frontend |
| `neural_*.py` | Private offline runtime, model files and Linux neural playback |
| `portable_*.py`, `media_tools.py`, `runtime_support.py` | Portable audio, executables and data paths |
| `tests/` | Regression, device-boundary and package tests |
| `packaging/` | Native builders, vendored sources and third-party notices |
| `tools/` | Repository checks and clean source export |
| `docs/` | Product, architecture, workflow and operational documentation |

Start at the [documentation index](docs/README.md). Agent contributors use the
shared [AGENTS.md](AGENTS.md), with [Claude](CLAUDE.md) and
[Antigravity](GEMINI.md) entry points. Read only documents relevant to a task.

## License

The application owner has not selected a project license. Public source
visibility does not add a license grant. Existing third-party notices are kept
under [packaging/licenses](packaging/licenses/) and [packaging/copyright](packaging/copyright).
