# Regression test scope

Apply the [root contract](../AGENTS.md) and [test guide](../docs/testing.md).

- Keep tests importable as tests.*; use package-qualified imports for shared fixtures.
- Resolve repository files from the repository root, not beside a moved test module.
- Exercise observable behavior with controlled provider/device boundaries; keep real codec/process checks where practical.
- Avoid external speech services, downloads and the user's live routing in automated tests.
- Skip actual OS/hardware checks explicitly when unavailable; do not replace them with misleading passing mocks.
- Run targeted tests, then `python -m unittest discover -s tests -t . -v` for broad changes.
