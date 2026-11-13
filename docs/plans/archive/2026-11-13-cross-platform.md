> Historical implementation record. Current instructions are in [the documentation index](../../README.md).

# Linux, Windows and macOS desktop support

The user requests the existing Qt/VieNeu application on all three desktop OSes.
Keep Linux PulseAudio routing; Windows/macOS target user-installed virtual audio
endpoints (VB-CABLE/BlackHole) through PortAudio. Do not silently send TTS to the
system speaker when no virtual endpoint is selected. Keep restart/cancel semantics.

Independent domains: portable PCM output/decoder; neural paths/process management
and frozen Python bootstrap; controller/UI integration and per-OS packaging.

- Portable audio module enumerates/selects devices and streams decoded stereo
  PCM to selected output, supports cancellation and optional speaker preview.
- Platform UI shows output selector/connect/disconnect and driver guidance;
  Linux retains create/remove/mix controls. Portable real-mic mixing is handled
  by existing external virtual routing software and is explicitly unavailable
  in this app version (no misleading enabled controls).
- Use correct per-user data paths, Windows venv Scripts/python.exe, and correct
  process-tree cancellation on Windows. Frozen builds bundle uv for first-use
  private Python provisioning, preserving one Download action for neural setup.
- FFmpeg is resolved from PATH or imageio-ffmpeg resources. Windows/macOS builds
  include FFmpeg, Qt and PortAudio, but not virtual audio drivers/model weights.
- Native Linux .deb remains supported; add Windows .exe folder/zip and macOS
  .app/zip native build scripts plus GitHub Actions matrices. Build binaries on
  their own OS. No claim of native Windows/macOS verification from Linux.
- Add one-click source launchers as an immediately usable cross-platform source
  distribution, GitHub setup metadata/docs, and refresh the prepared public Git
  snapshot/bundle. Keep application license unset as requested previously.

Verification: existing Linux regressions; portable audio stream/cancel/error
fixtures; mocked Windows/macOS path/process tests; Qt routing UI; package content,
CI/build manifests and source archive. Native Windows/macOS builds remain for CI.

## Final verification

Full suite: 191 tests passed, with 3 skips (2 legacy Tk display classes and
1 native Windows Job Object test). Real FFmpeg exercises streaming/cancellation;
PortAudio uses device doubles. Real offscreen Qt covers Windows/macOS routing
UI and Linux regressions. Packaging plans and Linux .deb extraction/startup
checks pass. Review fixed worker import isolation, Windows process trees,
private pip destinations, unexpected stream completion and lost cleanup errors.

Windows/macOS native artifacts cannot be built/tested here because this host
is Linux and native build dependencies are unavailable. The included GitHub
Actions matrix runs native builds and bundle --check on their proper OSes.
Source launchers + source ZIP are provided immediately.
