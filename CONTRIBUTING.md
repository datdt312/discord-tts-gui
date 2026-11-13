# Contributing

Start with [development setup](docs/development.md), then select checks from
[testing](docs/testing.md). Agent-assisted work follows [AGENTS.md](AGENTS.md).

## A useful change

- Describe the user-visible problem and intended behavior.
- Keep UI, playback, runtime and packaging boundaries explicit.
- Add a regression when behavior changes; use controlled provider/device boundaries in automated tests.
- Update affected docs. Add a short decision record for lasting architectural choices.
- Include commands/results and remaining platform limitations in the handoff.

Use Python 3.12 for verification and retain Python 3.10 syntax compatibility in
shipped sources. Dependency changes must preserve provenance and license notices;
do not patch bundled libraries to work around application behavior.

## Before handing off

```bash
python tools/check_repo.py
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -t . -v
```

Review `git diff --check` and `git status --short`. Keep generated packages,
private audio, model caches and credentials out of commits. Repository checks
also run in CI; native packaging has a separate build workflow.

Pull requests should explain the resulting behavior, why it changed, and how
it was verified. State skips or untested native environments directly. No app
license has been selected; do not add one without the owner's instruction.
