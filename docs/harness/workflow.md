# Change workflow

## 1. Establish the task

State the requested outcome and observable acceptance behavior. Inspect the
working tree before edits; preserve unrelated user changes. Read the applicable
[AGENTS.md](../../AGENTS.md) and only the relevant technical/scoped guides.

For a small edit, proceed directly. For work with several dependent steps,
create a short [execution plan](../plans/README.md) with the scope, decisions,
verification and remaining gaps. A plan records work; it does not create an
extra approval gate beyond the user's request or environment permissions.

## 2. Investigate and implement

Locate the boundary responsible for the behavior. Reproduce failures where
possible and add an observable regression before changing behavior. Prefer
provider/device doubles around external services while exercising actual
control flow, subprocesses and decoding locally.

Keep UI state on the UI thread and retain the [runtime contracts](invariants.md).
Avoid unrelated refactors or dependency changes. Do not edit bundled libraries
as a workaround for first-party logic.

## 3. Verify at the right scope

Start with the affected test modules from [testing](../testing.md), then run:

```bash
python tools/check_repo.py
```

Broad or boundary changes also run the full suite. Packaging changes run package
and native-build-plan checks. Use a native runner or machine for claims about
Windows/macOS binaries. Streaming/hardware/manual acceptance has its own evidence;
record skipped or unavailable checks explicitly.

## 4. Keep the repository coherent

Update directly affected docs and decision records. Keep generated files and
local state out of source control. Review diff/whitespace and use the explicit
[export command](../../tools/export_source.py) for a handoff.

A completed task reports:

- What the user can now observe and why the change was made.
- Which commands were run and their actual results, including skips.
- Known limitations, remaining native checks and any external blocker.
- The concrete files/artifacts to review.

Pushes, releases and visibility changes happen only when the user's task
includes them. A local commit or source ZIP is not a hosted repository.
