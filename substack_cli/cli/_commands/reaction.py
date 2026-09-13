"""``substack-cli reaction`` — react to a publication's posts and comments.

Endpoint facts this module is built on (see the "Reaction" section of
``docs/api/substack-endpoints.md`` for full provenance):

* ``list`` is public (no session/cookie): ``GET <pub>/api/v1/posts/<slug>``
  already carries the post's aggregate ``reactions`` map (``{emoji: count}``)
  the same response :mod:`substack_cli.cli._commands.post` already fetches
  for ``post get``. This module re-fetches it directly (rather than
  importing from ``post.py``) to stay a self-contained noun; ``list`` maps
  that map into a list of ``{"reaction": emoji, "count": n}`` items, ``[]``
  when the map is empty or absent.
* ``add``/``remove`` are authenticated and target either a post
  (``POST``/``DELETE <pub>/api/v1/post/<post_id>/reaction``) or a comment
  (``POST``/``DELETE <pub>/api/v1/comment/<comment_id>/reaction``), so both
  verbs take a mutually exclusive ``--post``/``--comment`` id. Their URLs
  are built from :func:`substack_cli.substack.http.publication_base`, so a
  ``SUBSTACK_API_BASE`` override applies to the writes exactly as it does
  to the read. They go
  through :func:`substack_cli.substack.webglass.request` -- never
  ``substack_cli.substack.http`` directly -- so a missing session or a dead
  one surfaces as ``CliError(EXIT_ENV_ERROR)`` *before* any write is
  attempted, and neither verb ever retries a write (webglass.request makes
  exactly one subprocess call).
* ``"❤"`` (heart) is the only reaction emoji value ever observed on the
  add endpoint; ``--emoji`` defaults to it and the help text says so.
* Neither the add nor the remove response carries a post/comment slug, so
  the ``url`` reported back is a best-effort ``https://<host>/p/<id>`` page
  link built from the id the caller passed in -- not derived from the
  webglass response body.
"""

from __future__ import annotations

import argparse
import re
from typing import Any

from substack_cli.cli._commands.overview import emit_overview
from substack_cli.cli._errors import CliError
from substack_cli.cli._output import emit_result
from substack_cli.substack import http, webglass

#: The only reaction emoji value observed on the add endpoint.
_DEFAULT_EMOJI = "❤"

# Same remap this module borrows from `post.py`'s pattern: `http.get_json`
# folds every HTTP failure into a single CliError(2) whose message embeds
# urllib's "HTTP Error <code>: <reason>" text. A 404 here means "no such
# post" (exit 1), not "the network/environment is broken" (exit 2).
_HTTP_ERROR_STATUS_RE = re.compile(r"HTTP Error (\d{3})")

_VERBS = [
    "reaction list --publication <host> --post <slug> [--json] — a post's "
    "aggregate reaction counts (public, no session)",
    "reaction add --publication <host> (--post <post_id> | --comment <comment_id>) "
    f"[--emoji {_DEFAULT_EMOJI}] [--json] — add a reaction (requires a webglass session)",
    "reaction remove --publication <host> (--post <post_id> | --comment <comment_id>) "
    "[--json] — remove your reaction (requires a webglass session)",
    "reaction overview — this descriptive snapshot",
]


def _reaction_url(host: str, target: str, target_id: str) -> str:
    """The add/remove endpoint for one post or comment.

    Built from :func:`substack_cli.substack.http.publication_base` rather
    than a hardcoded ``https://<host>/api/v1`` so a ``SUBSTACK_API_BASE``
    override reaches the write verbs exactly as it reaches the reads: a
    local/staging base that only redirected ``list`` would leave add/remove
    pointed at the real publication.
    """
    return f"{http.publication_base(host).rstrip('/')}/{target}/{target_id}/reaction"


def _page_url(host: str, target_id: str) -> str:
    # No slug is available from the reaction response (post or comment) --
    # this is a best-effort page link built from the id alone.
    return f"https://{host}/p/{target_id}"


def _target(args: argparse.Namespace) -> tuple[str, str]:
    post_id = getattr(args, "post", None)
    if post_id is not None:
        return "post", str(post_id)
    return "comment", str(args.comment)


def _emit_reaction_result(result: dict[str, Any], *, json_mode: bool) -> None:
    if json_mode:
        emit_result(result, json_mode=True)
        return
    emit_result(
        f"{result['target']} {result['id']}: {result['reaction']} -> {result['url']}",
        json_mode=False,
    )


def cmd_reaction_list(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    try:
        raw = http.get_json(args.publication, f"posts/{args.post}")
    except CliError as err:
        match = _HTTP_ERROR_STATUS_RE.search(err.message)
        if match and match.group(1) == "404":
            raise CliError(
                code=1,
                message=f"no such post {args.post!r} on {args.publication!r}",
                remediation="check the slug and --publication host",
            ) from err
        raise
    reactions_map = raw.get("reactions") if isinstance(raw, dict) else None
    items = (
        [{"reaction": emoji, "count": count} for emoji, count in reactions_map.items()]
        if isinstance(reactions_map, dict)
        else []
    )
    if json_mode:
        emit_result(items, json_mode=True)
    elif not items:
        emit_result("(no reactions)", json_mode=False)
    else:
        emit_result(
            "\n".join(f"{item['reaction']}: {item['count']}" for item in items),
            json_mode=False,
        )
    return 0


def cmd_reaction_add(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    target, target_id = _target(args)
    host = http.publication_host(args.publication)
    # webglass.request checks session_required() first, so a missing/dead
    # session raises CliError(EXIT_ENV_ERROR) before any subprocess runs.
    webglass.request(
        "POST", _reaction_url(host, target, target_id), json_body={"reaction": args.emoji}
    )
    result = {
        "id": target_id,
        "target": target,
        "reaction": args.emoji,
        "url": _page_url(host, target_id),
    }
    _emit_reaction_result(result, json_mode=json_mode)
    return 0


def cmd_reaction_remove(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    target, target_id = _target(args)
    host = http.publication_host(args.publication)
    webglass.request("DELETE", _reaction_url(host, target, target_id))
    result = {
        "id": target_id,
        "target": target,
        # The DELETE response carries no emoji -- 'heart' is the only
        # observed reaction value, so it is reported as a best-effort label.
        "reaction": _DEFAULT_EMOJI,
        "url": _page_url(host, target_id),
    }
    _emit_reaction_result(result, json_mode=json_mode)
    return 0


def _reaction_sections() -> list[dict[str, object]]:
    return [
        {"title": "Verbs", "items": list(_VERBS)},
        {
            "title": "Notes",
            "items": [
                "list is public (no session); add/remove go through the webglass "
                "adapter and never retry a write",
                f"{_DEFAULT_EMOJI!r} is the only observed reaction emoji value",
                "add/remove results report {id, target, reaction, url}; url is a "
                "best-effort https://<host>/p/<id> page link since the reaction "
                "endpoints return no slug",
            ],
        },
    ]


def cmd_reaction_overview(args: argparse.Namespace) -> int:
    emit_overview(
        "substack-cli reaction",
        _reaction_sections(),
        json_mode=bool(getattr(args, "json", False)),
    )
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "reaction",
        help="React to a publication's posts and comments (see "
        "'substack-cli reaction overview').",
    )
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    p.set_defaults(func=cmd_reaction_overview, json=False)
    # `p` is a _CliArgumentParser (top-level subparsers were built with that
    # parser_class); propagate it so `reaction <verb>` parse errors route
    # through the structured error contract instead of argparse's default
    # exit 2.
    noun_sub = p.add_subparsers(dest="reaction_command", parser_class=type(p))

    list_p = noun_sub.add_parser(
        "list", help="List a post's aggregate reaction counts (public, no session)."
    )
    list_p.add_argument(
        "--publication", required=True, help="Publication host, e.g. example.substack.com"
    )
    list_p.add_argument("--post", required=True, help="Post slug, e.g. my-first-post")
    list_p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    list_p.set_defaults(func=cmd_reaction_list)

    add_p = noun_sub.add_parser(
        "add", help="Add a reaction to a post or comment (requires a webglass session)."
    )
    add_p.add_argument(
        "--publication", required=True, help="Publication host, e.g. example.substack.com"
    )
    add_group = add_p.add_mutually_exclusive_group(required=True)
    add_group.add_argument("--post", help="Post id to react to.")
    add_group.add_argument("--comment", help="Comment id to react to.")
    add_p.add_argument(
        "--emoji",
        default=_DEFAULT_EMOJI,
        help=f"Reaction emoji (default {_DEFAULT_EMOJI!r} -- the only value Substack "
        "has been observed to accept).",
    )
    add_p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    add_p.set_defaults(func=cmd_reaction_add)

    remove_p = noun_sub.add_parser(
        "remove",
        help="Remove your reaction from a post or comment (requires a webglass session).",
    )
    remove_p.add_argument(
        "--publication", required=True, help="Publication host, e.g. example.substack.com"
    )
    remove_group = remove_p.add_mutually_exclusive_group(required=True)
    remove_group.add_argument("--post", help="Post id to remove your reaction from.")
    remove_group.add_argument("--comment", help="Comment id to remove your reaction from.")
    remove_p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    remove_p.set_defaults(func=cmd_reaction_remove)

    ov = noun_sub.add_parser("overview", help="Describe the reaction noun's verb surface.")
    ov.add_argument("--json", action="store_true", help="Emit structured JSON.")
    ov.set_defaults(func=cmd_reaction_overview)
