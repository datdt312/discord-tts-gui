# Repository cleanup and engineering harness

## Objective

Prepare a coherent public-source handoff that the owner can connect to a remote.
Preserve current application behavior while making setup, boundaries and checks
legible to humans, Codex, Claude Code and Antigravity.

## Decisions

- Keep runtime modules at root to preserve launcher/frozen worker boundaries.
- Move regressions to tests/ and use package-qualified fixture imports.
- Put maintained docs behind a short README/index; archive previous task notes.
- Use root AGENTS.md as the common contract, with native Claude/Gemini pointers
  and short scoped instruction files.
- Add standard-library repository checks and deterministic clean source export.
- Do not push or create a hosted repository; the user will connect their remote.

## Checklist

- [x] Reorganize tests and historical notes; update discovery/import paths.
- [x] Write maintained README, ignore/line-ending rules and agent entry points.
- [x] Write architecture/product/development/testing/release/troubleshooting guides.
- [x] Implement checker/exporter and their focused regression fixtures.
- [x] Validate docs, structure, source export and the full regression suite.
- [x] Refresh the independent Git handoff and report exact verification gaps.

## Verification

The prepared Git copy passed 206 tests: 203 passed and 3 skipped (legacy Tk display
classes and the native Windows Job Object check). The offline repository checker,
clean ZIP extraction/check, package documentation links and 15 harness regressions
passed. Native Windows/macOS hardware validation remains outside this Linux cleanup
task, as described in the quality guide. No remote was configured or pushed.
