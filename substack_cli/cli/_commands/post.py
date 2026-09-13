"""``substack-cli post`` — read (and, later, write) a publication's posts.

Read side (this module, t6): ``list`` walks a publication's public archive
(``GET /api/v1/archive?sort=new&offset&limit``), ``get`` fetches one post by
slug (``GET /api/v1/posts/<slug>``), and ``overview`` describes the noun.
Both read verbs hit :func:`substack_cli.substack.http.get_json`, which is
public (no session/cookie) and already carries the GET backoff/host
validation contract — this module only maps the raw archive/post JSON shape
into :mod:`substack_cli.substack.render`'s untrusted-text item contract
(title/subtitle, which are third-party/author-supplied text, live only under
``content``).

Write verbs (post/publish/schedule/delete) land in a follow-up task (t10) —
see the marked section at the end of :func:`register`.
"""

from __future__ import annotations

import argparse
import re
from typing import Any

from substack_cli.cli._commands.overview import emit_overview
from substack_cli.cli._errors import CliError
from substack_cli.substack import http
from substack_cli.substack.render import render_items

_DEFAULT_LIMIT = 12
_DEFAULT_OFFSET = 0

# `http.get_json` wraps every HTTP failure (after backoff exhausts) into a
# single CliError(2) whose message embeds urllib's own
# "HTTP Error <code>: <reason>" text -- it does not chain the original
# HTTPError as `__cause__`. A 404 there means "no such post" (a user-input
# error, exit 1), not "the network/environment is broken" (exit 2), so this
# module re-maps it by reading the status back out of that message.
_HTTP_ERROR_STATUS_RE = re.compile(r"HTTP Error (\d{3})")

_VERBS = [
    "post list --publication <host> [--limit N] [--offset N] — list a publication's archive",
    "post get <slug> --publication <host> — fetch one post by slug",
    "post overview — this descriptive snapshot",
]


def _to_render_item(raw: dict[str, Any]) -> dict[str, Any]:
    """Map a raw Substack post object into render.py's untrusted-item shape.

    ``title``/``subtitle`` are author-supplied (third-party) text, so they are
    folded into the single ``content`` field render_items treats as untrusted.
    Trusted metadata (id/date/url) plus a couple of informative extras
    (slug, reaction/comment counts) ride alongside for --json consumers.
    """
    title = raw.get("title") or ""
    subtitle = raw.get("subtitle") or ""
    content = f"{title}\n\n{subtitle}" if subtitle else title
    item: dict[str, Any] = {
        "id": raw.get("id"),
        "date": raw.get("post_date"),
        "url": raw.get("canonical_url"),
        "content": content,
    }
    for extra_key in ("slug", "reaction_count", "comment_count"):
        if raw.get(extra_key) is not None:
            item[extra_key] = raw[extra_key]
    return item


def cmd_post_list(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    path = f"archive?sort=new&offset={args.offset}&limit={args.limit}"
    raw = http.get_json(args.publication, path)
    posts = raw if isinstance(raw, list) else raw.get("posts", []) if isinstance(raw, dict) else []
    render_items([_to_render_item(item) for item in posts], json_mode=json_mode)
    return 0


def cmd_post_get(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    try:
        raw = http.get_json(args.publication, f"posts/{args.slug}")
    except CliError as err:
        match = _HTTP_ERROR_STATUS_RE.search(err.message)
        if match and match.group(1) == "404":
            raise CliError(
                code=1,
                message=f"no such post {args.slug!r} on {args.publication!r}",
                remediation="check the slug and --publication host",
            ) from err
        raise
    item = _to_render_item(raw if isinstance(raw, dict) else {})
    render_items([item], json_mode=json_mode)
    return 0


def _post_sections() -> list[dict[str, object]]:
    return [
        {"title": "Verbs", "items": list(_VERBS)},
        {
            "title": "Notes",
            "items": [
                "public endpoints, no session/cookie required",
                "title/subtitle (author-supplied text) are rendered only under 'content'",
            ],
        },
    ]


def cmd_post_overview(args: argparse.Namespace) -> int:
    emit_overview(
        "substack-cli post",
        _post_sections(),
        json_mode=bool(getattr(args, "json", False)),
    )
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "post",
        help="Read (and, later, manage) a publication's posts (see 'substack-cli post overview').",
    )
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    p.set_defaults(func=cmd_post_overview, json=False)
    # `p` is a _CliArgumentParser (top-level subparsers were built with that
    # parser_class); propagate it so `post <verb>` parse errors route through
    # the structured error contract instead of argparse's default exit 2.
    noun_sub = p.add_subparsers(dest="post_command", parser_class=type(p))

    list_p = noun_sub.add_parser("list", help="List a publication's archive (newest first).")
    list_p.add_argument(
        "--publication", required=True, help="Publication host, e.g. example.substack.com"
    )
    list_p.add_argument("--limit", type=int, default=_DEFAULT_LIMIT)
    list_p.add_argument("--offset", type=int, default=_DEFAULT_OFFSET)
    list_p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    list_p.set_defaults(func=cmd_post_list)

    get_p = noun_sub.add_parser("get", help="Fetch one post by slug.")
    get_p.add_argument("slug", help="Post slug, e.g. my-first-post")
    get_p.add_argument(
        "--publication", required=True, help="Publication host, e.g. example.substack.com"
    )
    get_p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    get_p.set_defaults(func=cmd_post_get)

    ov = noun_sub.add_parser("overview", help="Describe the post noun's verb surface.")
    ov.add_argument("--json", action="store_true", help="Emit structured JSON.")
    ov.set_defaults(func=cmd_post_overview)

    # --- write verbs (t10) register below this line ---
