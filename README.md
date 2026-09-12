# substack-cli

Agent-first CLI to manage a Substack publication and account: publish and
schedule posts, read posts and comments, run audience and post statistics, and
manage subscribers. Unofficial community tool, not affiliated with Substack.

## Status

**Scaffold.** The Substack surface above is the goal, not what ships today.
What is on disk now is the AgentCulture sibling baseline this repo was
scaffolded from ([`culture-agent-template`](https://github.com/agentculture/culture-agent-template)):
an agent-first CLI skeleton, a mesh identity, the vendored skill kit, and a
buildable/deployable package baseline. Everything documented below is
checked-in reality; the post/subscriber/stats verbs are the work ahead.

## What you get today

- **An agent-first CLI** cited from [teken](https://github.com/agentculture/teken)
  (`afi-cli`) — the runtime package has no third-party dependencies.
- **A mesh identity** — `culture.yaml` (`suffix` + `backend`) and the matching
  resident prompt file (`CLAUDE.md`, since this repo runs `backend: claude`).
  The mesh resident is one of **two separate selections** over this clone —
  see [Two selections, not one](#two-selections-not-one) below.
- **Four harness prompt files**, one per agent harness, each read by exactly
  one of them (see [Prompt files by harness](#prompt-files-by-harness) below).
  All four harnesses are usable interactively regardless of which one
  `culture.yaml` names as the mesh resident.
- **The canonical guildmaster skill kit** (19 skills) under `.claude/skills/`,
  vendored cite-don't-import. See [`docs/skill-sources.md`](docs/skill-sources.md).
- **A build + deploy baseline** — pytest, lint, the agent-first rubric gate, a
  committed-secret scanner, a per-harness smoke check, and PyPI Trusted
  Publishing wired into GitHub Actions.

## Quickstart

```bash
uv sync
uv run pytest -n auto                 # run the test suite
uv run substack whoami                # identity from culture.yaml
uv run substack learn                 # self-teaching prompt (add --json)
uv run teken cli doctor . --strict    # the agent-first rubric gate CI runs
```

## CLI

The installed command is **`substack`** (`[project.scripts]` in
`pyproject.toml`); `substack-cli` is the distribution name and the name the
help output prints. `python -m substack_cli` works too.

| Verb | What it does |
|------|--------------|
| `whoami` | Report this agent's nick, version, backend, and model from `culture.yaml`. |
| `learn` | Print a structured self-teaching prompt. |
| `explain <path>` | Markdown docs for any noun/verb path. |
| `overview` | Read-only descriptive snapshot of the agent. |
| `doctor` | Check the agent-identity invariants (prompt-file-present, backend-consistency). |
| `cli overview` | Describe the CLI surface itself. |

Every command supports `--json`. Results go to stdout, errors/diagnostics to
stderr (never mixed). Exit codes: `0` success, `1` user error, `2` environment
error, `3+` reserved.

## Prompt files by harness

Four harnesses, four root files, no shared base — each file is read by
exactly one harness:

| Harness | File(s) |
|---------|---------|
| Claude Code | [`CLAUDE.md`](CLAUDE.md) |
| Pi / associate | [`AGENTS.override.md`](AGENTS.override.md) + [`.pi/SYSTEM.md`](.pi/SYSTEM.md) |
| colleague | [`AGENTS.colleague.md`](AGENTS.colleague.md) |
| Qwen Code | [`QWEN.md`](QWEN.md) |

**Claude Code** — `CLAUDE.md` is the fullest write-up of the repo's
conventions; read it first.

**Pi / associate** — `AGENTS.override.md` replaces this directory's
`AGENTS.md`/`CLAUDE.md` in Pi's context layer, so Pi does not inherit
`CLAUDE.md`. `.pi/SYSTEM.md` replaces Pi's default system prompt with the
non-coding `associate` identity (read/find/summarize only).

**colleague** — colleague's prompt cascade is `AGENTS.md` →
`AGENTS.colleague.md` → `AGENTS.colleague.<model>.md`. This repo ships only
the middle layer: there is no `AGENTS.md` (a shared base across harnesses was
considered and rejected) and no per-model override file.

**Qwen Code** — Qwen Code reads `QWEN.md` and `AGENTS.md`; since there is no
`AGENTS.md`, `QWEN.md` is its sole source of guidance.

There is intentionally **no `AGENTS.md`** at the root — each harness gets an
unrelated file rather than cascading from a shared base.

## Two selections, not one

It is tempting to read "switch harness" as one decision. It is actually two,
and this repo's layout exists partly to keep them separate:

1. **The interactive harness** — which binary you run (`claude`, `pi`,
   `colleague`, `qwen`). `cd` into the clone and run any of them; all four
   are live simultaneously, and none of them requires editing a file or
   flipping a switch. A harness can be force-selected for one invocation
   (e.g. a CI smoke check) without ever touching `culture.yaml` — see
   [`docs/automation-contract.md`](docs/automation-contract.md).
2. **The mesh resident** — the single `backend` `culture.yaml` declares,
   which is what the Culture daemon starts and what `steward doctor`
   checks. `guild harness use <name>` changes only this.

`culture.yaml`'s `backend` affects (2) only. It never affects which harness
you can invoke interactively in (1). See
[`docs/harness-selection.md`](docs/harness-selection.md) for the full
writeup.

## Development

```bash
uv run pytest -n auto                       # full suite
uv run pytest tests/test_cli.py -v          # one file
uv run black substack_cli tests             # CI runs --check
uv run isort substack_cli tests             # CI runs --check-only
uv run flake8 substack_cli tests            # line length 100
uv run bandit -c pyproject.toml -r substack_cli
python3 scripts/scan-secrets.py             # committed-secret gate
uv run python scripts/harness-smoke.py --stage all --require config
```

Every PR bumps the version in `pyproject.toml` (CI's `version-check` job blocks
merge otherwise). See [`CLAUDE.md`](CLAUDE.md) for the full conventions (CLI
error/output contract, the `cicd` PR lane, worktree layout, deploy setup).

## License

Apache 2.0 — see [`LICENSE`](LICENSE).
