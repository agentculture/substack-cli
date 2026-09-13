# substack-cli

Agent-first CLI to manage a Substack publication and account: publish and
schedule posts, read posts and comments, react to posts/comments, and read the
account feed. Unofficial community tool, not affiliated with Substack.

## Status

**Five nouns wired: `account`, `post`, `comment`, `reaction`, `feed`.** Public
read verbs (`post list`/`get`, `comment list`, `reaction list`) are plain
stdlib HTTP against the observed Substack API, no session required. Owner
verbs (`post publish`/`schedule`/`unpublish`/`delete`, `comment reply`/`delete`,
`reaction add`/`remove`, `feed read`, `account whoami`) shell out to the
`webglass` binary (the sibling `webglass-cli` project) with a session named by
`$SUBSTACK_WEBGLASS_SESSION` — see [One-time login](#one-time-login) and
[Terms of Service risk](#terms-of-service-risk) below before pointing this at
a real account. The AgentCulture sibling baseline this repo was scaffolded
from ([`culture-agent-template`](https://github.com/agentculture/culture-agent-template))
is still underneath: the agent-first CLI skeleton, a mesh identity, the
vendored skill kit, and a buildable/deployable package baseline.

## What you get today

- **Five Substack nouns** — `account`, `post`, `comment`, `reaction`, `feed` —
  see [CLI](#cli) below for the full verb table.
- **An agent-first CLI** cited from [teken](https://github.com/agentculture/teken)
  (`afi-cli`) — the runtime package has no third-party dependencies; even the
  Substack domain layer (`substack_cli/substack/`: `http.py`, `webglass.py`,
  `render.py`, `body.py`) uses only the standard library and never imports
  Playwright.
- **A mesh identity** — `culture.yaml` (`suffix` + `backend`) and the matching
  resident prompt file (`CLAUDE.md`, since this repo runs `backend: claude`).
  The mesh resident is one of **two separate selections** over this clone —
  see [Two selections, not one](#two-selections-not-one) below.
- **Four harness prompt files**, one per agent harness, each read by exactly
  one of them (see [Prompt files by harness](#prompt-files-by-harness) below).
  All four harnesses are usable interactively regardless of which one
  `culture.yaml` names as the mesh resident.
- **19 vendored skills** under `.claude/skills/`, cite-don't-import — 17 from
  guildmaster (eight of those devague-origin re-broadcasts) and `ask-colleague`
  direct from `colleague`. See [`docs/skill-sources.md`](docs/skill-sources.md).
- **A build + deploy baseline** — pytest, lint, the agent-first rubric gate, a
  committed-secret scanner, a per-harness smoke check, and PyPI Trusted
  Publishing wired into GitHub Actions.

## Terms of Service risk

Read this before pointing `substack-cli` at a real account. Substack's Terms
of Service prohibit automated processes against the service and prohibit
reverse engineering it. This CLI's owner verbs do both: they drive the same
internal API (`/api/v1`, observed and documented in
[`docs/api/substack-endpoints.md`](docs/api/substack-endpoints.md), not a
published or supported API) that the account owner's own browser uses, via a
webglass browser session logged in as that owner. There is no Substack
partnership, review, or endorsement behind any of this.

Use it only against your own account, at your own risk — including the risk
of account action by Substack. To keep that risk bounded, the client is
deliberately conservative: requests are serial (no concurrency, no request
pooling), failures back off rather than hammer the endpoint, and a write call
that fails is never auto-retried — a failed `post publish` or `comment reply`
surfaces the error and stops rather than silently resending a state-changing
request. `post publish --send` (without `--no-email`) emails every subscriber
and cannot be recalled once Substack has sent it — see the flag description in
the CLI table below.

## One-time login

Owner verbs authenticate through a `webglass` session rather than a stored
password or API token. Substack has no user-facing API token, so the CLI
drives a real, session-cookied browser context via the sibling
[`webglass-cli`](https://github.com/agentculture/webglass-cli) project's
`webglass` binary (installed separately, on `PATH`) instead of embedding a
browser automation library itself.

The intended one-time setup is: open a **headed** (visible, not headless)
webglass browser session, log in to Substack manually in that window exactly
as a person would (including any 2FA challenge), and then name that session in
`$SUBSTACK_WEBGLASS_SESSION` so every owner verb reuses its cookies instead of
logging in again.

**That login step does not exist yet.** `webglass-cli` can drive an existing
session but cannot yet create a fresh, authenticated, headed session for you —
tracked upstream as
[`agentculture/webglass-cli#17`](https://github.com/agentculture/webglass-cli/issues/17).
Until that lands, every owner verb here detects the missing capability and
exits `2` with a hint rather than guessing at a workaround; public read verbs
(`post list`/`get`, `comment list`, `reaction list`) need no session and work
today.

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
| `account whoami` | Account identity via the webglass session (owner). |
| `account overview` | Describe the account noun's verbs. |
| `post list` | List a publication's archive (public, no session). |
| `post get` | Fetch one post by slug (public, no session). |
| `post publish` | Create a draft; with `--send` also publish it (owner). Draft-first: without `--send` only a draft is created. `--send --no-email` publishes without notifying subscribers; `--send` alone emails every subscriber and cannot be recalled. |
| `post schedule` | Schedule a draft for a future publish time (owner). |
| `post unpublish` | Return a published post to drafts (owner). |
| `post delete` | Delete a draft or unpublished post (owner). |
| `post overview` | Describe the post noun's verbs. |
| `comment list` | List a post's comments (public, no session). |
| `comment reply` | Reply to a post or comment (owner). |
| `comment delete` | Delete a comment (owner). |
| `comment overview` | Describe the comment noun's verbs. |
| `reaction list` | List a post's aggregate reaction counts (public, no session). |
| `reaction add` | React to a post or comment (owner). |
| `reaction remove` | Remove your reaction (owner). |
| `reaction overview` | Describe the reaction noun's verbs. |
| `feed read` | Read the account's Notes/reader feed (owner). |
| `feed overview` | Describe the feed noun's verbs. |

"Owner" verbs need `$SUBSTACK_WEBGLASS_SESSION` (see
[One-time login](#one-time-login)); until that session flow ships they exit
`2` with a hint rather than fail unexplained. Every command supports
`--json`. Results go to stdout, errors/diagnostics to stderr (never mixed).
Exit codes: `0` success, `1` user error, `2` environment error, `3+` reserved.

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
