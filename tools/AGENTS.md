# Repository tooling scope

Apply the [root contract](../AGENTS.md).

- Keep checker/exporter standard-library only, offline and usable before app dependencies are installed.
- Inspect source/AST instead of importing the GUI, SDK or audio backend during checks.
- Export an explicit source allowlist, honor private/generated exclusions and reject source symlinks.
- Preserve public certificates and third-party notices; never blanket-ignore every PEM file.
- Do not initialize/push remotes or alter user credentials as part of checking/exporting.
- Verify with `python -m unittest -v tests.test_repo_harness` and `python tools/check_repo.py`.
