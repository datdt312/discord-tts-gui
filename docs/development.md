# Development setup

Run commands from the repository root. Application sources use Python 3.10+
syntax; CI uses Python 3.12. Keep the whole source tree together: copying
`app.py` alone omits the UI, playback and optional runtime modules.

## Dependency layers

| File | Contents | Intended use |
| --- | --- | --- |
| `requirements.txt` | `edge-tts` | Base online provider; native Linux dependencies supplied separately |
| `requirements-desktop.txt` | Base plus PyQt6, sounddevice, imageio-ffmpeg | Portable source desktop runtime |
| `requirements-build.txt` | Desktop plus PyInstaller and uv | Native frozen bundles |

The optional `vieneu==3.8.4` SDK belongs to the app-managed private environment.
Do not add it to the base desktop environment to make setup tests pass. Model
and runtime installation is a user action inside the app, separate from these
requirements files.

## Linux with system Qt

For Ubuntu 22.04 / Mint 21, system PyQt5 works with the supported Qt fallback:

```bash
sudo apt install python3-venv python3-tk python3-pyqt5 libsndfile1 libportaudio2 ffmpeg pulseaudio-utils espeak-ng xauth
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

On distributions with `python3-pyqt6`, that package can replace PyQt5 above.
The system-site option exposes APT's binding to the venv. Alternatively use
an isolated venv and install `requirements-desktop.txt` for pip PyQt6:

```bash
python3 -m venv .venv-desktop
.venv-desktop/bin/python -m pip install -r requirements-desktop.txt
.venv-desktop/bin/python app.py
```

Linux still requires the native PulseAudio-compatible tools and a desktop
audio session. `install.sh` installs source into the current user's data
directory and creates a desktop launcher; it is an installation path, so use
direct repository execution when editing code.

If a valid `.venv` exists next to `app.py`, Linux startup reexecutes its Python.
Remove an obsolete local environment or update it when diagnosing confusing
imports. Run the GUI as the desktop user, without sudo.

## Windows and macOS

Install Python 3.12, then use `start-windows.bat` or `start-macos.command`.
They create `.venv-desktop` and install the desktop requirements. First setup
needs Internet access. On macOS, restore executable permission if needed:

```bash
chmod +x start-macos.command
./start-macos.command
```

For manual PowerShell setup:

```powershell
py -3.12 -m venv .venv-desktop
.venv-desktop\Scripts\python.exe -m pip install -r requirements-desktop.txt
.venv-desktop\Scripts\python.exe app.py
```

Install VB-CABLE or BlackHole separately for Discord routing. The source
dependencies include FFmpeg fallback and PortAudio bindings, but no virtual
driver. eSpeak NG is optional and must be installed separately to use it.

## Repository workflow

Application modules stay at the root. Tests are an importable `tests` package;
use [testing commands](./testing.md) from the repository root. Native package
recipes and vendored Debian dependencies live in `packaging/`. Architecture
contracts are recorded in [architecture](./architecture.md) and
[decision 0001](./decisions/0001-desktop-boundaries.md).

Keep downloaded models, venvs and generated `dist/` output out of source
changes. Update tests at the boundary being changed: controller lifecycle,
provider stream, subprocess cleanup, device routing or UI behavior. Test doubles
should preserve cancellation and backpressure semantics.

Changes to module names or deployment paths require updating both package
builders and source launchers. Changes to runtime readiness need explicit
consideration of existing per-user caches and manifests. Follow
[release procedures](./releasing.md) for distributable artifacts and
[troubleshooting](./troubleshooting.md) for startup/runtime diagnostics.
