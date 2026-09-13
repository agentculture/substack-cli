"""``substack-cli comment`` — read a post's comments; reply/delete as owner.

Read side: ``list`` walks a post's comment thread
(``GET <pub>/api/v1/post/<post_id>/comments``), public, no session required.
It hits :func:`substack_cli.substack.http.get_json`, exactly like
:mod:`substack_cli.cli._commands.post`'s read verbs, and maps the raw
comment JSON shape into :mod:`substack_cli.substack.render`'s untrusted-text
item contract (a comment ``body`` is third-party/author-supplied text, so it
lives only under ``content``).

Write side: ``reply`` (``POST <pub>/api/v1/post/<post_id>/comment``, with an
optional ``parent_id`` for a threaded reply) and ``delete``
(``DELETE <pub>/api/v1/comment/<comment_id>``) both go through
:func:`substack_cli.substack.webglass.request` — the subprocess adapter onto
the sibling ``webglass`` CLI, since owner writes need the signed-in browser
session, never a substack-cli-held credential. All three endpoints (create,
reply-with-parent_id, delete) are **observed** in
``docs/api/substack-endpoints.md``'s Comment section, so no verb here is
"unverified": nothing in this module ships against an unobserved shape.

Neither write verb ever retries: :func:`webglass.request` makes exactly one
subprocess call per invocation (POST/DELETE are not idempotent), matching
the "writes never retry" contract :mod:`substack_cli.substack.http` already
documents for its own ``request_json``.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from substack_cli.cli._commands.overview import emit_overview
from substack_cli.cli._output import emit_result
from substack_cli.substack import http, webglass
from substack_cli.substack.render import render_items

_VERBS = [
    "comment list --publication <host> --post <post_id> [--json] — list a post's comments"
    " (public)",
    "comment reply --publication <host> --post <post_id> --body <text> [--parent <comment_id>]"
    " [--json] — post a top-level comment, or a threaded reply with --parent (owner, via"
    " webglass)",
    "comment delete --publication <host> <comment_id> [--post <post_id>] [--json] — delete a"
    " comment (owner, via webglass)",
    "comment overview — this descriptive snapshot",
]


def _to_render_item(raw: dict[str, Any]) -> dict[str, Any]:
    """Map a raw Substack comment object into render.py's untrusted-item shape.

    ``body`` is author-supplied (third-party) text, so it is the sole
    ``content`` field render_items treats as untrusted. Trusted metadata
    (id/author/date) plus a couple of informative extras (post_id,
    ancestor_path) ride alongside for --json consumers.
    """
    item: dict[str, Any] = {
        "id": raw.get("id"),
        "author": raw.get("name"),
        "date": raw.get("date"),
        "content": raw.get("body") or "",
    }
    for extra_key in ("post_id", "ancestor_path"):
        if raw.get(extra_key) is not None:
            item[extra_key] = raw[extra_key]
    return item


def cmd_comment_list(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    raw = http.get_json(args.publication, f"post/{args.post}/comments")
    comments = raw.get("comments", []) if isinstance(raw, dict) else []
    render_items([_to_render_item(item) for item in comments], json_mode=json_mode)
    return 0


def _comment_page_url(host: str, post_id: str, comment_id: object) -> str:
    """Best-effort link to a comment on its post page.

    The comment API response never carries the post's slug, only its
    numeric id, so this can't build the real ``/p/<slug>/comment/<id>``
    permalink Substack shows in the UI. Instead it anchors into the post's
    comment thread by post id: ``https://<host>/p/<post_id>/comments#comment-<id>``.
    Good enough for an agent to locate the comment; not guaranteed to be the
    exact canonical URL a browser would resolve.
    """
    return f"https://{host}/p/{post_id}/comments#comment-{comment_id}"


def _webglass_response_json(result: dict[str, Any]) -> dict[str, Any]:
    """Parse the JSON body of a successful webglass HTTP-shaped result.

    ``webglass.map_failure`` has already run and raised on any failure by
    the time this is called, so `result`'s ``lifecycle_state`` is
    ``"succeeded"``. The HTTP body still arrives as a raw string (webglass
    doesn't parse it for us) and, per the delete endpoint's observed shape,
    can legitimately be ``"{}"`` or empty.
    """
    content = result.get("content")
    trusted = content.get("trusted") if isinstance(content, dict) else None
    response = trusted.get("response") if isinstance(trusted, dict) else None
    body = response.get("body") if isinstance(response, dict) else None
    if not body:
        return {}
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def cmd_comment_reply(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    host = http.publication_host(args.publication)
    url = f"{http.publication_base(host)}/post/{args.post}/comment"
    body: dict[str, Any] = {"body": args.body}
    if args.parent is not None:
        body["parent_id"] = args.parent

    result = webglass.request("POST", url, json_body=body)
    created = _webglass_response_json(result)
    comment_id = created.get("id")
    payload = {"id": comment_id, "url": _comment_page_url(host, args.post, comment_id)}
    emit_result(payload, json_mode=json_mode)
    return 0


def cmd_comment_delete(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    host = http.publication_host(args.publication)
    url = f"{http.publication_base(host)}/comment/{args.comment_id}"

    webglass.request("DELETE", url)
    post_ref = args.post if args.post is not None else "unknown-post"
    payload = {"id": args.comment_id, "url": _comment_page_url(host, post_ref, args.comment_id)}
    emit_result(payload, json_mode=json_mode)
    return 0


def _comment_sections() -> list[dict[str, object]]:
    return [
        {"title": "Verbs", "items": list(_VERBS)},
        {
            "title": "Notes",
            "items": [
                "list is public, no session/cookie required",
                "reply and delete are owner verbs: routed through webglass, never retried",
                "comment bodies (author-supplied text) are rendered only under 'content'",
                "reply/delete --json results carry 'id' and a best-effort 'url'"
                " (post-anchored; the API never returns the post slug)",
            ],
        },
    ]


def cmd_comment_overview(args: argparse.Namespace) -> int:
    emit_overview(
        "substack-cli comment",
        _comment_sections(),
        json_mode=bool(getattr(args, "json", False)),
    )
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "comment",
        help="Read a post's comments, and reply/delete as owner (see"
        " 'substack-cli comment overview').",
    )
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    p.set_defaults(func=cmd_comment_overview, json=False)
    # `p` is a _CliArgumentParser (top-level subparsers were built with that
    # parser_class); propagate it so `comment <verb>` parse errors route
    # through the structured error contract instead of argparse's default
    # exit 2.
    noun_sub = p.add_subparsers(dest="comment_command", parser_class=type(p))

    list_p = noun_sub.add_parser("list", help="List a post's comments (public).")
    list_p.add_argument(
        "--publication", required=True, help="Publication host, e.g. example.substack.com"
    )
    list_p.add_argument("--post", required=True, help="Post id, e.g. 42")
    list_p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    list_p.set_defaults(func=cmd_comment_list)

    reply_p = noun_sub.add_parser(
        "reply",
        help="Post a top-level comment, or a threaded reply with --parent (owner, via"
        " webglass).",
    )
    reply_p.add_argument(
        "--publication", required=True, help="Publication host, e.g. example.substack.com"
    )
    reply_p.add_argument("--post", required=True, help="Post id to comment on, e.g. 42")
    reply_p.add_argument("--body", required=True, help="Comment text.")
    reply_p.add_argument(
        "--parent", default=None, help="Parent comment id, to post a threaded reply."
    )
    reply_p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    reply_p.set_defaults(func=cmd_comment_reply)

    delete_p = noun_sub.add_parser("delete", help="Delete a comment (owner, via webglass).")
    delete_p.add_argument("comment_id", type=int, help="Comment id to delete, e.g. 99")
    delete_p.add_argument(
        "--publication", required=True, help="Publication host, e.g. example.substack.com"
    )
    delete_p.add_argument(
        "--post",
        default=None,
        help="Post id the comment belongs to (only used to build a nicer --json 'url').",
    )
    delete_p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    delete_p.set_defaults(func=cmd_comment_delete)

    ov = noun_sub.add_parser("overview", help="Describe the comment noun's verb surface.")
    ov.add_argument("--json", action="store_true", help="Emit structured JSON.")
    ov.set_defaults(func=cmd_comment_overview)
