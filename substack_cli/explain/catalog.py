"""Markdown catalog for ``substack-cli explain <path>``.

Each entry is verbatim markdown. Keys are command-path tuples. The empty tuple
and ``("substack-cli",)`` both resolve to the root entry.

Keep bodies self-contained: an agent reading one entry should get enough
context without chaining reads.
"""

from __future__ import annotations

_ROOT = """\
# substack-cli

An agent-first CLI to manage a Substack publication and account: publish and
schedule posts, read posts and comments, react to posts/comments, and read the
account feed. Unofficial community tool, not affiliated with Substack. Cited
from the teken `python-cli` reference; carries a mesh identity (`culture.yaml`
+ `CLAUDE.md`), the canonical guildmaster skill kit under `.claude/skills/`,
and a buildable/deployable package baseline.

## Verbs

- `substack-cli whoami` — identity probe from `culture.yaml`.
- `substack-cli learn` — structured self-teaching prompt.
- `substack-cli explain <path>` — markdown docs for any noun/verb.
- `substack-cli overview` — descriptive snapshot of the agent.
- `substack-cli doctor` — check the agent-identity invariants.
- `substack-cli cli overview` — describe the CLI surface.
- `substack-cli account whoami|overview` — account identity via webglass.
- `substack-cli post list|get|publish|schedule|unpublish|delete|overview` —
  read and manage a publication's posts.
- `substack-cli comment list|reply|delete|overview` — read and manage a
  post's comments.
- `substack-cli reaction list|add|remove|overview` — read and manage
  reactions on posts/comments.
- `substack-cli feed read|overview` — read the account's Notes/reader feed.

## Authentication

`list`/`get` verbs are public (stdlib GET, no session). Every other noun verb
acts as the signed-in account owner and needs a webglass session named by
`$SUBSTACK_WEBGLASS_SESSION`.

## Exit-code policy

- `0` success
- `1` user-input error
- `2` environment / setup error
- `3+` reserved

## See also

- `substack-cli explain whoami`
- `substack-cli explain doctor`
- `substack-cli explain post`
"""

_WHOAMI = """\
# substack-cli whoami

Reports the agent's identity from `culture.yaml`: nick (`suffix`), backend,
served model, and the package version. Read-only.

## Usage

    substack-cli whoami
    substack-cli whoami --json
"""

_LEARN = """\
# substack-cli learn

Prints a structured self-teaching prompt covering purpose, command map,
exit-code policy, `--json` support, and the `explain` pointer.

## Usage

    substack-cli learn
    substack-cli learn --json
"""

_EXPLAIN = """\
# substack-cli explain <path>

Prints markdown documentation for any noun/verb path. Unlike `--help` (terse,
positional), `explain` is global and addressable by path.

## Usage

    substack-cli explain substack-cli
    substack-cli explain whoami
    substack-cli explain --json <path>
"""

_OVERVIEW = """\
# substack-cli overview

Read-only descriptive snapshot of the agent: identity (from `culture.yaml`), the
verb surface, and the sibling-pattern artifacts the template carries. Accepts an
ignored `target` so a stray path never hard-fails.

## Usage

    substack-cli overview
    substack-cli overview --json
"""

_DOCTOR = """\
# substack-cli doctor

Checks the agent-identity invariants `steward doctor` verifies:
prompt-file-present and backend-consistency (`claude` → `CLAUDE.md`), plus a
skills-present check. Exits 1 when unhealthy.

prompt-file-present requires the *resident* prompt the declared backend
actually reads. Other harness prompt files recognized under the same backend
name (`AGENTS.override.md`, `.pi/SYSTEM.md`, `QWEN.md`) belong to
interactively available harnesses the mesh daemon never loads; they are
reported by the informational harness-prompts check and never substituted.

## Usage

    substack-cli doctor
    substack-cli doctor --json
"""

_CLI = """\
# substack-cli cli

Noun group for CLI-surface introspection. `cli overview` describes the CLI
itself (distinct from the global `overview`, which describes the agent).

## Usage

    substack-cli cli overview
    substack-cli cli overview --json
"""

_ACCOUNT = """\
# substack-cli account

Account-identity probe over the webglass session. `account whoami` reports
the signed-in account against a publication's API; `account overview`
describes the noun's verb surface without making a network call.

## Usage

    substack-cli account whoami --publication example.substack.com
    substack-cli account overview
    substack-cli account overview --json
"""

_ACCOUNT_WHOAMI = """\
# substack-cli account whoami

Probes the webglass session against a publication's API and reports the
signed-in account (user id, publication block). Owner verb — needs
`$SUBSTACK_WEBGLASS_SESSION` naming a session whose browser is logged in.

## Usage

    substack-cli account whoami --publication example.substack.com
    substack-cli account whoami --publication example.substack.com --json
"""

_ACCOUNT_OVERVIEW = """\
# substack-cli account overview

Describes the `account` noun's verb surface. Read-only, no session required.

## Usage

    substack-cli account overview
    substack-cli account overview --json
"""

_POST = """\
# substack-cli post

Read (public `list`/`get`) and manage (owner `publish`/`schedule`/
`unpublish`/`delete`) a publication's posts. `post overview` describes the
verb surface.

## Usage

    substack-cli post list --publication example.substack.com
    substack-cli post get my-first-post --publication example.substack.com
    substack-cli post overview
"""

_POST_LIST = """\
# substack-cli post list

Lists a publication's archive, newest first. Public — no session required.

## Usage

    substack-cli post list --publication example.substack.com
    substack-cli post list --publication example.substack.com --limit 10 --offset 0
"""

_POST_GET = """\
# substack-cli post get

Fetches one post by slug. Public — no session required.

## Usage

    substack-cli post get my-first-post --publication example.substack.com
    substack-cli post get my-first-post --publication example.substack.com --json
"""

_POST_PUBLISH = """\
# substack-cli post publish

Creates a draft (from `--markdown` or `--body-json`) and optionally publishes
it. Owner verb — needs `$SUBSTACK_WEBGLASS_SESSION`.

## Usage

    substack-cli post publish --publication example.substack.com \\
        --title "Hello" --markdown ./post.md
"""

_POST_SCHEDULE = """\
# substack-cli post schedule

Schedules an existing draft for publication. Owner verb — needs
`$SUBSTACK_WEBGLASS_SESSION`.

## Usage

    substack-cli post schedule --publication example.substack.com --draft 123
"""

_POST_UNPUBLISH = """\
# substack-cli post unpublish

Returns a published post to drafts. Owner verb — needs
`$SUBSTACK_WEBGLASS_SESSION`.

## Usage

    substack-cli post unpublish 123 --publication example.substack.com
"""

_POST_DELETE = """\
# substack-cli post delete

Deletes a draft or unpublished post. Owner verb — needs
`$SUBSTACK_WEBGLASS_SESSION`.

## Usage

    substack-cli post delete 123 --publication example.substack.com
"""

_POST_OVERVIEW = """\
# substack-cli post overview

Describes the `post` noun's verb surface. Read-only, no session required.

## Usage

    substack-cli post overview
    substack-cli post overview --json
"""

_COMMENT = """\
# substack-cli comment

Read a post's comments (public `list`) and reply/delete as owner. `comment
overview` describes the verb surface.

## Usage

    substack-cli comment list --publication example.substack.com --post 42
    substack-cli comment overview
"""

_COMMENT_LIST = """\
# substack-cli comment list

Lists a post's comments, replies included: the whole thread is requested
(`all_comments=true&sort=best_first`) and the nested replies are flattened
depth-first, each parent immediately followed by its own replies (`parent_id`
and `ancestor_path` are kept on every item). Public — no session required.

## Usage

    substack-cli comment list --publication example.substack.com --post 42
"""

_COMMENT_REPLY = """\
# substack-cli comment reply

Posts a top-level comment, or a threaded reply with `--parent`. Owner verb —
needs `$SUBSTACK_WEBGLASS_SESSION`.

## Usage

    substack-cli comment reply --post 42 --body "Nice post!"
"""

_COMMENT_DELETE = """\
# substack-cli comment delete

Deletes a comment. Owner verb — needs `$SUBSTACK_WEBGLASS_SESSION`.

## Usage

    substack-cli comment delete 99
"""

_COMMENT_OVERVIEW = """\
# substack-cli comment overview

Describes the `comment` noun's verb surface. Read-only, no session required.

## Usage

    substack-cli comment overview
    substack-cli comment overview --json
"""

_REACTION = """\
# substack-cli reaction

React to a publication's posts and comments. `list` is public; `add`/`remove`
are owner verbs. `reaction overview` describes the verb surface.

## Usage

    substack-cli reaction list --post my-first-post --publication example.substack.com
    substack-cli reaction overview
"""

_REACTION_LIST = """\
# substack-cli reaction list

Lists a post's aggregate reaction counts. Public — no session required.

## Usage

    substack-cli reaction list --post my-first-post --publication example.substack.com
"""

_REACTION_ADD = """\
# substack-cli reaction add

Reacts to a post or comment (mutually exclusive `--post`/`--comment`). Owner
verb — needs `$SUBSTACK_WEBGLASS_SESSION`.

## Usage

    substack-cli reaction add --post 42
"""

_REACTION_REMOVE = """\
# substack-cli reaction remove

Removes your reaction from a post or comment. Owner verb — needs
`$SUBSTACK_WEBGLASS_SESSION`.

## Usage

    substack-cli reaction remove --post 42
"""

_REACTION_OVERVIEW = """\
# substack-cli reaction overview

Describes the `reaction` noun's verb surface. Read-only, no session required.

## Usage

    substack-cli reaction overview
    substack-cli reaction overview --json
"""

_FEED = """\
# substack-cli feed

Reads the account's Notes/reader feed. Owner verb (account-scoped, no
`--publication`). `feed overview` describes the verb surface.

## Usage

    substack-cli feed read
    substack-cli feed overview
"""

_FEED_READ = """\
# substack-cli feed read

Reads the account feed (`home` or `following` via `--source`). Owner verb —
needs `$SUBSTACK_WEBGLASS_SESSION`.

## Usage

    substack-cli feed read
    substack-cli feed read --source following --limit 10
"""

_FEED_OVERVIEW = """\
# substack-cli feed overview

Describes the `feed` noun's verb surface. Read-only, no session required.

## Usage

    substack-cli feed overview
    substack-cli feed overview --json
"""


ENTRIES: dict[tuple[str, ...], str] = {
    (): _ROOT,
    ("substack-cli",): _ROOT,
    ("substack",): _ROOT,
    ("whoami",): _WHOAMI,
    ("learn",): _LEARN,
    ("explain",): _EXPLAIN,
    ("overview",): _OVERVIEW,
    ("doctor",): _DOCTOR,
    ("cli",): _CLI,
    ("cli", "overview"): _CLI,
    ("account",): _ACCOUNT,
    ("account", "whoami"): _ACCOUNT_WHOAMI,
    ("account", "overview"): _ACCOUNT_OVERVIEW,
    ("post",): _POST,
    ("post", "list"): _POST_LIST,
    ("post", "get"): _POST_GET,
    ("post", "publish"): _POST_PUBLISH,
    ("post", "schedule"): _POST_SCHEDULE,
    ("post", "unpublish"): _POST_UNPUBLISH,
    ("post", "delete"): _POST_DELETE,
    ("post", "overview"): _POST_OVERVIEW,
    ("comment",): _COMMENT,
    ("comment", "list"): _COMMENT_LIST,
    ("comment", "reply"): _COMMENT_REPLY,
    ("comment", "delete"): _COMMENT_DELETE,
    ("comment", "overview"): _COMMENT_OVERVIEW,
    ("reaction",): _REACTION,
    ("reaction", "list"): _REACTION_LIST,
    ("reaction", "add"): _REACTION_ADD,
    ("reaction", "remove"): _REACTION_REMOVE,
    ("reaction", "overview"): _REACTION_OVERVIEW,
    ("feed",): _FEED,
    ("feed", "read"): _FEED_READ,
    ("feed", "overview"): _FEED_OVERVIEW,
}
