# QWEN.md

This file provides guidance to Qwen Code when working with code in this
repository. Qwen Code's context loader reads exactly `QWEN.md` and `AGENTS.md`
in a directory; this repo deliberately ships only `QWEN.md` — there is no
`AGENTS.md` here (each harness gets its own file; see "Prompt files by
harness" below), so this file is the sole source of project guidance for a
Qwen Code session.

## What this project is

`substack-cli` is an **agent-first CLI to manage a Substack publication and
account** — publish and schedule posts, read posts and comments, react to
posts/comments, and read the account feed. Unofficial community tool, not
affiliated with Substack.

Five nouns are wired: `account`, `post`, `comment`, `reaction`, `feed` (see
[Substack surface](#substack-surface) below). The AgentCulture sibling
baseline this repo was scaffolded from (`culture-agent-template`) is still
underneath: the agent-first CLI skeleton (`whoami`, `learn`, `explain`,
`overview`, `doctor`, `cli overview`), a mesh identity, the vendored
guildmaster skill kit, and a buildable/deployable package baseline. Do not
assume a verb beyond those five exists (e.g. subscriber management or
audience statistics) — read the tree.

It is a sibling to [`guildmaster`](https://github.com/agentculture/guildmaster)
(the **skills supplier**), [`steward`](https://github.com/agentculture/steward)
(**alignment** — `steward doctor`, the sibling-pattern baseline), and
[`teken`](https://github.com/agentculture/teken) (the **afi-cli** "Agent First
Interface" scaffolder this CLI is cited from) within the Organic Development
framework.

## Prompt files by harness

This repo's root carries one prompt file per agent harness, each read by
exactly one of them — there is no shared base file for them to inherit from:

- **Claude Code** → [`CLAUDE.md`](CLAUDE.md) (the fullest write-up; read it
  first if you need more than fits here).
- **Pi / associate** → [`AGENTS.override.md`](AGENTS.override.md) for context,
  plus [`.pi/SYSTEM.md`](.pi/SYSTEM.md) for its system prompt.
- **colleague** → [`AGENTS.colleague.md`](AGENTS.colleague.md).
- **Qwen Code** → this file.

`.qwen/skills` is a relative symlink onto `.claude/skills`, so a Qwen Code
session loads the same one skill tree the other harnesses are wired to — no
forked copies. (Wiring is shared; loading is not universal — colleague 1.76.0
loads 0 of the 19 for upstream reasons, see `docs/harness-verification.md`.)

## Identity

Declared in `culture.yaml`:

```yaml
agents:
- suffix: substack-cli
  backend: claude
```

`backend: claude` fixes the *mesh resident* prompt file to `CLAUDE.md` — the
mesh runtime reads that file, not this one. A Qwen Code session working in this
clone is a separate, local tool session; it reads `QWEN.md` regardless of what
`culture.yaml` declares, and running Qwen Code here neither requires nor
changes that declaration. The declaration and the resident prompt together
satisfy the two invariants `steward doctor` verifies:
**prompt-file-present** and **backend-consistency** (`claude` ↔ `CLAUDE.md`).

## Commands

```bash
uv sync                                  # install deps (dev group included)

uv run substack whoami                   # note: the binary is `substack`
uv run substack learn --json
uv run substack doctor

uv run pytest -n auto                    # full suite, parallel
uv run pytest tests/test_cli.py -v       # one file
uv run pytest tests/test_cli.py::test_whoami_text -v   # one test
uv run pytest -n auto --cov=substack_cli --cov-report=term   # coverage (fail_under=60)

uv run black substack_cli tests          # CI runs --check
uv run isort substack_cli tests          # CI runs --check-only
uv run flake8 substack_cli tests         # line length 100
uv run bandit -c pyproject.toml -r substack_cli
# markdownlint-cli2 is npm, not uv: npm install -g markdownlint-cli2@0.21.0
markdownlint-cli2 "**/*.md" "#node_modules" "#.local" "#.claude/skills" "#.teken"
python3 scripts/scan-secrets.py          # committed-secret / non-localhost-endpoint gate
uv run teken cli doctor . --strict       # the agent-first rubric gate CI enforces
uv run python scripts/harness-smoke.py --stage all --require config
```

**Binary vs. prog name.** `[project.scripts]` installs the command as
**`substack`**, while the argparse `prog` (and every doc, catalog entry and
help string) says `substack-cli`. Prose of the form `substack-cli whoami` is
the *logical* command name; what you actually type is `uv run substack whoami`
(or `python -m substack_cli`).

## The CLI contract

The CLI is cited (cite-don't-import) from teken's `python-cli` reference
(`teken cli cite`), so the runtime package has **no third-party dependencies**;
`teken` (a.k.a. `afi-cli`) is a dev dependency only, and `culture.yaml` is
parsed by hand in `_commands/whoami.py` rather than pulling in PyYAML. Keep it
that way when you add domain verbs — a Substack HTTP client belongs behind an
optional extra or in the stdlib, not in `dependencies`.

Verbs today: `whoami`, `learn`, `explain <path>`, `overview`, `doctor`,
`cli overview`, plus the five Substack nouns — see
[Substack surface](#substack-surface) below.

The wiring that spans files:

- `substack_cli/cli/__init__.py` — parser, dispatch, error contract.
  `_CliArgumentParser` overrides `.error()` so even *argparse* failures
  (unknown verb, missing arg) render as the structured `error:` / `hint:` pair
  and exit `1`, not argparse's default exit `2`. Parse-time errors happen
  before `args.json` exists, so `main()` peeks at raw argv for `--json` and
  stashes it on the class-level `_json_hint`. Pass
  `parser_class=_CliArgumentParser` to every `add_subparsers()` call (see
  `_commands/cli.py`) or a nested noun drops out of the contract silently.
  `_dispatch()` wraps any non-`CliError` exception so no traceback reaches
  stderr.
- `substack_cli/cli/_errors.py` — `CliError(code, message, remediation)` plus
  the exit-code policy: `0` success, `1` user error, `2` environment error,
  `3+` reserved. Every *command handler* raises `CliError` on failure; two
  paths differ downstream by design — `_CliArgumentParser.error()` emits a
  `CliError` then raises `SystemExit`, and `doctor` *returns* `1` for an
  unhealthy report rather than raising.
- `substack_cli/cli/_output.py` — results to **stdout**, errors and diagnostics
  to **stderr**, never mixed, in both text and JSON mode.
- `substack_cli/cli/_commands/*.py` — one module per verb/noun, each exposing
  `register(sub)`; register new noun groups in `_build_parser()` at the marked
  comment.
- `substack_cli/explain/catalog.py` — markdown keyed by command-path tuple.
  `tests/test_cli.py` walks `known_paths()`, so an unregistered or
  uncatalogued path fails the suite.

Rubric rules CI enforces via `teken cli doctor . --strict`: every command takes
`--json`; any noun with action-verbs must also expose `overview`; descriptive
verbs never hard-fail on a bad target (`overview /no/such/path` exits `0`);
`learn` must keep covering purpose, command map, exit codes, `--json`, and
`explain`.

## Substack surface

The domain layer lives in `substack_cli/substack/`: `http.py` (stdlib HTTP for
the public read verbs — `post list`/`get`, `comment list`, `reaction list`, no
session needed), `webglass.py` (subprocess wrapper around the sibling
`webglass-cli` project's `webglass` binary for owner verbs — `post
publish`/`schedule`/`unpublish`/`delete`, `comment reply`/`delete`, `reaction
add`/`remove`, `feed read`, `account whoami`), and `render.py`/`body.py`
(ProseMirror body construction). Owner verbs need
`$SUBSTACK_WEBGLASS_SESSION` naming a session already logged in to Substack;
until `webglass-cli` can create such a session itself
(`agentculture/webglass-cli#17`), owner verbs exit `2` with a hint. `post
publish` is draft-first — without `--send` it only creates a draft; `--send`
alone emails every subscriber and cannot be recalled. Tests for this layer
use fakes under `tests/fakes/`.

A new noun is a module under `cli/_commands/` with `register(sub)`, a line in
`_build_parser()`, a catalog entry in `explain/catalog.py`, a row in `learn.py`'s
text **and** JSON payload, and tests. Every endpoint the CLI calls must appear
in [`docs/api/substack-endpoints.md`](docs/api/substack-endpoints.md) before
it ships — that file is the only record of what Substack's unpublished API
actually does. Credentials (Substack session cookies or API tokens) come from
the environment — `scripts/scan-secrets.py` runs in CI and fails on committed
credentials and non-localhost endpoints.

## Skills

`.claude/skills/` vendors 19 skills, cite-don't-import, reachable here through
the `.qwen/skills` symlink: 17 from guildmaster (eight of those devague-origin
re-broadcasts) and `ask-colleague` direct from `colleague`. Provenance and the
re-sync procedure live in `docs/skill-sources.md` — check a skill's row there
before assuming guildmaster is its upstream. Do not
reformat or edit vendored scripts — a fix belongs upstream, then re-sync. Every
vendored `SKILL.md` needs `type: command`; `core.skill_loader` silently skips
one without it.

## Conventions

- **Every PR bumps the version** — even docs/config/CI. Use the
  `version-bump` skill; the `version-check` CI job blocks merge otherwise.
- **Four harnesses, four files.** If you change a convention in this file,
  change it in `CLAUDE.md`, `AGENTS.override.md` and `AGENTS.colleague.md` too
  — CI's `harness-smoke` job fails when any one of the four configs breaks.
- `doctor`'s `_PROMPT_FILE` table and
  `.claude/skills/agent-config/data/backend-fingerprints.yaml` are two copies
  of one registry; `tests/test_harness_registries.py` fails if they drift.
  `_PROMPT_FILE` (recognition — does *some* harness on this backend read this
  file?) and `_RESIDENT_PROMPT` (health — does the *daemon's* file exist?) are
  deliberately different tables; don't collapse them.
- **Deploy**: pushing to `main` publishes to PyPI via Trusted Publishing
  (`.github/workflows/publish.yml`); PRs do a TestPyPI dry-run.

## Layout

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

This file describes the repository **as it exists on disk today**. When you
edit, keep claims grounded in checked-in reality; if a section drifts ahead of
reality, mark it `(planned)` or move it under a `## Roadmap` heading. For the
full set of workflow conventions (worktree layout, memory discipline,
`ask-colleague` usage), see [`CLAUDE.md`](CLAUDE.md) — those conventions apply
to work in this repo regardless of which harness is doing it.
