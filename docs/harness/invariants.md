# Runtime invariants and regression map

These are maintained contracts. Test names/locations are navigation aids, not a
replacement for inspecting test assertions or running them.

| ID | Contract | Main regression boundary |
| --- | --- | --- |
| REQ-1 | One active worker, one newest pending request; replacements wait for cleanup | [Speech replacement](../../tests/test_speech_replacement.py) |
| REQ-2 | Late status/error/done events from an old generation cannot reset the new reading | [Speech replacement](../../tests/test_speech_replacement.py) |
| REQ-3 | Stop/remove/close discard pending speech and reap work before routing teardown | [Replacement](../../tests/test_speech_replacement.py), [streaming](../../tests/test_streaming.py) |
| UI-1 | Worker notifications go through the event queue; Qt owns widget updates | [Qt controller](../../tests/test_qt_controller.py) |
| UI-2 | Progress is temporary, actions remain reachable, editor paste replaces selection | [Qt layout](../../tests/test_qt_ui.py), [controller](../../tests/test_qt_controller.py) |
| AUD-1 | Portable audio requires an explicit output; no automatic speaker fallback | [Portable output](../../tests/test_portable_audio.py), [platform UI](../../tests/test_cross_platform_ui.py) |
| AUD-2 | Decode/play can start before synthesis ends; cancellation interrupts waits and reaps workers | [Streaming](../../tests/test_streaming.py), [portable decoding](../../tests/test_portable_playback.py) |
| AUD-3 | Unexpected output completion and cleanup failures are reported, not successful playback | [Portable output](../../tests/test_portable_audio.py), [portable decoding](../../tests/test_portable_playback.py) |
| MOD-1 | Setup alone downloads; ready state requires offline verification; inference stays offline | [Neural runtime](../../tests/test_neural_runtime.py), [backend](../../tests/test_neural_backend.py) |
| MOD-2 | Model graphs/external data are adjacent regular copies; preserve the Hub cache | [Model files](../../tests/test_neural_model_files.py) |
| MOD-3 | External SDK workers use their private environment; frozen scripts live under workers/ | [Neural backend](../../tests/test_neural_backend.py), [desktop packaging](../../tests/test_desktop_packaging.py) |
| MOD-4 | Unrelated output selection/refresh must not cancel model setup | [Platform UI](../../tests/test_cross_platform_ui.py) |
| PKG-1 | Native/DEB builders include the same production modules and retain notices | [Desktop packaging](../../tests/test_desktop_packaging.py), [DEB packaging](../../tests/test_packaging.py) |
| REPO-1 | Export excludes generated/private files while preserving source, agent docs and public CA certificates | [Repository harness](../../tests/test_repo_harness.py) |

Keep this map synchronized when moving a boundary. Add observable regressions for
new failure classes instead of mechanically asserting that an implementation
contains a particular line.
