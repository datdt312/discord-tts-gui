# Building and releasing

The current package version is `1.3.0`. Linux Debian packages and native frozen
desktop bundles use different dependency models. Build from a clean checkout
with the [test suite](./testing.md) passing for the applicable platform.

## Linux Debian package

The Debian builder requires Python 3.10+ and `dpkg-deb`:

```bash
python3 packaging/build_deb.py
dpkg-deb --info dist/discord-tts-gui_1.3.0_all.deb
sha256sum -c dist/SHA256SUMS
```

The output is an architecture-independent `.deb` plus `dist/SHA256SUMS`.
`SOURCE_DATE_EPOCH` controls staged file timestamps. The package includes
application sources and explicitly vendored pure Python dependencies;
development environments and model caches are excluded.

APT supplies Python, Qt, Tk, aiohttp, FFmpeg, eSpeak NG and PulseAudio utilities.
The package supports PyQt6 or the PyQt5 fallback available on Ubuntu 22.04 /
Mint 21. Installation does not run pip or fetch models. Optional AI setup
remains a separate per-user action after launch.

On a disposable target desktop, install and inspect the packaged runtime:

```bash
sudo apt install ./dist/discord-tts-gui_1.3.0_all.deb
discord-tts-gui --check
discord-tts-gui
```

The program installs into `/usr/share/discord-tts-gui` and launches through
`/usr/bin/discord-tts-gui`. Review upgrade behavior from a prior package and
source installation; close old windows before comparing versions.

## Native Windows and macOS bundles

Build on the destination OS and architecture using Python 3.12:

```bash
python -m pip install -r requirements-build.txt
python packaging/build_desktop.py
```

The builder uses PyInstaller onedir output, then stages only the bundle,
self-contained [user guide](../packaging/README.desktop.md), requirements references
and dependency notices. The user guide is also the installed DEB README;
developer documentation stays in the source tree. Artifacts are named
`discord-tts-gui-1.3.0-<target>-<architecture>.zip` with a `.sha256` sidecar.
Windows contains `Discord TTS GUI.exe`; macOS contains `Discord TTS GUI.app`.
The Windows/macOS bundles include Qt, FFmpeg, PortAudio and uv. They exclude
the optional neural SDK, private interpreter, model weights and audio drivers.

Inspect either platform's plan on any host without build dependencies:

```bash
python packaging/build_desktop.py --target windows --plan
python packaging/build_desktop.py --target macos --plan
```

`--target` selects a recipe, not a cross compiler; foreign-host builds fail.
The builder also has a Linux frozen archive recipe, while the CI Linux
deliverable is the `.deb`. Neural setup inside a frozen bundle uses uv and
managed Python 3.12 rather than treating the GUI executable as Python.

After building, run the frozen executable with `--check`, then follow the
manual acceptance steps in [testing](./testing.md). Check VB-CABLE on Windows
and BlackHole on macOS. Test both macOS architectures independently. Source
tests and a valid build plan do not establish that native binaries, SDK setup
or hardware playback work on a target system.

## GitHub Actions and publication

[The workflow](../.github/workflows/build.yml) runs manually through
`workflow_dispatch` or when a `v*` tag is pushed. It builds a Linux `.deb`,
Windows x86_64 ZIP, macOS ARM64 ZIP and macOS Intel ZIP, then uploads workflow
artifacts and checksums. It does not create or publish GitHub Releases.
Artifacts exist only after their jobs complete successfully.

For a version change, synchronize `VERSION` in both builders and the version
reported by `packaging/desktop_entry.py`; update user-facing artifact names.
Run packaging tests and inspect staged files before tagging. Download the
successful CI artifacts, verify checksums and complete target-system checks
before publishing them through the repository's chosen release process.

Signing and macOS notarization credentials are not configured. Native bundles
are unsigned; assess OS launch prompts during acceptance. Keep notices from
`packaging/VENDORED.txt`, `packaging/copyright` and `packaging/licenses/` with
artifacts. The repository has no chosen application license grant; dependency
notices do not decide licensing for original application code.
