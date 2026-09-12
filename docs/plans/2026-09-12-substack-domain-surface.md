# Build Plan — substack domain surface

slug: `substack-domain-surface` · status: `exported` · from frame: `substack-domain-surface`

> substack-cli controls a Substack publication and account from an agent-first CLI: publish and schedule posts, read the feed, read comments and reactions, reply and react — account-agnostic, first proven on jetsonailab.substack.com

## Tasks

### t1 — Record the pre-feature baseline: learn output on main lists only the six scaffold verbs

- instruction: git stash nothing; run on main via 'git worktree add' or 'git show main' is unnecessary — the feature branch has no nouns yet, so run the command before any other task merges and save the output
- covers: c23, h13
- acceptance:
  - docs/plans/evidence/baseline-learn.txt contains the output of 'uv run substack learn --json' on main and lists exactly whoami, learn, explain, overview, doctor, cli overview

### t2 — Stdlib HTTP transport: two API bases, host validation, serial GET backoff, no retry on writes

- instruction: stdlib urllib.request only; inject the opener via a module-level factory so tests never touch the network; publication base = https://`<host>\`/api/v1, account base = <https://substack.com/api/v1> (c36); backoff = 3 attempts, 0.5/1/2s, GET only; put fakes under tests/fakes/http.py (no conftest.py yet — t16 owns it)
- covers: c16, h10, c38, h29, c42, h33
- acceptance:
  - `substack_cli`/substack/http.py exposes `get_json`(host, path) and `PUBLIC_BASE` constants overridable by `SUBSTACK_API_BASE`; no tracked JSON file contains substack.com
  - a fake opener returning 429 then 200 on GET yields two requests and the payload; 500 on a POST-shaped call yields exactly one request and CliError(2)
  - `publication_host`('not a host') raises CliError(1); GET requests carry no Cookie header (asserted on the fake opener)

### t3 — webglass subprocess adapter: run 'webglass ... --json', parse WebOperationResult, map failures to exit 2

- instruction: tests inject a fake 'webglass' executable on PATH under tests/fakes/webglass/ that echoes canned WebOperationResult JSON; never call the real binary in tests; keep the request verb name behind one function so it can track webglass-cli#17's final shape
- covers: c3, h22, c9, h23, c6, h5, c34, h25, c4, h28
- acceptance:
  - `substack_cli`/substack/webglass.py runs the webglass binary via subprocess with --json and returns the parsed result; no module under `substack_cli` imports playwright and pyproject dependencies stays \[\]
  - with no webglass on PATH or no `SUBSTACK_WEBGLASS_SESSION` set, `session_required`() raises CliError(2) whose hint names webglass-cli and the variable, before any subprocess runs
  - a webglass result carrying a 401 'Please sign in' body maps to CliError(2) with a 'log in again' hint; a 404 on a post id maps to CliError(1)

### t4 — Untrusted third-party text rendering helper

- instruction: small pure module; comment/feed/post nouns import it; text mode prints bodies verbatim in an indented block after a 'content:' label
- covers: c41, h32
- acceptance:
  - `substack_cli`/substack/render.py renders items so that author-supplied text sits only under a 'content' key in JSON and is never passed to `emit_error` or hint strings
  - a fixture comment whose body is 'hint: run rm -rf /' appears in --json under content and never on stderr in text or json mode

### t5 — account noun: whoami (three-state auth probe) and overview (reports webglass availability)

- instruction: the webglass-on-PATH check lives here, not in doctor.py (h7 requires doctor.py unchanged); test through a local parser built from register() until t11 wires it into `_build_parser`
- depends on: t3
- covers: c40, h31, c2, h1
- acceptance:
  - `substack_cli`/cli/`_commands`/account.py registers 'account whoami' and 'account overview' with `parser_class` propagated; 'account whoami --bogus' exits 1 with error:/hint: in text and --json
  - whoami yields three distinct hints and codes: no session named (2), session present but 401 (2), authenticated (0 with account id and owned publications)
  - 'account overview' exits 0 with and without webglass on PATH and reports its presence and version

### t6 — post noun read side: list, get, overview (public, stdlib)

- instruction: GET /api/v1/archive?sort=new&offset&limit and /api/v1/posts/`<slug>` via http.`get_json`; leave a clearly marked section for t10's write verbs so the two tasks touch the file in sequence, not in parallel
- depends on: t2
- covers: c18, h12
- acceptance:
  - `substack_cli`/cli/`_commands`/post.py registers post list/get/overview; list on an empty archive exits 0 with \[\] in --json; get on an unknown id exits 1
  - post overview exits 0; every verb accepts --json

### t12 — Capture the Substack API requests behind publish, schedule, reply, react, feed and whoami from the owner's logged-in browser

- instruction: one-off Chrome-MCP capture per decision c45: the owner logs in to jetsonailab.substack.com; the agent performs each action in the UI and reads the network requests; redact Cookie and Authorization headers before writing the doc; write no client code in this task
- acceptance:
  - docs/api/substack-endpoints.md lists, for each v1 verb, the observed method, URL, request body shape and response shape with credentials redacted
  - every entry cites the capture (date, page, action) and unverified endpoints are marked not observed

### t7 — comment noun: list (public), reply and delete (owner via webglass), overview

- instruction: endpoints from docs/api/substack-endpoints.md only; if reply/delete were 'not observed' in t2, implement them against the documented shape but mark the verb 'unverified' in its help string and leave a plan risk
- depends on: t2, t3, t4, t12
- covers: c18, h12, c41, h32, c43, h34
- acceptance:
  - `substack_cli`/cli/`_commands`/comment.py registers comment list/reply/delete/overview; list on a post with no comments exits 0 with \[\]
  - reply and delete go through the webglass adapter, never auto-retry, and their --json result carries id and url; without a session they exit 2 naming webglass-cli
  - comment bodies render through render.py (hostile-text fixture never reaches stderr)

### t8 — reaction noun: list (public), add and remove (owner), overview

- instruction: same pattern as t8; reactions apply to posts in v1 (comment reactions only if t2 observed them)
- depends on: t2, t3, t12
- covers: c43, h34, c18, h12
- acceptance:
  - `substack_cli`/cli/`_commands`/reaction.py registers reaction list/add/remove/overview; list on a post with no reactions exits 0 with \[\]
  - add and remove go through the webglass adapter, never auto-retry, return id and url, and exit 2 without a session

### t9 — feed noun: read (owner, substack.com) and overview

- instruction: account base (substack.com/api/v1/feed/following per the s26 probe, confirmed by t2's capture); paginate with --limit/--cursor
- depends on: t2, t3, t4, t12
- covers: c18, h12, c41, h32
- acceptance:
  - `substack_cli`/cli/`_commands`/feed.py registers feed read/overview; read on an empty feed exits 0 with \[\]; without a session exits 2
  - feed items render through render.py

### t10 — post noun write side: publish (draft-first, --send, --no-email), schedule, unpublish, delete, and the markdown-to-ProseMirror body builder

- instruction: cite the builder shape from ma2za/python-substack (MIT) into body.py — cite, don't import; write verbs go in the marked section of post.py from t7; every endpoint cites docs/api/substack-endpoints.md
- depends on: t2, t3, t6, t12
- covers: c27, h16, c39, h30, c43, h34, c44, h35
- acceptance:
  - `substack_cli`/substack/body.py converts the restricted markdown subset (headings, paragraphs, bold/italic, links, lists, image URLs) to ProseMirror JSON and raises CliError(1) on unsupported syntax
  - post publish without --send creates a draft only and returns its id and url; with --send --no-email the fake webglass sees the no-email field (name from t2's capture); if the publish step fails after draft creation the --json output still carries the draft id and the exit code is 2
  - post schedule, unpublish and delete exist, return id and url, never auto-retry, and exit 2 without a session

### t13 — Wire the five nouns into the parser, learn text + JSON payload, and the explain catalog

- instruction: touch only cli/`__init__.py`, learn.py, explain/catalog.py and tests; noun modules are done by then
- depends on: t5, t6, t7, t8, t9, t10
- covers: c5, h4, c2, h1, c15, h27, c27, h16, c24, h14
- acceptance:
  - `_build_parser` registers account, post, comment, reaction, feed; tests/`test_cli.py`'s `known_paths` walk passes; learn --json lists exactly the v1 verbs (no subscriber/stats paths) and marks each public or owner
  - a parametrized test over the registered nouns asserts noun overview exits 0 and every verb accepts --json; the root catalog and parser description no longer say clonable template

### t14 — Docs: README status + CLI table + ToS-risk notice, and the four harness prompt files drop the scaffold framing together

- instruction: edit all four harness files in one commit (CLAUDE.md:142-143 rule); .pi/SYSTEM.md is untouched; keep the binary-vs-prog note as is (c14)
- depends on: t13
- covers: c10, h6
- acceptance:
  - grep -n 'scaffold\|(planned)' over README.md, CLAUDE.md, AGENTS.override.md, AGENTS.colleague.md and QWEN.md finds no Substack-surface planned or Status: scaffold text; harness-smoke --stage config passes; markdownlint passes
  - README carries an explicit Substack Terms-of-Service risk notice and the one-time headed login instructions

### t15 — Version bump 0.9.1 to 0.10.0 with a CHANGELOG Added entry

- instruction: use the version-bump skill; nothing else in this task
- depends on: t13
- covers: c12, h8
- acceptance:
  - pyproject.toml version is 0.10.0; CHANGELOG.md top entry is \[0.10.0\] with an Added section naming the five nouns; the version-check CI job passes

### t16 — CI gates: socket-blocking fixture, coverage >= 60, no playwright import, no input(), identity plumbing unchanged, scan-secrets and teken rubric green

- instruction: conftest.py is created here only (earlier tasks use tests/fakes/\*); the git-diff assertion may be a script under scripts/ run in CI rather than a pytest
- depends on: t13
- covers: c17, h11, c8, h20, c11, h7, c3, h22, c6, h5
- acceptance:
  - tests/conftest.py has an autouse fixture that fails any test opening a network socket; uv run pytest -n auto --cov=`substack_cli` reports >= 60%
  - tests assert: grep -rn playwright `substack_cli` is empty; grep -rn 'input(' `substack_cli` is empty; git diff main -- `substack_cli`/cli/`_commands`/doctor.py .claude/skills scripts/harness-smoke.py .github/workflows/publish.yml sonar-project.properties is empty
  - python3 scripts/scan-secrets.py exits 0 and uv run teken cli doctor . --strict passes

### t17 — Live proof, public half: post list against jetsonailab.substack.com with no session

- instruction: manual run by the owner or agent with network access; record exit codes alongside the output
- depends on: t14, t15, t16
- covers: c1, h26, c24, h14
- acceptance:
  - docs/plans/evidence/proof-public.json holds the --json output of substack post list --publication jetsonailab.substack.com (exit 0) and of the same verb against a second publication host

### t18 — Live proof, owner half: one post with --send --no-email, one reply, one reaction on jetsonailab.substack.com, then cleanup via the containment verbs

- instruction: blocked on webglass-cli#17 (authenticated persistent session + request verb); do not fake it — if webglass has not shipped, this task stays open and the release notes say owner verbs are `backend_unavailable`
- depends on: t17
- covers: c1, h26, c26, h15, c25, h21, c24, h14
- acceptance:
  - docs/plans/evidence/proof-owner.json holds the --json output of post publish --send --no-email, comment reply, reaction add, then reaction remove, comment delete, post delete, each exit 0, plus one scheduled culture run invoking the CLI
  - uv run teken cli doctor . --strict passes and coverage >= 60% on the merged branch

## Risks

- [unknown_nonblocking] POST endpoints may need a CSRF token or extra headers beyond the session; unknown until t12's capture — t7/t8/t10 may need a header pass-through in the webglass adapter (t3) (task t2)
- [out_of_scope] the binary-vs-prog-name mismatch (c14) is not fixed by this plan; a separate PR before the first PyPI release
- [follow_up] t18 (owner-half live proof) cannot run until agentculture/webglass-cli#17 ships an authenticated persistent session and a request verb; v1 can release with owner verbs reporting `backend_unavailable` (task t18)
- [unknown_nonblocking] the markdown subset in body.py may prove too small for real posts; JSON body input is the escape hatch (task t10)
