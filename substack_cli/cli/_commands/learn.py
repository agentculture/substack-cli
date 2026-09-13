"""``substack-cli learn`` — the learnability affordance.

Prints a structured self-teaching prompt. Must satisfy the agent-first rubric:
>=200 chars and mention purpose, command map, exit codes, --json, and explain.
"""

from __future__ import annotations

import argparse

from substack_cli import __version__
from substack_cli.cli._output import emit_result

_TEXT = """\
substack-cli — an agent-first CLI to manage a Substack publication and account.
Unofficial community tool, not affiliated with Substack.

Purpose
-------
Publish and schedule posts, read posts and comments, react to posts/comments,
and read the account feed, all from one agent-first CLI (cited from the teken
`python-cli` reference). Ships with an identity (culture.yaml + CLAUDE.md), the
canonical guildmaster skill kit under .claude/skills/, and a deploy/CI baseline.

Commands
--------
  substack-cli whoami                    Identity from culture.yaml.
  substack-cli learn                     This self-teaching prompt.
  substack-cli explain <path>...         Markdown docs for any noun/verb path.
  substack-cli overview                  Descriptive snapshot of the agent.
  substack-cli doctor                    Check the agent-identity invariants.
  substack-cli cli overview              Describe the CLI surface itself.
  substack-cli account whoami            Account identity via the webglass session.
  substack-cli account overview          Describe the account noun's verbs.
  substack-cli post list                 List a publication's archive (public).
  substack-cli post get                  Fetch one post by slug (public).
  substack-cli post publish              Create/publish a draft (owner).
  substack-cli post schedule             Schedule a draft (owner).
  substack-cli post unpublish            Return a post to drafts (owner).
  substack-cli post delete               Delete a draft/unpublished post (owner).
  substack-cli post overview             Describe the post noun's verbs.
  substack-cli comment list              List a post's comments (public).
  substack-cli comment reply             Reply to a post/comment (owner).
  substack-cli comment delete            Delete a comment (owner).
  substack-cli comment overview          Describe the comment noun's verbs.
  substack-cli reaction list             List a post's reaction counts (public).
  substack-cli reaction add              React to a post/comment (owner).
  substack-cli reaction remove           Remove your reaction (owner).
  substack-cli reaction overview         Describe the reaction noun's verbs.
  substack-cli feed read                 Read the account's Notes feed (owner).
  substack-cli feed overview             Describe the feed noun's verbs.

Authentication
---------------
"public" verbs need no session — they are stdlib GET calls. "owner" verbs act
on your own account and need a webglass session named by
$SUBSTACK_WEBGLASS_SESSION, whose browser profile is signed in to Substack.
Until webglass-cli ships authenticated sessions
(agentculture/webglass-cli#17), owner verbs report exit 2.

Machine-readable output
-----------------------
Every command supports --json. Errors in JSON mode emit
{"code", "message", "remediation"} to stderr. Stdout and stderr never mix.

Exit-code policy
----------------
  0 success
  1 user-input error (bad flag, bad path, missing arg)
  2 environment / setup error
  3+ reserved

More detail
-----------
  substack-cli explain substack-cli
"""


def _as_json_payload() -> dict[str, object]:
    return {
        "tool": "substack-cli",
        "version": __version__,
        "purpose": (
            "Agent-first CLI to manage a Substack publication and account: "
            "publish/schedule posts, read posts and comments, react, and read "
            "the account feed (unofficial, not affiliated with Substack)."
        ),
        "commands": [
            {"path": ["whoami"], "summary": "Identity probe from culture.yaml.", "access": "local"},
            {"path": ["learn"], "summary": "Self-teaching prompt.", "access": "local"},
            {"path": ["explain"], "summary": "Markdown docs by path.", "access": "local"},
            {
                "path": ["overview"],
                "summary": "Descriptive snapshot of the agent.",
                "access": "local",
            },
            {
                "path": ["doctor"],
                "summary": "Check the agent-identity invariants.",
                "access": "local",
            },
            {
                "path": ["cli", "overview"],
                "summary": "Describe the CLI surface.",
                "access": "local",
            },
            {
                "path": ["account", "whoami"],
                "summary": "Account identity via the webglass session.",
                "access": "owner",
            },
            {
                "path": ["account", "overview"],
                "summary": "Describe the account noun's verb surface.",
                "access": "local",
            },
            {
                "path": ["post", "list"],
                "summary": "List a publication's archive (newest first).",
                "access": "public",
            },
            {
                "path": ["post", "get"],
                "summary": "Fetch one post by slug.",
                "access": "public",
            },
            {
                "path": ["post", "publish"],
                "summary": "Create a draft and optionally publish it.",
                "access": "owner",
            },
            {
                "path": ["post", "schedule"],
                "summary": "Schedule an existing draft for publication.",
                "access": "owner",
            },
            {
                "path": ["post", "unpublish"],
                "summary": "Return a published post to drafts.",
                "access": "owner",
            },
            {
                "path": ["post", "delete"],
                "summary": "Delete a draft or unpublished post.",
                "access": "owner",
            },
            {
                "path": ["post", "overview"],
                "summary": "Describe the post noun's verb surface.",
                "access": "local",
            },
            {
                "path": ["comment", "list"],
                "summary": "List a post's comments.",
                "access": "public",
            },
            {
                "path": ["comment", "reply"],
                "summary": "Post a top-level comment or a threaded reply.",
                "access": "owner",
            },
            {
                "path": ["comment", "delete"],
                "summary": "Delete a comment.",
                "access": "owner",
            },
            {
                "path": ["comment", "overview"],
                "summary": "Describe the comment noun's verb surface.",
                "access": "local",
            },
            {
                "path": ["reaction", "list"],
                "summary": "List a post's aggregate reaction counts.",
                "access": "public",
            },
            {
                "path": ["reaction", "add"],
                "summary": "React to a publication's post or comment.",
                "access": "owner",
            },
            {
                "path": ["reaction", "remove"],
                "summary": "Remove your reaction from a post or comment.",
                "access": "owner",
            },
            {
                "path": ["reaction", "overview"],
                "summary": "Describe the reaction noun's verb surface.",
                "access": "local",
            },
            {
                "path": ["feed", "read"],
                "summary": "Read the account's Notes/reader feed.",
                "access": "owner",
            },
            {
                "path": ["feed", "overview"],
                "summary": "Describe the feed noun's verb surface.",
                "access": "local",
            },
        ],
        "exit_codes": {
            "0": "success",
            "1": "user-input error",
            "2": "environment/setup error",
        },
        "json_support": True,
        "explain_pointer": "substack-cli explain <path>",
    }


def cmd_learn(args: argparse.Namespace) -> int:
    if getattr(args, "json", False):
        emit_result(_as_json_payload(), json_mode=True)
    else:
        emit_result(_TEXT, json_mode=False)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "learn",
        help="Print a structured self-teaching prompt for agent consumers.",
    )
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    p.set_defaults(func=cmd_learn)
