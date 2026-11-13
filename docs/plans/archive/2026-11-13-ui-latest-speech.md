> Historical implementation record. Current instructions are in [the documentation index](../../README.md).

# Compact UI and replace-current-speech behavior

**User requirements:** Keep controls usable when download/status content grows; hide download information after completion; reorganize buttons; Speak while reading stops the old request and speaks current text; changing engine or voice while reading restarts with current text/selection; default engine is VieNeu-TTS, including first launch before setup.

**Layout:** A scrollable content area contains text, engine/voice controls, temporary download progress and collapsed audio settings. A fixed footer holds Speak/Restart, Stop and virtual mic creation/status. Grid weights and full-width device selectors avoid the previous packed rows exceeding the window. Status is concise; full error details remain in the error dialog. The download frame disappears on terminal setup states; installed model status remains brief, with repair/download in optional settings.

**Playback:** One active worker and one pending replacement, with newest request replacing any older pending request. Cancel old work first, then start the pending snapshot only after worker exit. Request-tagged worker events prevent old completion/status/error messages from changing the new job. Stop, Remove and Close clear pending speech. Engine/voice changes restart only active speech, not idle edits or model setup. Offline eSpeak synthesis must also observe cancellation.

**Independent implementation:** desktop_ui.py owns layout only; app.py owns request control, event routing, progress visibility and existing routing callbacks. The layout builder signature is build_ui(ui, bind_text_shortcuts, engine_choices), with VieNeu first. New callbacks on_engine_changed/on_voice_changed are provided by app.py. Existing widget attributes are preserved. Source and native packages include desktop_ui.py.

- [x] Regression tests for newest-request wins, no overlapping playback, stale events, engine/voice change, Stop while replacement pending and cancelable offline synthesis.
- [x] Qt layout with persistent actions, default VieNeu and actual offscreen geometry checks. Legacy Tk checks remain display-dependent.
- [x] Implement generation-tagged event routing and serial restart handling; hide completed progress and compact status/model hints.
- [x] Full tests, independent review, and updated 1.2.0 .deb/documentation.

## UI library steering

The user requested a more polished UI library during implementation. The default
frontend is now Qt, with qt_ui.py adapting the existing controller. PyQt6 is
preferred; PyQt5 preserves Ubuntu 22.04 / Mint 21 compatibility. The native
package declares an alternative dependency rather than downloading Python
binaries at startup. Qt offscreen rendering is available in this environment,
allowing actual geometry, editing and controller tests without X11 sockets.
The legacy Tk builder remains for existing test fixtures.

## Final verification

130 tests passed with two legacy Tk display classes skipped. After the final
card spacing adjustment, all 13 real Qt UI/controller tests and all 8 package
tests passed again. The package smoke test extracts the actual .deb, starts
the default Qt frontend and closes it cleanly. Source venv startup also passed.
Real Qt screenshots were rendered and inspected. The Qt5 fallback and actual
installation/playback on individual Kubuntu/Mint versions remain unverified.

Artifact: dist/discord-tts-gui_1.2.0_all.deb
Screenshot: dist/discord-tts-gui-1.2.0.png
