# substack domain surface

> substack-cli controls a Substack publication and account from an agent-first CLI: publish and schedule posts, read the feed, read comments and reactions, reply and react — account-agnostic, first proven on jetsonailab.substack.com
> instruction: public half runs in CI-free local check now; owner half runs after the webglass M6 brief lands

## Audience

- the primary consumer is an AI agent (Claude Code, the Culture mesh resident, or a scheduled routine) driving the publication for the human owner; the human uses the same CLI interactively for spot checks
  - instruction: check every verb is scriptable: run each with --json and no TTY

## Before → After

- Before: today the CLI is the culture-agent-template scaffold: whoami/learn/explain/overview/doctor/cli overview only; managing the publication means the browser, and an agent cannot post, read the feed, or reply at all
  - instruction: run it on main
- After: an agent (or the owner) runs 'substack post|feed|comment|reaction|account `<verb>` --json' with a webglass session named in the environment and a --publication host, and gets structured results on stdout and error:/hint: pairs on stderr, for any Substack account
  - instruction: manual run, recorded in the PR

## Why it matters

- jetson-ai-lab updates, replies and reactions can be driven by the mesh agent on a schedule instead of by hand, and the same CLI serves any other publication the owner controls
  - instruction: schedule one culture run that invokes the CLI and verify the post appears on jetsonailab.substack.com

## Requirements

- each Substack noun (post, feed, comment, reaction, account/whoami-style identity) is one module under `substack_cli`/cli/`_commands`/ exposing register(sub), registered in `_build_parser`() at the marked comment, with `parser_class`=`_CliArgumentParser` passed to every nested `add_subparsers`() so argparse errors keep the error:/hint: contract and exit 1
  - instruction: add a per-noun copy of tests/`test_cli_introspection.py`:57-65
  - honesty: substack post --bogus exits 1 with error:/hint: on stderr, in text and --json mode
- Substack API failures map onto the existing exit-code policy: bad user input (unknown post id, invalid slug) exits 1; missing/expired credentials or unreachable substack.com exits 2 via CliError(`EXIT_ENV_ERROR`); results go to stdout and errors to stderr in both text and --json mode
  - instruction: fake-webglass tests for both cases
  - honesty: a missing or unauthenticated webglass session exits 2 with a hint naming the session variable; a nonexistent post id exits 1
- learn.py's `_TEXT` and `_as_json_payload`() and explain/catalog.py gain one row/entry per new Substack command path; the root catalog entry and the parser prog/description stop describing the repo as 'a clonable template'
  - instruction: uv run pytest tests/`test_cli.py` -v
  - honesty: tests/`test_cli.py`'s `known_paths`() walk passes and learn --json lists every new path
- landing real Substack nouns is a coordinated edit across README.md (Status + CLI table) and all four harness prompt files (CLAUDE.md, AGENTS.override.md, AGENTS.colleague.md, QWEN.md): each drops the 'Status: scaffold' / '(planned)' framing and the 'Adding the Substack surface (planned)' section together; .pi/SYSTEM.md carries no domain text and stays untouched
  - instruction: grep -n 'scaffold\|(planned)' CLAUDE.md AGENTS.override.md AGENTS.colleague.md QWEN.md README.md
  - honesty: all four harness files and README no longer contain 'Status: scaffold' or '(planned)' for the Substack surface, and harness-smoke --stage config passes
- the feature PR bumps the version with a minor step (0.9.1 -> 0.10.0) and records the new nouns under '### Added' in CHANGELOG.md, per the every-PR-bumps rule enforced by the version-check job
  - instruction: version-check CI job
  - honesty: pyproject version is 0.10.0 and CHANGELOG has a matching ### Added entry
- every Substack noun with action verbs also exposes an 'overview' verb and every verb takes --json, propagating `parser_class`=type(p) at each nesting level exactly as cli.py does; this is the repo's own convention (cli.py docstring, overview.py conventions text) and is stricter than teken's rubric, which only probes 'cli overview'
  - instruction: parametrized test over the registered noun list
  - honesty: for each new noun, 'substack `<noun>` overview' exits 0 and every verb accepts --json
- the Substack API base URL lives as a Python constant (overridable by an env var for testing), never in a JSON config: scan-secrets' endpoint check only parses JSON files, so a JSON config carrying <https://substack.com> would fail CI while a .py constant passes
  - instruction: grep the constant; scan-secrets passes
  - honesty: the base URL is a Python constant overridable by `SUBSTACK_API_BASE`; no tracked JSON file contains it
- new noun modules ship with tests that keep aggregate coverage at or above the `fail_under`=60 floor; HTTP calls are exercised against a fake transport (stdlib urllib opener injection), never against live substack.com in the suite
  - instruction: run with a socket-blocking fixture
  - honesty: uv run pytest -n auto --cov=`substack_cli` reports >= 60% and no test opens a network socket
- descriptive Substack verbs (feed read, post list, comment list, reaction list) never hard-fail on an empty or missing target — they return 0 with an empty result; only malformed input (exit 1) or auth/network failure (exit 2) raise CliError, mirroring overview.py and doctor.py's return-1-don't-raise split
  - instruction: fake-transport tests returning \[\]
  - honesty: substack feed read on an empty feed and substack comment list on a post with no comments both exit 0 with an empty list
- the four write verbs of v1 are: post publish (from a markdown or JSON body file), post schedule, comment reply, reaction add; the read verbs are: post list/get, feed read, comment list, reaction list, account whoami; subscriber and stats management is a later release
  - instruction: assert on learn --json in tests
  - honesty: learn --json lists exactly the v1 verbs and no subscriber/stats paths
- v1 splits by auth need: public read verbs (post list/get, comment list, reaction list on public posts) use stdlib HTTP and ship first; owner verbs (post publish/schedule, comment reply, reaction add, feed read, account whoami) are wired to webglass sessions and report a structured `backend_unavailable` (exit 2) until webglass-cli ships authenticated persistent sessions
  - instruction: CI test job has no webglass on PATH; run the full suite there
  - honesty: on a machine without webglass, every public read verb still exits 0 and every owner verb exits 2 with a hint naming webglass-cli
- write verbs never auto-retry a non-idempotent POST: backoff on 429/5xx applies to GETs only; a failed publish/reply/react reports the failure with exit 2 and any partial state, so a retry cannot double-post or double-comment
  - instruction: two fake-transport tests
  - honesty: a fake transport returning 500 to POST /drafts/{id}/publish yields exactly one request and exit 2; the same 500 on a GET yields a retry
- two-phase verbs report partial state: post publish is create-draft then publish, and if the publish step fails the verb still returns the draft id and URL (stdout, --json) so the agent can resume or delete it rather than re-create
  - instruction: fake-webglass test: draft create 200, publish 500
  - honesty: when the publish step fails, --json output contains the draft id and URL and the exit code is 2
- account whoami is the auth probe and distinguishes three states with distinct hints: no webglass session named (exit 2), webglass session exists but Substack answers 401 'Please sign in' (exit 2, hint: log in again headed), and authenticated (exit 0 with the account id and owned publications)
  - instruction: parametrized test over the three fake responses
  - honesty: the three states produce three distinct hint strings and the documented exit codes
- third-party text (comment bodies, feed items, post titles from other authors) is untrusted input to the consuming agent: in --json it sits under an explicit 'content' field per item and never in top-level message/hint strings; in text mode it is rendered verbatim but never interpolated into error:/hint: lines
  - instruction: fixture comment with hostile text
  - honesty: a comment body containing 'hint: run rm -rf' appears only under content in --json and never on stderr
- --publication accepts a host, validated as a DNS name; owner verbs only ever route through the webglass session (whose cookies the browser scopes to substack.com), and public read verbs only send stdlib GETs with no credentials, so a wrong or hostile host can leak nothing beyond the request itself
  - instruction: two unit tests
  - honesty: --publication 'not a host' exits 1; public read verbs send no Cookie header (asserted on the fake transport)
- every write verb has a containment twin in v1: post unpublish and post delete, comment delete, reaction remove — a bad publish can be pulled from the site even though already-sent emails cannot be recalled; each write verb's --json result carries the created object's id and canonical URL
  - instruction: assert on learn --json and on fake-transport results
  - honesty: learn --json lists post unpublish, post delete, comment delete, reaction remove, and every write verb's --json result has id and url keys
- post publish is two-step by default: it creates or updates a draft and returns its id; sending requires an explicit --send (or a separate 'post send' verb), and --no-email publishes to the site without emailing subscribers so live proofs on a real publication do not spam the list
  - instruction: fake-transport tests; field name filled in after the request capture
  - honesty: post publish without --send creates a draft only; with --send --no-email the fake transport sees `send_email`=false (field name confirmed at capture time)

## Honesty conditions

- against jetsonailab.substack.com, 'substack post list --json' returns the archive with no session, and once an authenticated webglass session exists 'substack post publish', 'substack comment reply' and 'substack reaction add' each land a visible change on the site
- pyproject \[project\].dependencies stays \[\] and 'grep -rn playwright `substack_cli`' returns nothing
- python3 scripts/scan-secrets.py exits 0 on the feature branch and no JSON file carries substack.com
- the CLI is driven end-to-end by an agent with no human in the loop: every verb takes --json and no verb prompts interactively (the one-time headed login is the only human step)
- every authenticated verb's transport is a subprocess call to 'webglass ... --json' with a fake-webglass test double; no `substack_cli` module imports playwright or opens a browser
- git diff main -- `substack_cli`/cli/`_commands`/doctor.py .claude/skills scripts/harness-smoke.py .github/workflows/publish.yml sonar-project.properties is empty
- public read verbs (post list via /api/v1/archive) work with no session; owner verbs without a session exit 2 naming the missing webglass session
- 'uv run substack learn' on main lists only the six scaffold verbs
- the same verbs succeed against two different publication hosts with two cookie sets
- one scheduled mesh run publishes a jetson-ai-lab update and replies to a comment without a human touching the browser
- learn --json lists post, feed, comment, reaction, account with the verbs named in c27, and each exits 0 with --json

## Success signals

- at least 5 nouns ship (post, feed, comment, reaction, account), each verb supports --json, teken cli doctor . --strict passes, coverage stays >= 60%, and one real post plus one real reply and one real reaction land on jetsonailab.substack.com via the CLI
  - instruction: walk learn --json and invoke each path

## Scope / boundaries

- the runtime package keeps dependencies = \[\] (pyproject.toml): HTTP is stdlib urllib for public read endpoints, and every authenticated operation goes through the webglass binary as a subprocess; webglass-cli is an install prerequisite (like devex and agtag), never a Python dependency
  - instruction: run both on the feature branch
- substack-cli holds no Substack credential at all: the only auth input is a webglass session id; scripts/scan-secrets.py still fails CI on committed credential-shaped strings and on non-localhost URLs under url/endpoint/host/baseUrl keys in JSON files, so no checked-in JSON config may carry <https://substack.com>
  - instruction: run the script; grep -l substack.com -- '\*.json'
- browser control lives entirely in webglass-cli: substack-cli composes webglass session/page/action verbs and parses their WebOperationResult JSON; it adds no browser code, no form filling and no web UI of its own
  - instruction: tests inject a fake webglass executable on PATH
- the identity plumbing is not touched by domain verbs: doctor.py's `_PROMPT_FILE`/`_RESIDENT_PROMPT`, backend-fingerprints.yaml, tests/`test_harness_registries.py`, scripts/harness-smoke.py, the 19 vendored skills, publish.yml and sonar-project.properties all stay as they are
  - instruction: run that git diff on the feature branch

## Non-goals

- the binary-vs-prog-name mismatch (installed 'substack' vs argparse prog 'substack-cli', CLAUDE.md:52-58) is pre-existing debt to resolve before the first release; it is tracked separately and not part of the domain-surface work unless the plan explicitly folds it in
- no scraping of HTML pages and no bulk copying of content: the CLI only calls the JSON API the logged-in owner's own browser already uses, for the owner's own publication and feed; bulk export of other publications is out of scope

## Assumptions

- the first proving ground is the jetsonailab.substack.com publication, but the CLI stays account-agnostic: the publication host and credentials are runtime inputs (env / flag / config), never a default baked into code or docs
- no credential file or ignore pattern is needed: the CLI's inputs are a webglass session id, a publication host and post/comment ids; the browser profile lives under webglass's own state dir, outside this repo
- authentication is a webglass session whose persistent Chromium profile the owner logged into once; substack-cli names it by `SUBSTACK_WEBGLASS_SESSION` (or --session-id) and treats a missing/unauthenticated session as exit 2 with a hint; webglass-cli 0.8.3 cannot create such a session yet (M6 unbuilt), so owner-only verbs stay `backend_unavailable` until it does
  - instruction: curl-equivalent test for archive; fake-webglass test for the exit-2 path
- the endpoint map is taken as leads from python-substack (drafts create/publish/schedule, MIT, active) and AnthonyDavidAdams/substack-api-reference (129 endpoints incl. comments, reactions, notes, subscribers, stats), then confirmed by an observed request capture against jetsonailab.substack.com (mechanism per the open capture question) before any client code is written; unverified paths are never shipped
- cite-don't-import candidates: ma2za/python-substack (MIT, write side: drafts/publish/schedule/images) and NHagar/`substack_api` (MIT, read side) are the reference implementations to cite from; the TypeScript clients and MCP servers are consulted for endpoint shapes only
- webglass-cli 0.8.3 has no network lens (page inspect offers outline/controls/metadata/console/structure only), so endpoint discovery on the logged-in publication needs either a network lens added to webglass (extend webglass-cli#17) or a one-off DevTools/Chrome-MCP capture; webglass alone cannot observe the SPA's XHR calls today
- there are two API bases, not one: publication-scoped verbs (post, comment, reaction on posts) hit https://`<publication-host>\`/api/v1, while account-scoped verbs (feed read, notes, account whoami) hit <https://substack.com/api/v1>; --publication selects the former and the session implies the latter; publications on custom domains are addressed by their host, unverified
- post bodies are ProseMirror JSON; 'publish from markdown' means converting a restricted markdown subset (headings, paragraphs, bold/italic, links, lists, images by URL) through a builder cited from python-substack; unsupported markdown fails the verb with exit 1 rather than silently dropping formatting

## Scope exploration

- `s1` — `substack_cli/cli/__init__.py (_build_parser, _CliArgumentParser, _dispatch)`: new noun groups register at the '# Register your own noun groups here' comment; nested subparsers must pass `parser_class`=`_CliArgumentParser` or they drop out of the structured-error contract; `_dispatch` wraps non-CliError exceptions so HTTP failures must be raised as CliError to keep remediation hints
  - seeds: `c2`
- `s2` — `pyproject.toml [project] dependencies / dev group`: dependencies is an empty list and only dev deps (teken, pyyaml, pytest) exist; CLAUDE.md states a Substack HTTP client belongs behind an optional extra or the stdlib
  - seeds: `c3`
- `s3` — `substack_cli/cli/_errors.py + _output.py`: exit codes are 0/1/2 with 3+ reserved; every handler raises CliError(code, message, remediation); `emit_result`/`emit_error` enforce the stdout/stderr split — an auth failure fits `EXIT_ENV_ERROR` (2), a missing post fits `EXIT_USER_ERROR` (1)
  - seeds: `c4`
- `s4` — `substack_cli/cli/_commands/learn.py + substack_cli/explain/catalog.py`: both still describe 'a clonable template for AgentCulture mesh agents' with a six-command map; the text and the JSON payload are two hand-maintained copies and the catalog's `known_paths`() is walked by tests, so every new path needs entries in all three places
  - seeds: `c5`
- `s5` — `scripts/scan-secrets.py + .github/workflows/tests.yml lint job`: check 1 flags token-shaped strings and secret-ish key=value assignments >=20 chars in any tracked text file (placeholders like $VAR are exempt); check 2 inspects only JSON-parsable files for non-localhost URLs under baseUrl/endpoint/url/host keys — a base URL constant in a .py module is not caught by check 2, a JSON config would be
  - seeds: `c6`
- `s6` — `user request (jetson-ai-lab account, 'account agnostic')`: the user named jetsonailab.substack.com as the first target and required account-agnostic control; culture.yaml/whoami identity is the agent's own, unrelated to the Substack account identity
  - seeds: `c7`
- `s7` — `README.md + CLAUDE.md + AGENTS.override.md + AGENTS.colleague.md + QWEN.md + .pi/SYSTEM.md`: README.md:9-16 says 'Scaffold' and its CLI table (44-56) lists only scaffold verbs; CLAUDE.md:8-19/101-110, AGENTS.override.md:274-287, AGENTS.colleague.md:505-517 and QWEN.md:583-596/716-722 each restate '(planned)' + 'Status: scaffold' and tell the agent to answer that posts/comments are not implemented; CLAUDE.md:142-143 mandates editing all four together; .pi/SYSTEM.md has no domain content
  - seeds: `c10`
- `s8` — `doctor.py registries, harness-smoke.py, test_harness_registries.py, .claude/skills, publish.yml, sonar-project.properties`: doctor.py:44-70 maps backend->prompt filename only; harness-smoke `stage_config` checks the four files exist, are non-empty and are registered, never their content; sonar.sources=`substack_cli` and sonar.tests=tests are directory globs; publish.yml triggers on pyproject/`substack_cli`/\*\* paths; none of the 19 vendored skills mention Substack
  - seeds: `c11`
- `s9` — `CHANGELOG.md + pyproject.toml version + version-check CI job`: top entry is \[0.9.1\] - 2026-09-12 matching pyproject.toml:3; CLAUDE.md:177-178 states every PR bumps the version via the version-bump skill and CI blocks merge otherwise; new functionality is a minor bump under ### Added
  - seeds: `c12`
- `s10` — `.gitignore + CLAUDE.md:106-107 credential contract`: .gitignore already ignores .env/.envrc/.venv/.pypirc; CLAUDE.md:106-107 says credentials must come from the environment; no repo-local credential file exists today so no new pattern is needed yet
  - seeds: `c13`
- `s11` — `pyproject.toml [project.scripts] + CLAUDE.md:52-58 binary-vs-prog note`: scripts installs 'substack' while prog/docs say 'substack-cli'; no PyPI name-conflict evidence found anywhere in the repo; CLAUDE.md frames the mismatch as a defect to fix before first release, separate from adding nouns
  - seeds: `c14`
- `s12` — `tests/test_cli.py, tests/test_cli_introspection.py, substack_cli/cli/_commands/cli.py, teken rubric checks (.venv/.../teken/rubric/checks/overview_cmd.py)`: `test_cli.py`:112-116 walks catalog `known_paths`() and asserts explain resolves each; `test_cli_introspection.py`:57-65 asserts 'cli overview --bogus' exits 1 with error:/hint:; cli.py:33-34 propagates `parser_class`=type(p); teken `overview_cmd.py`:60-77 hard-codes \['cli','overview'\] and no rubric bundle walks other nouns — per-noun overview/--json is self-imposed, not rubric-enforced
  - seeds: `c15`
- `s13` — `scripts/scan-secrets.py:186-207 _scan_endpoints + tests/test_scan_secrets.py`: `_scan_endpoints` returns \[\] unless json.loads succeeds, then flags baseUrl/endpoint/url/host keys with non-localhost hosts; a `BASE_URL` constant in a .py module trips neither the endpoint nor the credential check (key name not secret-shaped)
  - seeds: `c16`
- `s14` — `pyproject.toml [tool.coverage.report] fail_under + tests.yml test job`: `fail_under` = 60 at pyproject.toml:53; CI runs pytest -n auto --cov=`substack_cli`; no test-count constraint exists; thin untested HTTP wiring would drag the average down
  - seeds: `c17`
- `s15` — `substack_cli/cli/_commands/overview.py:9-11,96-107 + doctor.py:174-186`: overview accepts and ignores a bogus target and exits 0 (tested at `test_cli_introspection.py`:29-32); doctor returns 0/1 from `cmd_doctor` without raising for an unhealthy report — CliError is reserved for malformed invocation or environment failure
  - seeds: `c18`
- `s16` — `Substack auth (ignorance.ai reverse-engineering post, ma2za/python-substack README, NHagar/substack_api docs, dknell/substack-sdk api-reference.md, faq.substack.com login + 2FA articles)`: every unofficial client authenticates with browser cookies (connect.sid and/or substack.sid); python-substack offers email+password but recommends cookies when captcha or magic-link is required; Substack natively supports TOTP 2FA; the /api/v1/login request body and cookie lifetime were not observed in any source
  - seeds: `c19`
- `s17` — `Substack endpoints (python-substack, substack-api-reference, mostlypython 'Automating Substack Notes', glama substack-mcp get_post_comments)`: well-corroborated: POST/PUT/DELETE /api/v1/drafts, POST /api/v1/drafts/{id}/publish, GET /api/v1/post/{id}/comments, POST /api/v1/comment/feed with bodyJson for Notes, /api/v1/notes?cursor= for the feed; single-source or unverified: schedule payload, comment reply path, reaction endpoints, subscriber and stats paths; post bodies are ProseMirror-style JSON
  - seeds: `c20`
- `s18` — `substack.com/tos Acceptable Use Policy`: the ToS prohibits crawling/scraping, storing significant content, reverse engineering, and processes that run while not logged in; every surveyed peer tool (python-substack, substack-mcp-plus, NHagar) operates in this tension and disclaims affiliation; no attributable suspension for API automation was found but rate limits and Cloudflare behaviour on /api/v1 are undocumented
  - seeds: `c21`
- `s19` — `OSS clients survey (NHagar/substack_api, ma2za/python-substack, ty13r/substack-mcp-plus, dknell/substack-sdk, jakub-k-slys/substack-api, AnthonyDavidAdams/substack-api-reference)`: python-substack (173 stars, MIT) covers drafts/publish/schedule but not comments, reactions, notes or subscribers; `substack_api` (223 stars, MIT) is read-only; substack-mcp-plus wraps python-substack; none covers the full reply/react surface, so comments and reactions need first-hand capture
  - seeds: `c22`
- `s20` — `webglass-cli 0.8.3 (webglass learn, explain session/page/action, pyproject.toml, CLAUDE.md M5/M6, adapters/playwright.py:261-487)`: sibling agent-first CLI with playwright as a core dependency and real headless Chromium; sessions persist on disk with a `user_data_dir`; page open/read/inspect/extract/links and action follow/press exist; fill/select and authenticated capability are M5/M6 and not built; raw cookies are never persisted by default
  - seeds: `c31`, `c32` (rejected)
- `s21` — `jetsonailab.substack.com/api/v1 public probe (curl, read-only GET)`: GET /api/v1/archive?sort=new answers 200 application/json without auth (0 posts returned today); GET /api/v1/publication answers 403 without a session — public read endpoints exist, owner endpoints need the browser session
  - seeds: `c20`
- `s22` — `webglass-cli CLAUDE.md M5/M6 + session create docs (re-read for the runtime-plane decision)`: M5 (fill/select, preview/apply) and M6 (authenticated capability, credential brokering) are explicitly 'not built' / 'only on demand'; sessions persist a `user_data_dir` but never raw cookies or full profiles by default — so an authenticated session is new webglass work, not a configuration
  - seeds: `c33`, `c34`
- `s23` — `challenge pass / adjacent-systems lens: webglass explain page inspect (lens list) + webglass-cli#17`: no network/request lens exists; the v1 resolution and decision c31 overstate what webglass can observe; seeded c35 and question below
  - seeds: `c35`
- `s24` — `challenge pass / unstated-assumptions lens: s17 endpoint list + s21 probe (publication subdomain vs substack.com)`: the spec's after-state names one --publication host, but the Notes feed and comment/feed endpoints live on substack.com while archive/comments live on the publication host; seeded c36
  - seeds: `c36`
- `s25` — `challenge pass / unstated-assumptions lens: c27 'from a markdown or JSON body file' + s17 ProseMirror bodies + s19 python-substack builder`: markdown-to-ProseMirror conversion is unstated work; seeded c37 with a fail-closed rule for unsupported syntax
  - seeds: `c37`
- `s26` — `challenge pass / cheap-probe lens: curl GET jetsonailab.substack.com/api/v1/{posts,archive} and substack.com/api/v1/{notes,feed/following}`: publication endpoints return 200 with an empty list (the publication has no posts yet, so live proofs will create its first content); substack.com/api/v1/feed/following returns 401 'Please sign in' and /api/v1/notes 404 — the feed is account-scoped on substack.com and needs the session; seeded c36
  - seeds: `c36`
- `s27` — `challenge pass / failure-mode lens: c30 backoff decision, s21 401 body shape, webglass session --ttl-seconds + lease semantics (webglass explain session create; webglass commits 04d2c23/9a290f6)`: retry-with-backoff on writes can duplicate posts; publish is two calls; Substack signals logout with a 401 JSON body; webglass sessions carry a TTL and lease so the session can vanish mid-run — seeded c38, c39, c40
  - seeds: `c38`, `c39`, `c40`
- `s28` — `challenge pass / security lens: c8 audience (agent-driven), webglass explain page inspect 'untrusted source material' rule, c7 --publication host input`: prompt-injection via comment/feed text and host handling were unstated; seeded c41 and c42; session ids are public identifiers in webglass (`endpoint_ref` is the secret and never rendered) so passing --session-id on argv is acceptable
  - seeds: `c41`, `c42`
- `s29` — `challenge pass / reversibility lens: c26 success signal ('one real post ... on jetsonailab.substack.com'), c27 verb list, s17 drafts endpoints`: a published post emails every subscriber and cannot be un-sent; v1 listed no delete/unpublish/remove verbs; seeded c43 and c44 plus the question below on where the live proof runs
  - seeds: `c43`, `c44`
- `s30` — `challenge pass / observability lens: c4 exit-code policy, _output.py stdout/stderr split, webglass WebOperationResult evidence`: success paths return ids and URLs (c43) and failure paths return partial state (c39); no separate log file is proposed — stdout --json is the audit record and the PR proof; residual: no persistent local history of what was posted, left to the calling agent

## Decisions

- the noun/verb map follows the repo's own convention: every noun exposes overview, every verb takes --json, descriptive verbs exit 0 on empty results
- authentication is delegated to a browser the owner logged into once (a persistent Chromium profile); the CLI trusts that browser's session for every API call and never handles email/password — realised through webglass-cli sessions per c33
  - instruction: substack account whoami exits 2 with a 'log in once in the profile' hint when the profile has no Substack session
- the README carries an explicit Substack ToS-risk notice and the client is serial with exponential backoff on 429 and 5xx
  - instruction: grep the README for the notice; unit test the backoff with a fake transport returning 429 then 200
- unverified endpoints (schedule, comment reply, reactions, subscribers, stats) are discovered with webglass-cli against the logged-in publication before implementation; nothing unobserved ships
  - instruction: each implemented endpoint cites the webglass evidence (page-ref or extract output) in the PR
- webglass-cli is the runtime browser plane: substack-cli drives it as a subprocess ('webglass session/page/action ... --json'), the way the cicd skill drives devex; substack-cli never imports Playwright and keeps dependencies = \[\]
  - instruction: substack doctor reports whether 'webglass' is on PATH and its version
- endpoint discovery: a one-off Chrome-MCP network capture on the owner's logged-in browser unblocks the plan now; a network lens is requested from webglass-cli (issue 17) for the durable path
  - instruction: the plan's first task is the capture; each shipped endpoint cites its captured request
- the live proof runs on jetsonailab.substack.com with --send --no-email and is cleaned up with post delete / comment delete / reaction remove
  - instruction: PR records the --json output of the proof and of the cleanup

## Hard questions

- cookie-only auth for v1, or also scripted email/password login? cookie lifetime is unknown, so how does the CLI report an expired session (exit 2 with a re-copy-cookie hint)? (resolved: control a Playwright browser and trust the authentication that already lives in it: the owner logs in once in a headed, persistent Chromium profile; the CLI reuses that profile's cookies and never handles email/password itself)
- the ToS bans automated processes and reverse engineering; the user accepts this risk for their own account — does the README carry an explicit ToS-risk notice, and does the CLI default to conservative pacing (serial requests, backoff on 429)? (resolved: README carries an explicit ToS-risk notice and the client paces conservatively: serial requests, backoff on 429/5xx, no parallelism)

## Open parks

- [unknown_nonblocking] rate limits, Cloudflare challenges on /api/v1 and session lifetime are undocumented anywhere; learn empirically and add backoff — not decidable before first live runs
- [unknown_nonblocking] whether Substack POST endpoints require a CSRF token or specific headers beyond the session cookie, and whether custom-domain publications differ from \*.substack.com — not observable until the first request capture
- [unknown_nonblocking] concurrency: two mesh runs sharing one webglass session could interleave draft edits; single-writer is assumed for v1 and not enforced
- [follow_up] webglass-cli needs an authenticated, persistent-profile session (its M6 'authenticated capability', unbuilt at 0.8.3) plus a request/fetch verb from that session; a brief goes to agentculture/webglass-cli and substack-cli's owner verbs stay `backend_unavailable` until it lands

## Resolved vagueness

- [unknown_blocking] exact paths and payloads for schedule, comment reply, post/comment/note reactions, subscriber list and stats — only a single unverified source (substack-api-reference) names them; resolve by network capture in the first implementation task — resolved: explore the unverified endpoints via webglass-cli (page open/inspect/extract on the logged-in publication pages) before coding them; only observed requests ship
