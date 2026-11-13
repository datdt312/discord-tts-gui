> Historical implementation record. Current instructions are in [the documentation index](../../README.md).

# Click-to-install Linux package

**Goal:** Deliver an actual single-file installer for Ubuntu/Kubuntu 22.04+ and Linux Mint 21+ (Python 3.10+), with a normal applications-menu launcher.

**Architecture:** An architecture-independent `.deb` installs the existing Python application, a system-Python launcher, a desktop entry and an icon. Bundle the pure Python edge-tts, certifi, tabulate and typing_extensions sources with their licenses. Let the distro install python3-aiohttp, Tk, FFmpeg, eSpeak and PulseAudio utilities. Do not copy the development virtual environment or require pip during installation. No maintainer script runs application code as root or modifies user home directories.

**Scope:** Ubuntu/Debian-family package, not a universal Linux binary. First installation may need Internet to obtain distro dependencies; online speech still requires Internet. The package uses a distinct desktop ID/name to avoid the old per-user launcher hiding the packaged app. Keep source installation available.

- [x] Write failing package tests: build/extract real `.deb`, check dependencies, bundled source/licenses, executable launcher and icon/desktop paths, no virtualenv/cache/absolute developer paths, and relocated launcher diagnostics.
- [x] Add vendored pure Python sources and provenance, launcher assets, Vietnamese instructions, and a repeatable build script.
- [x] Build the deliverable and checksum; validate desktop metadata, compilation and bundled SDK imports; run full unittest suite.
- [x] Review packaging for target Python compatibility, missing runtime files and upgrade/launcher conflicts. Document limits of verification on the available Ubuntu host.

**Verification:** All 42 tests pass, including 7 real-package integration tests. Desktop validation, shell syntax, Python compilation and Python 3.10 AST parsing pass. Extracted launcher diagnostics import bundled edge-tts 7.3.1 successfully using the available installed SDK environment for native aiohttp. Rebuilding produces byte-identical `.deb` output. Independent package review found no important/critical blocker.

**Limits:** The isolated host lacks system python3-aiohttp, and no system installation was performed. Xvfb GUI smoke was attempted but the sandbox blocks local X11 socket creation/connection (Operation not permitted). Actual dependency installation, menu launch and audio playback on target Kubuntu/Mint releases remain unverified.

No Git metadata is available. Build/test artifacts remain in this writable workspace; do not install into the host system.
