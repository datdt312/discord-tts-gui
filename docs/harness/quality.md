# Quality status and evidence

## What a check proves

| Check | Establishes | Does not establish |
| --- | --- | --- |
| `tools/check_repo.py` | Required docs/navigation, Python syntax, package manifests and selected import boundaries | Runtime behavior or native compatibility |
| Regression suite | Controller/runtime behavior under controlled provider and device boundaries | Microsoft availability or hardware voice quality |
| Real FFmpeg tests | Local codec streaming and process cleanup | Actual PortAudio/PulseAudio playback |
| Offscreen Qt checks | Widget layout, editing, callbacks and event handling | Desktop compositor/accessibility behavior on every OS |
| DEB extraction/startup | Package contents and local runtime smoke behavior | Installation on each supported distribution |
| Native build/`--check` | Build output/dependencies on the selected runner | Driver installation, real devices or model quality |

## Known gaps

- Native Windows/macOS builds and real VB-CABLE/BlackHole output need their target OSes.
- Model download/provisioning needs a live network; fake SDK tests do not prove upstream wheel availability.
- First-audio latency and audible quality depend on the machine/model/service and need measurement/listening.
- Signing/notarization is not configured for desktop archives.
- No application license has been selected by the owner.
- A workflow file does not prove that a hosted workflow has run successfully.

## Recording evidence

Use the current command output, not a copied count from an older plan. State
pass/fail/skip separately and identify the environment. If a check is unavailable,
record the constraint and the remaining acceptance step. Do not turn a gap into
a claim of support by relabeling a mock as a native test.

[Testing](../testing.md) defines automated/manual checks; [releasing](../releasing.md)
defines artifact verification. Historical test counts remain only in archived
execution records.
