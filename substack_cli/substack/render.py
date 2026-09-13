"""Untrusted third-party text rendering helper.

Comment/feed/post nouns share this module to render items that carry
**author-supplied, untrusted** text (a comment body, a post body, a feed
entry excerpt) alongside trusted metadata (id, author, date, url).

Security contract: the untrusted text lives only under the ``content`` key
of each item. It is written to stdout — in text mode as an indented block
under a ``content:`` label, in JSON mode as the ``content`` field of the
emitted object — and it is **never** passed to :func:`substack_cli.cli._output.emit_error`
or interpolated into any ``error:`` / ``hint:`` string. Diagnostics for this
module, if any, must stay confined to fixed, non-interpolated messages.
"""

from __future__ import annotations

from typing import Any, TextIO

from substack_cli.cli._output import emit_result

_METADATA_KEYS = ("id", "author", "date", "url")


def _render_item_text(item: dict[str, Any]) -> str:
    lines = [f"{key}: {item[key]}" for key in _METADATA_KEYS if key in item]
    lines.append("  content:")
    body = item.get("content", "")
    for body_line in str(body).splitlines() or [""]:
        lines.append(f"    {body_line}")
    return "\n".join(lines)


def render_items(
    items: list[dict[str, Any]],
    *,
    json_mode: bool,
    stream: TextIO | None = None,
) -> None:
    """Render a list of items whose ``content`` key holds untrusted text.

    Each item carries trusted metadata (``id``, ``author``, ``date``, ``url``)
    and one untrusted ``content`` field. In text mode, metadata lines are
    printed followed by a ``  content:`` label and the body indented by four
    spaces, verbatim (no escaping, no truncation). In JSON mode, items are
    emitted as-is via :func:`emit_result` so the untrusted text sits only
    under the ``content`` key of the JSON payload.

    Untrusted content is never routed through :class:`CliError` or any
    ``error:``/``hint:`` string, and never written to stderr.
    """
    if json_mode:
        emit_result(items, json_mode=True, stream=stream)
        return

    text = "\n\n".join(_render_item_text(item) for item in items)
    emit_result(text, json_mode=False, stream=stream)
