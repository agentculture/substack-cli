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

Write side (t10): ``publish`` (create a draft, then optionally publish it),
``schedule``, ``unpublish`` and ``delete``. These are owner verbs: they need
the logged-in browser session, so they go through
:mod:`substack_cli.substack.webglass` rather than the urllib transport, and
they never retry. Every endpoint they call is one observed in
``docs/api/substack-endpoints.md`` ("Post, owner side").
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from typing import Any

from substack_cli.cli._commands._help import JSON_HELP, PUBLICATION_HELP
from substack_cli.cli._commands.overview import emit_overview
from substack_cli.cli._errors import CliError
from substack_cli.cli._output import emit_diagnostic, emit_error, emit_result
from substack_cli.substack import body, http, webglass
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

#: Remediation for every --body-json rejection: unparseable, or parseable but
#: not a ProseMirror document.
_PROSEMIRROR_REMEDIATION = (
    'pass a file containing a ProseMirror document ({"type": "doc", "content": [...]})'
)

_VERBS = [
    "post list --publication <host> [--limit N] [--offset N] — list a publication's archive",
    "post get <slug> --publication <host> — fetch one post by slug",
    "post publish --publication <host> (--markdown <file> | --body-json <file>) --title <t> "
    "[--subtitle <s>] [--send] [--no-email] — create a draft, and with --send publish it",
    "post schedule --publication <host> --draft <id> --at <iso8601> — schedule a draft",
    "post unpublish <post_id> --publication <host> — return a published post to drafts",
    "post delete <post_id> --publication <host> — delete a draft or unpublished post",
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
    if isinstance(raw, list):
        posts = raw
    elif isinstance(raw, dict):
        posts = raw.get("posts", [])
    else:
        posts = []
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


# --- write side (t10) --------------------------------------------------------
#
# Every endpoint below appears in docs/api/substack-endpoints.md ("Post, owner
# side") with the observed request body. Owner verbs never use
# `substack_cli.substack.http`'s urllib transport: the auth lives in the
# browser session, so each request goes through the webglass adapter, which
# makes exactly one subprocess call. Writes are never retried -- replaying a
# create/publish/delete against an unknown server state is unsafe.


def _api_url(host: str, path: str) -> str:
    """Build a publication API URL, validating `host` (CliError(1) if bad)."""
    return http.publication_base(host).rstrip("/") + "/" + path.lstrip("/")


def _response_body(result: dict[str, Any]) -> dict[str, Any]:
    """Parse the JSON body out of a successful WebOperationResult.

    A body that is absent, empty or not a JSON object (``unpublish`` and
    ``delete`` answer with an empty body / ``{}``) yields ``{}`` rather than
    an error: the *call* succeeded, and these verbs take their id from the
    arguments, not the response.
    """
    content = result.get("content")
    trusted = content.get("trusted") if isinstance(content, dict) else None
    response = trusted.get("response") if isinstance(trusted, dict) else None
    body = response.get("body") if isinstance(response, dict) else None
    if isinstance(body, dict):
        return body
    if isinstance(body, str) and body.strip():
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _post_url(host: str, post_id: Any, body: dict[str, Any]) -> str:
    """Public post URL when the response carries a slug, else the editor URL."""
    slug = body.get("slug")
    if isinstance(slug, str) and slug:
        return f"https://{host}/p/{slug}"
    return f"https://{host}/publish/post/{post_id}"


def _emit_post_result(data: dict[str, Any], *, json_mode: bool) -> None:
    """Emit a write-verb envelope on stdout (JSON, or one ``key: value`` per line)."""
    if json_mode:
        emit_result(data, json_mode=True)
        return
    emit_result("\n".join(f"{key}: {value}" for key, value in data.items()), json_mode=False)


def _read_file(path: str, kind: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError as exc:
        raise CliError(
            code=2,
            message=f"cannot read {kind} file {path!r}: {exc.strerror or exc}",
            remediation=f"check the path passed to --{kind} and that the file is readable",
        ) from exc


def _draft_body(args: argparse.Namespace) -> str:
    """Return the ``draft_body`` string from --markdown or --body-json.

    A ``--body-json`` file must decode to a *ProseMirror document*: a
    top-level object with ``"type": "doc"`` and a list-valued ``content``.
    Anything else (``null``, a bare array of nodes, a scalar, ``{}``, or a
    single ``paragraph`` node someone pulled out of a document) is rejected
    here with ``CliError(1)`` — valid JSON that Substack's editor cannot
    load. Catching it locally costs nothing; letting it through creates a
    draft whose body silently fails to render.
    """
    if args.body_json:
        raw = _read_file(args.body_json, "body-json")
        try:
            document = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CliError(
                code=1,
                message=f"--body-json file {args.body_json!r} is not valid JSON: {exc}",
                remediation=_PROSEMIRROR_REMEDIATION,
            ) from exc
        if (
            not isinstance(document, dict)
            or document.get("type") != "doc"
            or not isinstance(document.get("content"), list)
        ):
            raise CliError(
                code=1,
                message=f"--body-json file {args.body_json!r} is not a ProseMirror document "
                '(needs a top-level object with "type": "doc" and a list "content")',
                remediation=_PROSEMIRROR_REMEDIATION,
            )
        return json.dumps(document, ensure_ascii=False)
    return body.to_draft_body(_read_file(args.markdown, "markdown"))


def _current_user_id(host: str) -> int:
    """Read the signed-in user's id from ``GET <pub>/api/v1/subscription``."""
    result = webglass.request("GET", _api_url(host, "subscription"))
    user_id = _response_body(result).get("user_id")
    if user_id is None:
        raise CliError(
            code=2,
            message="could not determine the signed-in user from "
            f"GET {_api_url(host, 'subscription')} (no user_id in the response)",
            remediation="confirm the webglass session is signed in to this "
            "publication, then retry",
        )
    return user_id


def cmd_post_publish(args: argparse.Namespace) -> int:
    """Create a draft, and with --send publish it. Never retries either step.

    ``--send`` without ``--no-email`` posts ``send: true``, which emails the
    publication's subscribers. That path is **unverified**: only the
    ``send: false`` (web-only) publish was exercised against the live API,
    and ``docs/api/substack-endpoints.md`` records ``send: true`` as "not
    exercised". Hence the stderr warning before an emailing publish -- the
    irreversible branch is the one nobody has watched work.
    """
    json_mode = bool(getattr(args, "json", False))
    host = http.publication_host(args.publication)
    # Build the body *before* any network call so unsupported markdown fails
    # at exit 1 without creating a half-finished draft.
    draft_body = _draft_body(args)

    send = bool(args.send) and not bool(args.no_email)
    if args.send and not args.no_email:
        emit_diagnostic(
            "warning: --send without --no-email will email this publication's "
            "subscribers; pass --no-email to publish on the web only"
        )

    payload = {
        "draft_title": args.title,
        "draft_subtitle": args.subtitle or "",
        "draft_body": draft_body,
        "type": "newsletter",
        "audience": "everyone",
        "draft_bylines": [{"id": _current_user_id(host), "is_guest": False}],
    }
    draft = _response_body(webglass.request("POST", _api_url(host, "drafts"), payload))
    draft_id = draft.get("id")
    url = _post_url(host, draft_id, draft)

    if not args.send:
        _emit_post_result(
            {"id": draft_id, "draft_id": draft_id, "url": url, "published": False},
            json_mode=json_mode,
        )
        return 0

    try:
        published = _response_body(
            webglass.request(
                "POST",
                _api_url(host, f"drafts/{draft_id}/publish"),
                {"send": send, "saved_segment_id": None},
            )
        )
    except CliError as err:
        # Partial state: the draft exists, publishing did not happen. The
        # result still goes to stdout (an agent needs the draft id to retry or
        # clean up), the failure to stderr, and the exit code is always 2 --
        # the CLI left the publication in a state the caller did not ask for,
        # whatever the underlying status was.
        _emit_post_result(
            {
                "id": draft_id,
                "draft_id": draft_id,
                "url": url,
                "published": False,
                "error": err.message,
            },
            json_mode=json_mode,
        )
        emit_error(err, json_mode=json_mode)
        return 2

    _emit_post_result(
        {
            "id": published.get("id", draft_id),
            "draft_id": draft_id,
            "url": _post_url(host, draft_id, published or draft),
            "published": True,
            "emailed": send,
        },
        json_mode=json_mode,
    )
    return 0


def cmd_post_schedule(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    host = http.publication_host(args.publication)
    try:
        datetime.fromisoformat(args.at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CliError(
            code=1,
            message=f"--at {args.at!r} is not an ISO 8601 timestamp",
            remediation="pass an ISO 8601 timestamp, e.g. 2026-10-01T09:00:00Z",
        ) from exc

    result = _response_body(
        webglass.request(
            "POST",
            _api_url(host, f"drafts/{args.draft}/scheduled_release"),
            {"trigger_at": args.at, "post_audience": "everyone", "saved_segment_id": None},
        )
    )
    _emit_post_result(
        {
            "id": result.get("id", args.draft),
            "url": _post_url(host, args.draft, result),
            "scheduled_at": args.at,
        },
        json_mode=json_mode,
    )
    return 0


def cmd_post_unpublish(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    host = http.publication_host(args.publication)
    result = _response_body(
        webglass.request("POST", _api_url(host, f"drafts/{args.post_id}/unpublish"), {})
    )
    _emit_post_result(
        {
            "id": args.post_id,
            "url": _post_url(host, args.post_id, result),
            "published": False,
        },
        json_mode=json_mode,
    )
    return 0


def cmd_post_delete(args: argparse.Namespace) -> int:
    json_mode = bool(getattr(args, "json", False))
    host = http.publication_host(args.publication)
    result = _response_body(webglass.request("DELETE", _api_url(host, f"drafts/{args.post_id}")))
    _emit_post_result(
        {"id": args.post_id, "url": _post_url(host, args.post_id, result), "deleted": True},
        json_mode=json_mode,
    )
    return 0


def _post_sections() -> list[dict[str, object]]:
    return [
        {"title": "Verbs", "items": list(_VERBS)},
        {
            "title": "Notes",
            "items": [
                "list/get are public endpoints, no session/cookie required",
                "title/subtitle (author-supplied text) are rendered only under 'content'",
                "publish/schedule/unpublish/delete need a webglass session "
                "($SUBSTACK_WEBGLASS_SESSION); without one they exit 2",
                "publish without --send creates a draft only; --send --no-email "
                "publishes on the web without emailing subscribers",
                "writes are never retried; a publish that fails after the draft "
                "was created still reports the draft id and exits 2",
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
    p.add_argument("--json", action="store_true", help=JSON_HELP)
    p.set_defaults(func=cmd_post_overview, json=False)
    # `p` is a _CliArgumentParser (top-level subparsers were built with that
    # parser_class); propagate it so `post <verb>` parse errors route through
    # the structured error contract instead of argparse's default exit 2.
    noun_sub = p.add_subparsers(dest="post_command", parser_class=type(p))

    list_p = noun_sub.add_parser("list", help="List a publication's archive (newest first).")
    list_p.add_argument("--publication", required=True, help=PUBLICATION_HELP)
    list_p.add_argument("--limit", type=int, default=_DEFAULT_LIMIT)
    list_p.add_argument("--offset", type=int, default=_DEFAULT_OFFSET)
    list_p.add_argument("--json", action="store_true", help=JSON_HELP)
    list_p.set_defaults(func=cmd_post_list)

    get_p = noun_sub.add_parser("get", help="Fetch one post by slug.")
    get_p.add_argument("slug", help="Post slug, e.g. my-first-post")
    get_p.add_argument("--publication", required=True, help=PUBLICATION_HELP)
    get_p.add_argument("--json", action="store_true", help=JSON_HELP)
    get_p.set_defaults(func=cmd_post_get)

    ov = noun_sub.add_parser("overview", help="Describe the post noun's verb surface.")
    ov.add_argument("--json", action="store_true", help=JSON_HELP)
    ov.set_defaults(func=cmd_post_overview)

    # --- write verbs (t10) register below this line ---

    pub_p = noun_sub.add_parser("publish", help="Create a draft and optionally publish it.")
    pub_p.add_argument("--publication", required=True, help=PUBLICATION_HELP)
    body_src = pub_p.add_mutually_exclusive_group(required=True)
    body_src.add_argument("--markdown", help="Path to a markdown file (restricted subset).")
    body_src.add_argument("--body-json", dest="body_json", help="Path to a ProseMirror JSON file.")
    pub_p.add_argument("--title", required=True, help="Post title.")
    pub_p.add_argument("--subtitle", default="", help="Post subtitle.")
    pub_p.add_argument(
        "--send",
        action="store_true",
        help="Publish the draft (not just create it). NOTE: only the "
        "--send --no-email path (send: false) has been exercised against the "
        "live API; the emailing path (send: true) is unverified and is "
        "recorded as 'not exercised' in docs/api/substack-endpoints.md.",
    )
    pub_p.add_argument(
        "--no-email",
        dest="no_email",
        action="store_true",
        help="With --send, publish on the web only (no email to subscribers).",
    )
    pub_p.add_argument("--json", action="store_true", help=JSON_HELP)
    pub_p.set_defaults(func=cmd_post_publish)

    sched_p = noun_sub.add_parser("schedule", help="Schedule an existing draft for publication.")
    sched_p.add_argument("--publication", required=True, help=PUBLICATION_HELP)
    sched_p.add_argument("--draft", required=True, help="Draft id to schedule.")
    sched_p.add_argument(
        "--at", required=True, help="ISO 8601 timestamp, e.g. 2026-10-01T09:00:00Z"
    )
    sched_p.add_argument("--json", action="store_true", help=JSON_HELP)
    sched_p.set_defaults(func=cmd_post_schedule)

    unpub_p = noun_sub.add_parser("unpublish", help="Return a published post to drafts.")
    unpub_p.add_argument("post_id", help="Post/draft id.")
    unpub_p.add_argument("--publication", required=True, help=PUBLICATION_HELP)
    unpub_p.add_argument("--json", action="store_true", help=JSON_HELP)
    unpub_p.set_defaults(func=cmd_post_unpublish)

    del_p = noun_sub.add_parser("delete", help="Delete a draft or unpublished post.")
    del_p.add_argument("post_id", help="Post/draft id.")
    del_p.add_argument("--publication", required=True, help=PUBLICATION_HELP)
    del_p.add_argument("--json", action="store_true", help=JSON_HELP)
    del_p.set_defaults(func=cmd_post_delete)
