# Documentation index

These guides describe the maintained application. Read the smallest relevant
section, then check the implementation/tests it references. Historical plans
are background records, not current operating instructions.

| Need | Start here |
| --- | --- |
| Install, choose voices, understand platform differences | [Product](product.md) and [root README](../README.md) |
| Understand the controller, audio pipelines or private runtime | [Architecture](architecture.md) |
| Prepare a development environment | [Development](development.md) |
| Choose automated checks or run native acceptance tests | [Testing](testing.md) |
| Build a package or prepare a release | [Releasing](releasing.md) |
| Diagnose model, audio or startup failures | [Troubleshooting](troubleshooting.md) |
| Connect your Git remote | [Git setup](GITHUB_SETUP.vi.md) |
| Work with an agent and keep evidence | [Harness guide](harness/README.md) |
| Understand lasting implementation tradeoffs | [Decision 0001](decisions/0001-desktop-boundaries.md) |
| Track a substantial task | [Execution plans](plans/README.md) |

## Maintaining this knowledge

The owner of a change updates the affected contract and its tests together.
Prefer links to existing explanations over copied instructions. If a statement
is no longer supported by code or verification, correct it or label the gap.
Do not treat a successful mock, offscreen render or generated build plan as
proof that native hardware or an unpublished artifact works.
