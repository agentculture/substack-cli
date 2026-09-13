"""``substack-cli feed`` — read the account's Notes/reader feed (t9).

Account-scoped (no ``--publication`` flag): every verb hits
``https://substack.com/api/v1`` (:func:`substack_cli.substack.http.account_base`)
through the authenticated :func:`substack_cli.substack.webglass.request`
adapter, since both observed endpoints require a signed-in session (a 401
"Please sign in" body when anonymous — see ``docs/api/substack-endpoints.md``'s
Feed section).

Two sources, selected with ``--source``:

* ``home`` (default) — ``GET reader/feed?limit=N[&cursor=<value>]`` ->
  ``{items, originalCursorTimestamp, nextCursor, trackingParameters}``. This
  is the Notes home feed; it is cursor-paginated, so its ``--json`` envelope
  surfaces ``nextCursor`` as ``next_cursor`` for a caller to pass back in on
  the next call.
* ``following`` — ``GET feed/following?limit=N`` -> a bare JSON array. Not
  paginated in the observed contract, so ``next_cursor`` is always ``null``.

Item shapes were not captured for either endpoint (see the Feed section's
"not captured" note), so items are treated as opaque dicts: :func:`_to_render_item`
builds a render.py item from whichever of ``id``/``name``/``author.name``/
``date``/``canonical_url``/``url`` are present, and folds any text-bearing
field (``body``, ``text``, ``title``) into the single untrusted ``content``
key render.py expects.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from substack_cli.cli._commands.overview import emit_overview
from substack_cli.cli._errors import CliError
from substack_cli.cli._output import emit_result
from substack_cli.substack import http, webglass
from substack_cli.substack.render import render_items

_DEFAULT_LIMIT = 20
_SOURCES = ("home", "following")

_VERBS = [
    "feed read [--source home|following] [--limit N] [--cursor <token>] — read the account feed",
    "feed overview — this descriptive snapshot",
]


def _response_body(result: dict[str, Any]) -> Any:
    """Pull and JSON-decode the HTTP response body out of a webglass result.

    ``webglass.request`` already raised (via ``map_failure``) for a failed
    lifecycle_state, so by the time this runs the request succeeded and
    carries an HTTP-shaped ``content.trusted.response`` — this only handles
    the body being a JSON *string* (the normal shape) or already-decoded.
    """
    trusted = result.get("content", {})
    trusted = trusted.get("trusted") if isinstance(trusted, dict) else None
    response = trusted.get("response") if isinstance(trusted, dict) else None
    body = response.get("body") if isinstance(response, dict) else None
    if body is None:
        return None
    if isinstance(body, (dict, list)):
        return body
    try:
        return json.loads(body)
    except (TypeError, ValueError) as exc:
        raise CliError(
            code=2,
            message="feed response body was not valid JSON",
            remediation="run the equivalent 'webglass request ... --json' command "
            "manually to inspect the raw body",
        ) from exc


def _to_render_item(raw: dict[str, Any]) -> dict[str, Any]:
    """Map an opaque feed item into render.py's untrusted-item shape.

    Trusted metadata (id/author/date/url) is pulled from whichever of
    ``id``/``name``/``author.name``/``date``/``canonical_url``/``url`` are
    present; any text-bearing field (``body``, ``text``, ``title`` — all
    third-party/author-supplied text) is folded into ``content``.
    """
    item: dict[str, Any] = {}

    if raw.get("id") is not None:
        item["id"] = raw["id"]

    author = raw.get("name")
    nested_author = raw.get("author")
    if isinstance(nested_author, dict) and nested_author.get("name"):
        author = nested_author["name"]
    if author is not None:
        item["author"] = author

    if raw.get("date") is not None:
        item["date"] = raw["date"]

    url = raw.get("canonical_url") or raw.get("url")
    if url is not None:
        item["url"] = url

    content_parts = [str(raw[key]) for key in ("body", "text", "title") if raw.get(key)]
    item["content"] = "\n\n".join(content_parts)

    return item


def cmd_feed_read(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    source = args.source
    base = http.account_base().rstrip("/")

    if source == "following":
        url = f"{base}/feed/following?limit={args.limit}"
    else:
        url = f"{base}/reader/feed?limit={args.limit}"
        if args.cursor:
            url = f"{url}&cursor={args.cursor}"

    result = webglass.request("GET", url)
    body = _response_body(result)

    if source == "following":
        raw_items = body if isinstance(body, list) else []
        next_cursor = None
    else:
        raw_items = body.get("items", []) if isinstance(body, dict) else []
        next_cursor = body.get("nextCursor") if isinstance(body, dict) else None

    items = [_to_render_item(raw) for raw in raw_items if isinstance(raw, dict)]

    if json_mode:
        emit_result({"items": items, "next_cursor": next_cursor}, json_mode=True)
    else:
        render_items(items, json_mode=False)
    return 0


def _feed_sections() -> list[dict[str, object]]:
    return [
        {"title": "Verbs", "items": list(_VERBS)},
        {
            "title": "Notes",
            "items": [
                "account-scoped: no --publication flag, always https://substack.com/api/v1",
                "session required (webglass) — exits 2 when unauthenticated",
                "home (reader/feed) is cursor-paginated; following (feed/following) is not",
                "item shapes are opaque; text fields render only under 'content'",
            ],
        },
    ]


def cmd_feed_overview(args: argparse.Namespace) -> int:
    emit_overview(
        "substack-cli feed",
        _feed_sections(),
        json_mode=bool(getattr(args, "json", False)),
    )
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "feed",
        help="Read the account's Notes/reader feed (see 'substack-cli feed overview').",
    )
    p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    p.set_defaults(func=cmd_feed_overview, json=False)
    # `p` is a _CliArgumentParser (top-level subparsers were built with that
    # parser_class); propagate it so `feed <verb>` parse errors route through
    # the structured error contract instead of argparse's default exit 2.
    noun_sub = p.add_subparsers(dest="feed_command", parser_class=type(p))

    read_p = noun_sub.add_parser("read", help="Read the account feed.")
    read_p.add_argument(
        "--source", choices=_SOURCES, default="home", help="Which feed to read (default: home)."
    )
    read_p.add_argument("--limit", type=int, default=_DEFAULT_LIMIT)
    read_p.add_argument(
        "--cursor", default=None, help="Pagination cursor (home source only; from next_cursor)."
    )
    read_p.add_argument("--json", action="store_true", help="Emit structured JSON.")
    read_p.set_defaults(func=cmd_feed_read)

    ov = noun_sub.add_parser("overview", help="Describe the feed noun's verb surface.")
    ov.add_argument("--json", action="store_true", help="Emit structured JSON.")
    ov.set_defaults(func=cmd_feed_overview)
