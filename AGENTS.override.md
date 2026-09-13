# AGENTS.override.md

This file is the **context layer** for the Pi harness (the `pi` CLI, and the
`associate` non-coding harness modelled on it) when it runs inside this repo.
Pi's CONTEXT loader concatenates `AGENTS.md` or `CLAUDE.md` from its user-level
config directory (see Pi's own docs), each parent directory, and the working
directory — but an `AGENTS.override.md` present in a directory replaces that
directory's `AGENTS.md`/`CLAUDE.md` entry outright rather than adding to it.
That is why this repo ships this file instead of an `AGENTS.md`: Pi must
**not** inherit `CLAUDE.md` (the Claude Code guidance file) — the two harnesses
read the same repository very differently, and `CLAUDE.md` assumes a coding
session with full repo-write authority that Pi's non-coding lane does not have.

The identity and behavioral bounds for that lane — who Pi is here, what it may
and may not do — live one layer up, in Pi's **system prompt** file,
[`.pi/SYSTEM.md`](.pi/SYSTEM.md). That file replaces Pi's default
coding-assistant system prompt entirely. This file is project *context* only:
what the repo is and how it is laid out, not who is reading it.

## What this project is

`substack-cli` is an **agent-first CLI to manage a Substack publication and
account** — publish and schedule posts, read posts and comments, react to
posts/comments, and read the account feed. Unofficial community tool, not
affiliated with Substack.

Five nouns are wired on disk: `account`, `post`, `comment`, `reaction`,
`feed` (see [Substack surface](#substack-surface) below). The AgentCulture
sibling baseline this repo was scaffolded from (`culture-agent-template`) is
still underneath: an agent-first CLI skeleton (`whoami`, `learn`, `explain`,
`overview`, `doctor`, `cli overview`), a mesh identity, the vendored skill
kit, and a build/deploy baseline. If you are asked where posts, comments, or
reactions are implemented, point at `substack_cli/cli/_commands/` and
`substack_cli/substack/` rather than inferring from the project description
alone — and if a question assumes a verb this repo does not have (e.g.
subscriber management or audience statistics), say so rather than guessing at
one.

It is a sibling to [`guildmaster`](https://github.com/agentculture/guildmaster)
(the skills supplier), [`steward`](https://github.com/agentculture/steward)
(alignment), and [`teken`](https://github.com/agentculture/teken) (the CLI
scaffolder this package is cited from).

## Four harnesses, four files, no shared base

This repo's root carries one prompt file per harness, each read by exactly
one of them — there is deliberately no shared `AGENTS.md` base for them to
cascade from:

- **Claude Code** reads [`CLAUDE.md`](CLAUDE.md).
- **Pi / associate** reads this file (`AGENTS.override.md`) for context, plus
  [`.pi/SYSTEM.md`](.pi/SYSTEM.md) for its system prompt.
- **colleague** reads [`AGENTS.colleague.md`](AGENTS.colleague.md) (the start
  of colleague's own cascade — see that file).
- **Qwen Code** reads [`QWEN.md`](QWEN.md).

If you are reading this as a human, `CLAUDE.md` is the fullest write-up of the
repo's conventions and is the one to read first; the other three exist to keep
each non-Claude harness from silently inheriting Claude-specific instructions
it cannot act on the same way.

`.pi/skills` is a relative symlink onto `.claude/skills`, so a Pi session sees
the same single skill tree as the other three harnesses — the skills are not
duplicated per harness.

## Identity

Declared in `culture.yaml`:

```yaml
agents:
- suffix: substack-cli
  backend: claude
```

This repo's *mesh* resident runs on `backend: claude`, so `CLAUDE.md` is the
live resident prompt. A Pi session working in this clone is a **local tool
session**, not the mesh resident — it reads this file and `.pi/SYSTEM.md`
regardless of what `culture.yaml` declares, and running `pi` here neither
requires nor changes that declaration.

(A sibling that wants `associate` as its *mesh* resident declares
`backend: colleague` with `model: associate`. That is a per-repo choice; this
one does not ship it.)

## Substack surface

Public read verbs (`post list`/`get`, `comment list`, `reaction list`) are
stdlib HTTP with no session. Owner verbs (`post publish`/`schedule`/
`unpublish`/`delete`, `comment reply`/`delete`, `reaction add`/`remove`,
`feed read`, `account whoami`) shell out to the `webglass` binary (sibling
project `webglass-cli`) and need `$SUBSTACK_WEBGLASS_SESSION` naming a
session whose browser is logged in to Substack; until `webglass-cli` can
create such a session (`agentculture/webglass-cli#17`), owner verbs exit `2`
with a hint. Every endpoint the CLI calls must appear in
[`docs/api/substack-endpoints.md`](docs/api/substack-endpoints.md) before it
ships — that is the only record of what Substack's unpublished API does.

## Layout (what you can read/find/summarize here)

```text
substack_cli/             agent-first CLI (cited from teken's python-cli reference)
  cli/                    parser, error/output contract, _commands/ (verbs)
  substack/               domain layer: http.py, webglass.py, render.py, body.py
  explain/                markdown catalog for `explain`
tests/                    CLI smoke, introspection, harness-registry, script tests
tests/fakes/              fakes for the Substack domain layer
scripts/                  scan-secrets.py, harness-smoke.py (both CI gates)
.claude/skills/           vendored guildmaster skill kit (cite-don't-import)
docs/                     skill provenance, four-harness contract/verification,
                          docs/api/substack-endpoints.md (observed endpoint map)
culture.yaml              mesh identity (suffix + backend)
.github/workflows/        tests.yml (test/lint/harness-smoke/version-check), publish.yml
```

Useful read-only commands for answering questions about the tree:
`uv run substack whoami`, `uv run substack learn`, `uv run substack doctor`,
`uv run substack explain <path>` — every one supports `--json`, writes results
to stdout and diagnostics to stderr, and changes nothing.

## Conventions worth knowing before you answer a question about this repo

- **The installed binary is `substack`, not `substack-cli`.** `[project.scripts]`
  names the command `substack`, while the CLI's own help output, the explain
  catalog and most prose say `substack-cli` (the distribution name). If someone
  reports that `substack-cli …` "does not exist", that mismatch is why — quote
  it rather than guessing at a broken install.
- The CLI has **no third-party runtime dependencies** by design (it is cited
  from teken's `python-cli` reference); even `culture.yaml` is parsed by hand
  in `_commands/whoami.py` rather than importing PyYAML. If a question assumes
  a library is available at runtime, check `pyproject.toml` before agreeing.
- Results go to **stdout**, errors and diagnostics to **stderr**, never mixed;
  exit codes are `0` success, `1` user error, `2` environment error, `3+`
  reserved. Errors print an `error:` line and a `hint:` line — no tracebacks.
- The vendored skills under `.claude/skills/` are cited **verbatim** from
  guildmaster — never propose editing their scripts; the fix belongs upstream
  (`docs/skill-sources.md` has the re-sync procedure).
- Every PR bumps the version (`version-bump` skill); CI's `version-check` job
  blocks merge otherwise.
- Four prompt files state overlapping conventions. If you spot one contradicting
  another, **report the contradiction** — do not pick a winner silently; the
  repo treats harness-config drift as a defect (CI's `harness-smoke` job exists
  for exactly that).
- This file describes the repo **as it exists on disk today**. If you are
  asked to update it, keep claims grounded in checked-in reality.
