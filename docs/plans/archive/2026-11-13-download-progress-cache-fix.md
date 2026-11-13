> Historical implementation record. Current instructions are in [the documentation index](../../README.md).

# Download progress and ONNX cache repair

**Requested:** Report model size and current download percentage; user then supplied an ONNX Runtime external-data validation failure after downloading.

**Root cause:** HF Hub 2.4 snapshot symlinks resolve graph and external weights into distinct two-character blob shards. ORT 1.31.1 rejects the companion file as escaping the graph's real directory. Reproduced with the user's installed SDK and existing cache.

- [x] Report actual bytes from Hub's public tqdm_class callback; support resume, cached completion, unknown lengths and cancellation. Percentage is explicitly per current file, not overall setup.
- [x] Add GUI progress bar, filename, percentage and MB/GB. Package install/model load/offline verification remain separate indeterminate stages.
- [x] Copy snapshot files atomically into private regular files with the same relative layout before SDK construction, in download and offline modes. Preserve shared cache; reuse unchanged materialized files.
- [x] Package 1.1.1 with the helper in native/source installers and document retry without deleting cache.

**Measured sizes:** 475.40 MB cached VieNeu fp32 files + 90.57 MB cached codec = 565,974,704 bytes. Native runtime/other cache and independent regular model copies bring expected disk use to roughly 2–3 GB, not the .deb size.

**Verification:** 101 unittest cases pass under ResourceWarning-as-error; display-dependent Tk class skipped. Independent review passed 55 targeted tests with no important/critical finding. Original ORT error reproduced; all six actual cached ONNX graphs load after staging. Actual SDK worker loaded offline, warmed up, exposed 25 presets, streamed speech over IPC into a 3.52-second 48 kHz WAV, and was reaped on close. Real HF 2.4 cached-file progress/staging chaining also verified (415,319,040-byte shared weight file). No downloads or modifications to installed/shared model cache were needed for these checks.

**Limits:** Live HTTP byte progress and the rendered Tk progress bar were not exercised against a display/network here. Actual offline synthesis is verified; perceived audio quality/hardware playback are separate listening checks.
