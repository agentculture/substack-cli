# Delivery Summary — substack domain surface

plan: `substack-domain-surface` · run: `partial` · date: `2026-09-12`
baseline: `devague summary skeleton`

## Intent

Ship the v1 Substack control surface for `substack-cli` — five nouns
(`account`, `post`, `comment`, `reaction`, `feed`) over stdlib HTTP for public
reads and the `webglass` binary for owner verbs — as the 17-task,
7-wave plan `substack-domain-surface` fanned out by `/assign-to-workforce`
on 2026-09-13, on branch `docs/init-harness-prompts`. The plan's announcement
and after-state, quoted from the frame:

> substack-cli controls a Substack publication and account from an
> agent-first CLI: publish and schedule posts, read the feed, read comments
> and reactions, reply and react — account-agnostic, first proven on
> jetsonailab.substack.com

After: an agent (or the owner) runs 'substack post|feed|comment|reaction|account
`<verb>` --json' with a webglass session named in the environment and a
--publication host, and gets structured results on stdout and error:/hint:
pairs on stderr, for any Substack account.

## Planned Work

Quoted verbatim from the `devague summary` skeleton:

- `t1` — Record the pre-feature baseline: learn output on main lists only the six scaffold verbs
- `t2` — Stdlib HTTP transport: two API bases, host validation, serial GET backoff, no retry on writes
- `t3` — webglass subprocess adapter: run 'webglass ... --json', parse WebOperationResult, map failures to exit 2
- `t4` — Untrusted third-party text rendering helper
- `t5` — account noun: whoami (three-state auth probe) and overview (reports webglass availability)
- `t6` — post noun read side: list, get, overview (public, stdlib)
- `t7` — comment noun: list (public), reply and delete (owner via webglass), overview
- `t8` — reaction noun: list (public), add and remove (owner), overview
- `t9` — feed noun: read (owner, substack.com) and overview
- `t10` — post noun write side: publish (draft-first, --send, --no-email), schedule, unpublish, delete, and the markdown-to-ProseMirror body builder
- `t12` — Capture the Substack API requests behind publish, schedule, reply, react, feed and whoami from the owner's logged-in browser
- `t13` — Wire the five nouns into the parser, learn text + JSON payload, and the explain catalog
- `t14` — Docs: README status + CLI table + ToS-risk notice, and the four harness prompt files drop the scaffold framing together
- `t15` — Version bump 0.9.1 to 0.10.0 with a CHANGELOG Added entry
- `t16` — CI gates: socket-blocking fixture, coverage >= 60, no playwright import, no input(), identity plumbing unchanged, scan-secrets and teken rubric green
- `t17` — Live proof, public half: post list against jetsonailab.substack.com with no session
- `t18` — Live proof, owner half: one post with --send --no-email, one reply, one reaction on jetsonailab.substack.com, then cleanup via the containment verbs

1 task was rejected during planning — see `devague plan show`.

## Actual Delivery

| Plan task | Status | What actually landed |
|-----------|--------|----------------------|
| `t1` | delivered | `docs/plans/evidence/baseline-learn.txt`; merge `9e41d55` |
| `t2` | delivered | `substack_cli/substack/http.py`, `tests/fakes/http.py`, `tests/test_substack_http.py`; merge `923fe7f`; amended by `74fc94e` (`d1`) |
| `t3` | delivered | `substack_cli/substack/webglass.py`, `tests/fakes/webglass/webglass`, `tests/test_webglass_adapter.py`; merge `395562a` |
| `t4` | delivered | `substack_cli/substack/render.py`, `tests/test_render.py`; merge `e292a95` |
| `t5` | delivered | `substack_cli/cli/_commands/account.py`, `tests/test_account.py`; merge `71b0352` (`d2`) |
| `t6` | delivered | `substack_cli/cli/_commands/post.py` read side, `tests/test_post.py`; merge `7aa21d3` |
| `t7` | delivered | `substack_cli/cli/_commands/comment.py`, `tests/test_comment.py`; merge `43c0bfb` |
| `t8` | delivered | `substack_cli/cli/_commands/reaction.py`, `tests/test_reaction.py`; merge `06487de` |
| `t9` | delivered | `substack_cli/cli/_commands/feed.py`, `tests/test_feed.py`; merge `fee61b3` |
| `t10` | delivered | write verbs in `post.py`, `substack_cli/substack/body.py`, `tests/test_post_write.py`, `tests/test_body.py`; merge `3c85083` |
| `t12` | delivered | `docs/api/substack-endpoints.md` from a live Chrome capture on the owner's session; merge `0f7df88`, fix `d3cc282` |
| `t13` | delivered | five nouns registered in `cli/__init__.py`; `learn.py` and `explain/catalog.py` cover all 24 paths; `tests/test_nouns_wired.py`; merge `531b712` |
| `t14` | delivered | README (status, CLI table, ToS-risk notice, one-time login) and the four harness prompts; merge `3d13f7b` |
| `t15` | delivered | `pyproject.toml` 0.10.0, `CHANGELOG.md` `[0.10.0]`; merge `c5fa2c4` |
| `t16` | delivered | `tests/conftest.py` socket block, `tests/test_repo_invariants.py`, `--cov-fail-under=60` in CI; merge `7747dbf` (`d3`) |
| `t17` | delivered | `docs/plans/evidence/proof-public.txt`: post list exit 0 on jetsonailab.substack.com and on.substack.com; commit `a54b9b3` (`d4`) |
| `t18` | blocked | owner verbs need an authenticated, persistent webglass session and a request verb that webglass-cli 0.8.3 does not have (agentculture/webglass-cli#17); no proof-owner evidence exists |

`t11` was a duplicate task rejected during planning and is not part of the contract.

## Mid-work Decisions

Approved deviation records, quoted from `devague deviate --list`:

- `d1` — t2's transport gained a descriptive User-Agent header and its GET retry loop now retries only 429, 5xx and transport errors (it retried every HTTPError); two tests in t6 and t8 that asserted four attempts on a 404 were changed to one — the wave-5 dry run of 'post list' returned 403: Substack rejects urllib's default Python-urllib agent (curl with a substack-cli/`<version>` agent gets 200); the plan text never mentioned a User-Agent, and the retry-every-error behaviour contradicted spec claim c38
- `d2` — t5's account whoami reads `user_id` from GET /api/v1/subscription (then /publication for the publication block) instead of /publication alone as its brief said — the t12 capture found /api/v1/subscription is the only endpoint carrying the signed-in `user_id`; /publication has none and /user/self answers 403
- `d3` — t16 edited `substack_cli`/substack/webglass.py's module docstring (a file outside its brief) to remove the literal word 'playwright' so the repo-invariant grep passes — the acceptance criterion is a literal substring grep over `substack_cli`; the docstring's 'no playwright import' disclaimer tripped it; wording changed, meaning kept
- `d4` — t17's evidence file is docs/plans/evidence/proof-public.txt (a header line plus the JSON record) instead of proof-public.json — scan-secrets' endpoint check rejects any JSON-parsable tracked file carrying https://`<host>`/p/... URLs and the t2 invariant forbids \*.json naming substack.com; the CI gates win over the file name in the acceptance criterion
- `d4` — t17's evidence file is docs/plans/evidence/proof-public.txt (a header line plus the JSON record) instead of proof-public.json — scan-secrets' endpoint check rejects any JSON-parsable tracked file carrying https://`<host>`/p/... URLs and the t2 invariant forbids *.json naming substack.com; the CI gates win over the file name in the acceptance criterion

Decisions no record covers, captured here directly:

- The capture task's endpoint discovery ran as a one-off Chrome capture of the owner's logged-in browser (decision c45), including one no-email publish, one comment, one reply, two reactions, and their deletion on jetsonailab.substack.com, each with the owner's explicit per-action permission; the site was left with zero posts and zero drafts.
- The fake `webglass` executable gained two backward-compatible mechanisms (`WEBGLASS_FAKE_RESPONSE_BY_URL` from t5, `WEBGLASS_FAKE_SEQUENCE_DIR` from t10) because multi-call flows need per-URL or sequenced canned responses; both merged.
- t5, t7 and t10 each added a public `publication_base()` helper to `http.py`; the merges kept one definition (t10's, which keeps the private name as an alias).
- t13 classified every noun's `overview` verb as `"access": "local"` rather than inheriting its noun's tier, since those verbs make no network call.
- The webglass-on-PATH check lives in `account overview`, not `doctor.py`, because honesty condition h7 requires `doctor.py` unchanged.

## Drift From Plan

| Plan item | Reason for divergence | Classification |
|-----------|-----------------------|----------------|
| `t2` (`d1`) | the wave-5 dry run of 'post list' returned 403: Substack rejects urllib's default Python-urllib agent (curl with a substack-cli/`<version>` agent gets 200); the plan text never mentioned a User-Agent, and the retry-every-error behaviour contradicted spec claim c38 | acceptable |
| `t5` (`d2`) | the t12 capture found /api/v1/subscription is the only endpoint carrying the signed-in user_id; /publication has none and /user/self answers 403 | acceptable |
| `t16` (`d3`) | the acceptance criterion is a literal substring grep over substack_cli; the docstring's 'no playwright import' disclaimer tripped it; wording changed, meaning kept | acceptable |
| `t17` (`d4`) | scan-secrets' endpoint check rejects any JSON-parsable tracked file carrying https://`<host>`/p/... URLs and the t2 invariant forbids *.json naming substack.com; the CI gates win over the file name in the acceptance criterion | acceptable |
| `t7` | `comment list` on an unknown post surfaces the 404 as exit 2, while `post get` and `reaction list` map 404 to exit 1 — the task's acceptance criteria never named the 404 case, but spec claim c4 does; no deviation record covers this (filed as evidence `e4` fail and delta `b3`) | needs-follow-up |
| `t18` | blocked on agentculture/webglass-cli#17 (authenticated persistent session plus a request verb); the owner half of the success signal is not delivered | needs-follow-up |

## Evidence

- tests: `uv run pytest -n auto` at `a54b9b3` — 329 passed, 1 skipped (pre-existing cross-repo report-only skip in `tests/test_harness_registries.py`)
- coverage: `uv run pytest -n auto --cov=substack_cli --cov-fail-under=60` at the t16 merge — 96.38 %
- lint: `black --check`, `isort --check-only`, `flake8`, `bandit -c pyproject.toml -r substack_cli` — clean at each task merge
- gates: `python3 scripts/scan-secrets.py` — clean (141 files); `uv run teken cli doctor . --strict` — pass; `scripts/harness-smoke.py --stage config --require config` — 6 passed; `markdownlint-cli2` over tracked markdown — clean
- validation ledger: obligations `o1`–`o23`, evidence `e1`–`e22` (`e4` fail; `o22`, `o23` have no evidence), deltas `b1`–`b4`, all confirmed by the owner on 2026-09-13 (`devague evidence --list`)
- live proof: `docs/plans/evidence/proof-public.txt` (four recorded runs)
- endpoint capture: `docs/api/substack-endpoints.md`
- commits: `a88345a..a54b9b3` on `docs/init-harness-prompts` (34 commits, 16 task merges)
- issues: agentculture/substack-cli#4 (deviation ledger), agentculture/webglass-cli#17 (authenticated session + request verb + network lens)

## Delivery Claims

| Claim | Confidence | Evidence |
|-------|------------|----------|
| five nouns with 24 command paths are registered, every verb takes `--json`, every noun exposes `overview` | high | `tests/test_nouns_wired.py` · evidence `e5`, `e7` · commit `531b712` |
| public read verbs (`post list`/`get`, `comment list`, `reaction list`) work against the live site with no session | high | `docs/plans/evidence/proof-public.txt` · evidence `e21`, `e22` · commit `74fc94e` |
| the runtime has no dependencies and never imports a browser-automation library | high | `tests/test_repo_invariants.py` · evidence `e2` |
| write verbs never auto-retry; GETs back off only on 429/5xx/transport errors | high | evidence `e11` · `tests/test_substack_http.py::test_get_does_not_retry_a_403` · `tests/test_post_write.py::test_write_verbs_never_retry_a_failed_call` |
| publish is draft-first; `--send --no-email` sends `send:false`; a failed publish still reports the draft id and exits 2 | medium | evidence `e12`, `e17` · capped by approved lapse `l14` (tests never observed red) and `l15` (`--no-email` without `--send` is silent) |
| owner verbs map a missing or logged-out webglass session to exit 2 with a hint | medium | evidence `e3`, `e13` · capped by approved lapse `l6` (adapter's HTTP response shape is invented pending webglass-cli#17) |
| third-party text never reaches stderr or hint lines | medium | evidence `e14` · capped by approved lapse `l3` (no multi-line hostile-body test) |
| a nonexistent id exits 1 on every read verb | low | evidence `e3` pass for reply, `e4` FAIL for `comment list` (exits 2) |
| the observed endpoint map is complete for the v1 verbs | medium | `docs/api/substack-endpoints.md`; reaction emoji values other than ❤, custom domains and `send:true` are marked not observed |
| one real post, reply and reaction land on jetsonailab.substack.com via the CLI | unverified | `t18` blocked — not claimed done (obligation `o22`, no evidence) |
| a scheduled mesh run drives the publication without a human | unverified | obligation `o23`, no evidence — not claimed done |

Lapse ledger evidence:

| Lapse | Code | What |
|-------|------|------|
| `l1` | `assumption-for-measurement` | the v1 park resolution assumed 'webglass page open/inspect/extract' can discover API endpoints; webglass explain page inspect lists only outline/controls/metadata/console/structure lenses — no network lens — so that was an assumption standing in for a check |
| `l2` | `assumption-for-measurement` | t1 agent redirected stderr into the evidence file (2>&1) and inferred stderr was empty from the file parsing as clean JSON rather than checking the stream separately |
| `l3` | `control-absent` | t4 agent implemented multi-line body handling in render.py but added no test for a multi-line hostile body, so that path is unverified |
| `l4` | `assumption-for-measurement` | t2 agent read 'backoff = 3 attempts, 0.5/1/2s' as 3 retries after the first try (4 GET attempts) because that reading uses all three delays; the plan text is ambiguous and the agent chose an interpretation rather than asking |
| `l5` | `provenance-missing` | t2 agent added `get_account_json`/`request_json`/`account_request_json` beyond the literally named `get_json` to cover the write path; scope inferred from the acceptance criteria rather than stated |
| `l6` | `assumption-for-measurement` | t3 agent invented the HTTP response shape (content.trusted.response = {status, body, headers}) that `map_failure` keys off, since webglass-cli#17's request verb does not exist yet; unverified against any real webglass output |
| `l7` | `control-absent` | t6 remaps 404->exit 1 by regex-parsing the 'HTTP Error `<code>`' text inside http.`get_json`'s CliError message because the error carries no structured status; a message-format change in http.py silently breaks the remap |
| `l8` | `grader-unverified` | t5's webglass version probe shells out to 'webglass --version' but the fake executable ignores argv, so the probe is only tested for presence/absence, never against the real binary's output |
| `l9` | `assumption-for-measurement` | t5 originally asserted `user_id` was 'not derivable' from any endpoint and hard-coded null, an unverified negative; the live capture showed /api/v1/subscription carries it |
| `l10` | `grader-unverified` | t9's first 401 test used `lifecycle_state` 'succeeded', which `map_failure` short-circuits, so the test would have passed for the wrong reason; caught by running the suite and fixed to 'failed' |
| `l11` | `grader-unverified` | t7's test helper defaulted `lifecycle_state` to 'succeeded' after a copy-paste, so failure-path tests initially passed without reaching `map_failure`; caught when tests failed, default restored to 'failed' |
| `l12` | `provenance-missing` | t8 built reaction URLs by hand instead of the `publication_base`() helper that landed via t5/t7, leaving two URL-building conventions to reconcile in t13 |
| `l13` | `assumption-for-measurement` | t8's remove result reports the heart emoji as the removed reaction although the DELETE response carries none; the value is fabricated best-effort |
| `l14` | `grader-unverified` | t10 wrote tests first but never observed a red run: every write-side test passed on the first implementation run, so the tests were never shown to fail for the right reason |
| `l15` | `control-absent` | t10 makes --no-email without --send a silent no-op; an agent passing it gets no signal that nothing was sent |

## Remaining Work / Follow-up

- `t18` — owner-half live proof: blocked until agentculture/webglass-cli#17 ships an authenticated persistent session and a request verb; then run publish `--send --no-email`, reply, react, and the containment verbs on jetsonailab.substack.com and record `docs/plans/evidence/proof-owner`.
- `t7` follow-up — make `comment list` map a 404 to exit 1 like `post get` and `reaction list` (delta `b3`); consider a structured status on the `CliError` raised by `http.py` so the remap stops parsing message text (lapse `l7`).
- webglass adapter — once webglass-cli#17 lands, replace the invented response shape in `map_failure` (lapse `l6`) and the speculative `request` verb name.
- `--no-email` without `--send` — emit a diagnostic or a usage error (lapse `l15`).
- render.py — add a multi-line hostile-body test (lapse `l3`).
- reaction `remove` — stop reporting a fabricated emoji in the result (lapse `l13`).
- spec follow-ups from the deviations — a requirement claim naming the User-Agent contract and an amendment to c40 naming `/api/v1/subscription`.
- `.devague/reviews/` markdown trips the local markdownlint glob (`MD034`); the folder is gitignored so CI is unaffected — add it to the lint ignore list or stop rendering bare URLs there.
- pre-existing, unchanged — the binary-vs-prog-name mismatch (`substack` vs `substack-cli`) is out of scope per c14 and still due before the first PyPI release.
