# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

`substack-cli` is an **agent-first CLI to manage a Substack publication and
account** — publish and schedule posts, read posts and comments, react to
posts/comments, and read the account feed. Unofficial community tool, not
affiliated with Substack.

Five nouns are wired: `account`, `post`, `comment`, `reaction`, `feed`. Public
read verbs (`post list`/`get`, `comment list`, `reaction list`) are stdlib
HTTP with no session. Owner verbs (`post publish`/`schedule`/`unpublish`/
`delete`, `comment reply`/`delete`, `reaction add`/`remove`, `feed read`,
`account whoami`) shell out to the `webglass` binary (sibling project
`webglass-cli`) and need `$SUBSTACK_WEBGLASS_SESSION` naming a session whose
browser is already logged in to Substack — see
[Substack surface](#substack-surface) below. The AgentCulture sibling baseline
this repo was scaffolded from (`culture-agent-template`) is still underneath:
the agent-first CLI skeleton (`whoami`, `learn`, `explain`, `overview`,
`doctor`, `cli overview`), a mesh identity, the vendored guildmaster skill kit,
and a buildable/deployable package baseline.

It is a sibling to [`guildmaster`](https://github.com/agentculture/guildmaster)
(the **skills supplier**), [`steward`](https://github.com/agentculture/steward)
(**alignment** — `steward doctor`, the sibling-pattern baseline), and
[`teken`](https://github.com/agentculture/teken) (the **afi-cli** "Agent First
Interface" scaffolder this CLI is cited from) within the Organic Development
framework.

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
help string) says `substack-cli`. Anything of the form `substack-cli whoami` in
this repo's prose is the *logical* command name; what you actually type is
`uv run substack whoami` (or `python -m substack_cli`). Fix the two names into
agreement before the first release rather than papering over it in docs.

## CLI architecture

Cited (cite-don't-import) from teken's `python-cli` reference, so the runtime
package has **no third-party dependencies** — `teken` is a dev dependency only,
and even `culture.yaml` is parsed by hand in `whoami.py` rather than pulling in
PyYAML. Keep it that way when you add domain verbs: a Substack HTTP client
belongs behind an optional extra or the stdlib, not in `dependencies`.

The wiring that spans files, and matters before you add a verb:

- `substack_cli/cli/__init__.py` — builds the parser, dispatches, and owns the
  error contract. `_CliArgumentParser` overrides `.error()` so even *argparse*
  failures (unknown verb, missing arg) render as the structured
  `error:` / `hint:` pair and exit `1`, never argparse's default exit `2`.
  Because parse-time errors happen before `args.json` exists, `main()` peeks at
  raw argv for `--json` and stashes it on the class-level `_json_hint`; keep
  passing `parser_class=_CliArgumentParser` to every `add_subparsers()` call
  (see `_commands/cli.py`) or a nested noun silently drops out of the contract.
  `_dispatch()` wraps any non-`CliError` exception so no traceback ever reaches
  stderr.
- `substack_cli/cli/_errors.py` — `CliError(code, message, remediation)` and the
  exit-code policy (`0` success, `1` user error, `2` environment error, `3+`
  reserved). Every *command handler* raises `CliError` on failure. Two paths
  deliberately differ downstream: `_CliArgumentParser.error()` emits a
  `CliError` and then raises `SystemExit`, and `doctor` *returns* `1` for an
  unhealthy report (an unhealthy agent is a result, not a CLI failure).
- `substack_cli/cli/_output.py` — the strict stream split: **results to stdout,
  errors and diagnostics to stderr, never mixed**, in both text and JSON mode.
- `substack_cli/cli/_commands/*.py` — one module per verb/noun, each exposing
  `register(sub)`. Register new noun groups in `_build_parser()` at the marked
  comment.
- `substack_cli/explain/catalog.py` — markdown keyed by command-path tuple.
  `tests/test_cli.py` walks `known_paths()`, so an unregistered or
  uncatalogued path fails the suite.

Three rubric-enforced rules constrain new commands (`teken cli doctor . --strict`):
every command takes `--json`; any noun with action-verbs must also expose
`overview`; descriptive verbs never hard-fail on a bad target (`overview
/no/such/path` exits `0` — see `_commands/overview.py`). `learn` must keep
covering purpose, command map, exit codes, `--json`, and `explain`.

## Substack surface

The domain layer lives in `substack_cli/substack/`: `http.py` (stdlib HTTP for
the public read verbs), `webglass.py` (subprocess wrapper around the
`webglass` binary for owner verbs), `render.py` and `body.py` (ProseMirror
body construction for post/comment writes). Tests for it live under
`tests/fakes/`. Owner verbs currently exit `2` with a hint: `webglass-cli`
cannot yet create an authenticated, headed-login session
(`agentculture/webglass-cli#17`), only drive an existing one. `post publish`
is draft-first — without `--send` it only creates a draft; `--send
--no-email` publishes without notifying subscribers; `--send` alone emails
every subscriber and cannot be recalled.

Work forwards from the existing shape, not around it: a new noun is a module
under `cli/_commands/` with `register(sub)`, a line in `_build_parser()`, a
catalog entry in `explain/catalog.py`, a row in `learn.py`'s text **and** JSON
payload, and tests. Every endpoint the CLI calls must appear in
[`docs/api/substack-endpoints.md`](docs/api/substack-endpoints.md) before it
ships — that file is the only record of what Substack's unpublished API
actually does, observed against a real logged-in session. Credentials
(Substack session cookies / API tokens) must come from the environment —
`scripts/scan-secrets.py` runs in CI and fails on committed credentials and
non-localhost endpoints. For anything non-trivial, use `/think` →
`/spec-to-plan` before writing code; that is what the vendored devague skills
are here for.

## Identity and the four harnesses

`culture.yaml` declares `suffix: substack-cli`, `backend: claude`. That single
`backend` key is the **mesh resident** selection: it fixes this file,
`CLAUDE.md`, as the prompt the Culture daemon reads, and it is what the two
invariants check — **prompt-file-present** and **backend-consistency**
(`claude` ↔ `CLAUDE.md`), verified by both `substack doctor` and
`steward doctor`.

That is *not* the same as which harness you can run. Four harnesses are live
simultaneously over one clone, each reading exactly one root file, with no
shared `AGENTS.md` base for them to cascade from:

| Harness | File(s) |
|---------|---------|
| Claude Code | `CLAUDE.md` (this file — the fullest write-up) |
| Pi / associate | `AGENTS.override.md` (context) + `.pi/SYSTEM.md` (system prompt) |
| colleague | `AGENTS.colleague.md` |
| Qwen Code | `QWEN.md` |

`AGENTS.override.md` exists specifically so Pi does **not** inherit this file.
`.qwen/skills`, `.colleague/skills` and `.pi/skills` are relative symlinks onto
`.claude/skills` — one skill tree, wired to all four harnesses. Three of them
load it; colleague 1.76.0 loads 0 of the 19 for upstream reasons
([colleague#494](https://github.com/agentculture/colleague/issues/494),
`docs/harness-verification.md`), so the wiring is shared but the loading is
not. Forcing a harness is invocation-level only (flags to one process); never
rewrite `culture.yaml` to do it — see `docs/harness-invocations.yaml` (source of truth),
`docs/automation-contract.md`, and `docs/harness-selection.md`.

**When you edit this file, update the other three too.** They restate the same
conventions and CI's `harness-smoke` job fails if any one of the four configs
breaks. `doctor`'s `_PROMPT_FILE` table and
`.claude/skills/agent-config/data/backend-fingerprints.yaml` are two copies of
the same registry; `tests/test_harness_registries.py` fails if they drift.
`_PROMPT_FILE` (recognition — does *some* harness on this backend read this
file?) and `_RESIDENT_PROMPT` (health — does the *daemon's* file exist?) are
deliberately different tables; don't collapse them.

## Skills

`.claude/skills/` vendors 19 skills, cite-don't-import: 17 from guildmaster
(eight of those devague-origin re-broadcasts) and `ask-colleague` direct from
`colleague` as a tracked divergence. Provenance and the re-sync procedure live
in `docs/skill-sources.md` — check a skill's row there before assuming
guildmaster is its upstream. Every vendored
`SKILL.md` needs `type: command` — `core.skill_loader` silently skips one
without it. Tooling prerequisites: **`devex`** on PATH (the `cicd` skill
delegates the PR lifecycle to `devex pr`), **`agtag`** on PATH (the
`communicate` skill), and optionally **`colleague`** (only when `ask-colleague`
is invoked).

The vendored skills are cited **verbatim** — do not reformat or edit their
scripts; a fix belongs upstream, then re-sync per `docs/skill-sources.md`.

## Conventions

- **Reach for `ask-colleague` reflexively.** Treat it as the teammate at the
  next desk, not a last resort — its value is a *second, independent mind* (a
  different backend/model), not a stronger one. Before presenting or opening a
  PR on a non-trivial committed diff, run `review`; for a fresh read of an
  unfamiliar area, run `explore`. Both are read-only (throwaway worktree, zero
  side effects), so the reflex is always safe. The side-effecting
  `write --apply` / `write --pr` still needs the user's go-ahead. Its output is
  a second opinion to verify and own, never authority.
- **Every PR bumps the version** — even docs/config/CI. Use the `version-bump`
  skill; the `version-check` CI job blocks merge otherwise.
- **PRs** go through the `cicd` skill (`devex pr` + SonarCloud gating against
  project key `agentculture_substack-cli`). Sign online posts as
  `- substack-cli (Claude)` — the `cicd` / `communicate` scripts resolve the
  nick from `culture.yaml` automatically, so don't sign the body by hand.
- **Deploy**: pushing to `main` publishes to PyPI via Trusted Publishing
  (`.github/workflows/publish.yml`); PRs do a TestPyPI dry-run. Configure the
  `pypi` / `testpypi` GitHub environments and a PyPI Trusted Publisher before
  the publish job can succeed.
- Keep this file grounded in **checked-in reality**. Anything that runs ahead
  of disk goes under a `(planned)` marker or a `## Roadmap` heading.

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

## Worktrees

**Git worktrees you create live in `../.worktrees.substack-cli/<name>/`** — one
repo-named directory beside the checkout, one subfolder per worktree:

```bash
git worktree add ../.worktrees.substack-cli/<name> -b <branch>
```

Never a shared `../worktrees/`. This workspace holds many sibling projects, and
a generic shared folder accumulates orphaned trees from several repos with
nothing indicating who owns which — someone clearing stale trees cannot tell
yours from junk. Use a branch prefix scoped to the work (`posts/t2`, not
`agent/t2`): plain `agent/*` names collide with leftovers from earlier fan-outs
and `git worktree add -b` fails on an existing branch.

The vendored `assign-to-workforce` skill already mandates the same repo-named
worktree root (`.worktrees.<repo-name>`, `SKILL.md` §Fan-out) — that half needs
no override. Its example *branch* names are `agent/<task-id>`, so scope those to
the work when you follow it; the skill is cited verbatim and must not be edited.

**Exception — tool-managed throwaways.** `ask-colleague`'s read-only verbs
create their own detached worktree under `${TMPDIR:-/tmp}` and delete it on an
EXIT trap; expect `git worktree list` to show one mid-command. Remove a
worktree you are done with via `git worktree remove <path>` — `git worktree
prune` only clears metadata for directories that are already gone. Never
`rm -rf` a worktree directory you did not create.

## Memory discipline — recall before, remember after

This repo keeps its eidetic memory **in-repo and public**: records resolve to
`<repo-root>/.eidetic/memory` — committed, and shared with mesh peers (the
`claude` and `colleague` backends both read the `substack-cli` scope), so
memory travels with the repo rather than a private home-dir store.

- **`/recall` before you start** a non-trivial task — prior decisions, gotchas,
  "have we done this before?" — so you build on what's known instead of
  re-deriving it.
- **`/remember` when something worth keeping surfaces** — a non-obvious
  decision and its rationale, a constraint, a fix and *why*. Capture it as it
  happens.

A plain `/remember` lands the note in `./.eidetic/memory` (the wrappers default
to `--visibility public`; in-repo routing needs `eidetic >= 0.10.0`). Keep
something out of the committed store with `--visibility private` (routes to
`$HOME`); `/recall` reads and merges both. Don't store what the repo already
records — store what you'd otherwise re-derive.
