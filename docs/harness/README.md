# Engineering harness

This repository uses small instruction entry points, discoverable technical
guides and executable checks so a contributor can find the right context,
change one boundary and verify the result without reconstructing a chat log.
It is a repository workflow, not an agent SDK or an application dependency.

## Where to look

| Artifact | Purpose |
| --- | --- |
| [AGENTS.md](../../AGENTS.md) | Short shared working agreement |
| [Agent setup](agents.md) | Codex, Claude and Antigravity entry points |
| [Architecture](../architecture.md) | Modules, ownership and data flow |
| [Invariants](invariants.md) | Contracts and regression locations |
| [Workflow](workflow.md) | Scope, implement, verify and hand off |
| [Quality status](quality.md) | Evidence categories and known gaps |
| [Plans](../plans/README.md) | Durable records for multi-step work |
| [Repository checker](../../tools/check_repo.py) | Documentation, syntax and boundary checks |
| [Source exporter](../../tools/export_source.py) | Explicit clean handoff, independent of local Git metadata |

## Feedback loops

1. A small change gets a focused regression/check.
2. The repository checker catches broken navigation, syntax and package boundary drift.
3. Broad changes run the regression suite; package changes exercise extraction and startup checks.
4. Native CI builds on the target OS. Real audio/model acceptance remains a separate step.
5. A discovered recurring mistake becomes a focused regression or a concise contract, not another long global prompt.

Read only what the task needs. Keep detailed procedures in their relevant guide;
keep always-loaded instructions short. Archived execution notes can explain a
decision but must not silently override maintained docs or current user intent.

This design is informed by the repository-legibility and feedback-loop ideas in
[OpenAI's harness engineering discussion](https://openai.com/index/harness-engineering/).
The concrete boundaries and checks here come from this project's code.
