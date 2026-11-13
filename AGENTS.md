# Repository working agreement

This is a Python/Qt desktop TTS application. Keep this guidance shared by Codex,
Claude Code and Antigravity. User instructions for the current task take
precedence over this repository guidance.

## Find the relevant context

- Product behavior: [docs/product.md](docs/product.md).
- Module boundaries: [docs/architecture.md](docs/architecture.md).
- Setup and commands: [docs/development.md](docs/development.md).
- Test selection: [docs/testing.md](docs/testing.md).
- Packaging/version changes: [docs/releasing.md](docs/releasing.md).
- Workflow and invariants: [docs/harness/README.md](docs/harness/README.md).
- For edits inside `tests/`, `packaging/`, `tools/` or `docs/`, read that directory's `AGENTS.md`.

Read what the task needs; do not load every document or archived plan for small
edits. The implementation and executable checks establish behavior. Correct
stale docs when a change proves them wrong.

## Preserve these contracts

- One active speech worker and at most one pending replacement. Only the latest request may update the UI.
- Stop/remove/close cancel pending playback. Unrelated output selection or refresh must not cancel model downloads.
- Keep GUI updates on the UI thread; communicate worker results through the event queue.
- Do not silently switch engines/voices or route portable audio to default speakers.
- Normal Speak must not download models. Only explicit model setup provisions the private runtime.
- Preserve model caches and system audio defaults; remove only app-owned routing.
- Frozen workers execute from `workers/`, away from bundled native extensions.
- Retain Python 3.10 syntax compatibility. CI and recommended development use Python 3.12.
- Preserve vendored source/license files unless a dependency update is part of the task.

## Make and verify a change

1. Inspect the relevant implementation and regression tests.
2. For a behavior fix, reproduce it and add a meaningful failing regression where practical.
3. Make the smallest coherent change, then run affected tests.
4. Run `python tools/check_repo.py`. For broad/runtime changes run:

   ```bash
   QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -t . -v
   ```

5. Update directly affected docs. For multi-step work, maintain a record under `docs/plans/active/`; archive it when complete.
6. Report changed behavior, commands/results, skips and native-platform limitations. Mocked devices are not hardware verification.

On PowerShell set `$env:QT_QPA_PLATFORM = 'offscreen'` before unittest.
Do not add tests that merely restate a constant or implementation detail.

## Repository hygiene

- Keep app modules at the root until a scoped packaging/import migration is requested; tests belong in `tests/`.
- `dist/`, environments, caches, recordings, model weights and local credentials are not source files.
- Use `python tools/export_source.py` for a clean handoff; do not zip the entire working directory.
- Agent entry points refer to this contract instead of duplicating it.
- Do not push, publish, change visibility or create a release unless the user's task authorizes it.
- Do not invent a project license or upload downloaded model weights.
