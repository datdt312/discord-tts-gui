# Packaging scope

Apply the [root contract](../AGENTS.md) and [release guide](../docs/releasing.md).

- Keep DEB APP_SOURCES and desktop MODULES aligned with production files.
- Frozen worker data belongs under workers/; uv belongs under tools/ in the bundle.
- Do not include model weights, caches, environments or credentials.
- Preserve vendor sources, versions, provenance and notices; avoid incidental dependency edits.
- Build native binaries on their own OS; a plan is not a built artifact.
- Verify `tests.test_packaging` and `tests.test_desktop_packaging` when this scope changes.
