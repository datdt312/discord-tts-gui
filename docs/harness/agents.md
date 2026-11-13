# Codex, Claude Code and Antigravity

The repository shares one working agreement in [AGENTS.md](../../AGENTS.md).
Keep tool entry points thin so behavior does not drift between assistants.
No personal model, credential, permission or global configuration is committed.

| Tool | Entry point in this repository | Scoped guidance |
| --- | --- | --- |
| Codex | Root `AGENTS.md` | Read the relevant directory `AGENTS.md` for the task |
| Claude Code | Root `CLAUDE.md` imports `@AGENTS.md` | Directory `CLAUDE.md` imports its sibling `AGENTS.md` |
| Antigravity | Root `AGENTS.md`; `GEMINI.md` is a compatibility pointer | Root agreement explicitly routes to relevant scoped files |

## Codex

Codex discovers applicable `AGENTS.md` guidance by directory. See the
[official instructions guide](https://developers.openai.com/codex/guides/agents-md).
Open the repository root for normal work. A nested scope should add only its
local constraints, not repeat the complete root contract.

## Claude Code

The explicit `@AGENTS.md` import supports sessions that load `CLAUDE.md` and
keeps the shared instructions available even when native AGENTS discovery varies.
Claude's [memory/instruction documentation](https://code.claude.com/docs/en/memory)
describes import and version/configuration differences. Do not assume a Markdown
link alone has the same loading behavior as Claude's import syntax.

## Antigravity

Current [Antigravity rules documentation](https://antigravity.google/docs/rules/)
recognizes root `AGENTS.md`/`GEMINI.md`. It does not automatically load rules
below the selected workspace directory. The root agreement therefore tells the
agent to read the relevant local scope. Open the project root, not an arbitrary
nested folder, when working across modules. `GEMINI.md` deliberately points to
the shared contract without assuming Claude-style import semantics.

## Verify your local session

Ask the tool to identify the instruction files it loaded before a complex task.
Confirm it can locate the relevant test command and invariant. If its installed
version or enterprise configuration ignores a project entry point, explicitly
provide the shared file and consult that tool's official discovery settings.
Repository checks validate files and references; they do not launch or prove
configuration of all three assistant clients.
