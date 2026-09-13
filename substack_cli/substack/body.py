"""Markdown (restricted subset) -> ProseMirror document builder.

Substack posts are ProseMirror documents; the editor sends them as a JSON
**string** in ``draft_body`` (see ``docs/api/substack-endpoints.md``, "Post,
owner side"). The observed root is ``{"type": "doc", "content": [...]}`` and
the observed paragraph carries ``attrs {"textAlign": null}``, which this
builder mirrors exactly.

Node *shapes* (doc/paragraph/heading/bulletList/listItem/link+strong+em marks)
are cited from **ma2za/python-substack** (MIT) — the shape only, as a
reference for what Substack accepts. No code is copied or imported from it;
this module is stdlib-only, like the rest of the runtime package.

The supported markdown subset is deliberately small and *closed*: ATX
headings ``#``..``###``, paragraphs, ``**bold**``, ``*italic*``,
``[text](url)`` links, ``-`` bullet lists, ``1.`` ordered lists, and a
standalone ``![alt](url)`` image line. Everything else — fenced or indented
code, code spans, tables, block quotes, raw HTML, nested lists, deeper
headings, inline images — raises ``CliError(EXIT_USER_ERROR)`` naming the
construct and pointing at ``--body-json``. A silently-dropped construct would
publish a post that does not match what the author wrote, so the builder
refuses rather than guesses.
"""

from __future__ import annotations

import json
import re
from typing import Any

from substack_cli.cli._errors import EXIT_USER_ERROR, CliError

#: ATX heading: one to six '#' then whitespace. Only 1-3 are supported.
_HEADING_RE = re.compile(r"^(#{1,6})(\s+|$)")
_BULLET_RE = re.compile(r"^[-*+]\s+")
_ORDERED_RE = re.compile(r"^\d+\.\s+")
_IMAGE_LINE_RE = re.compile(r"^!\[([^\]]*)\]\(\s*(\S+?)\s*\)$")
_HTML_RE = re.compile(r"<\s*/?[A-Za-z!][^>]*>")

#: Inline tokens, scanned left to right in one pass so that ``**bold**`` is
#: never mis-read as two ``*italic*`` delimiters.
_INLINE_RE = re.compile(
    r"\*\*(?P<bold>[^*]+?)\*\*"
    r"|\*(?P<italic>[^*]+?)\*"
    r"|\[(?P<link_text>[^\]]+)\]\(\s*(?P<link_url>\S+?)\s*\)"
)

_REMEDIATION_TAIL = (
    "is outside the supported markdown subset (headings # to ###, paragraphs, "
    "**bold**, *italic*, [links](url), '-' and '1.' lists, and a standalone "
    "![alt](url) image line); remove it, or pass a ProseMirror document with "
    "--body-json <file> instead of --markdown"
)


def _unsupported(construct: str, line_no: int) -> CliError:
    return CliError(
        code=EXIT_USER_ERROR,
        message=f"unsupported markdown at line {line_no}: {construct}",
        remediation=f"{construct} {_REMEDIATION_TAIL}",
    )


def _check_inline(text: str, line_no: int) -> None:
    """Reject inline constructs the subset does not cover."""
    if "`" in text:
        raise _unsupported("inline code span", line_no)
    if "![" in text:
        raise _unsupported("inline image (an image must be alone on its line)", line_no)
    if _HTML_RE.search(text):
        raise _unsupported("raw html", line_no)


def _text_node(text: str, mark: dict[str, Any] | None = None) -> dict[str, Any]:
    node: dict[str, Any] = {"type": "text", "text": text}
    if mark is not None:
        node["marks"] = [mark]
    return node


def _inline_nodes(text: str, line_no: int) -> list[dict[str, Any]]:
    """Tokenize one block's text into ProseMirror text nodes with marks."""
    _check_inline(text, line_no)

    nodes: list[dict[str, Any]] = []
    cursor = 0
    for match in _INLINE_RE.finditer(text):
        if match.start() > cursor:
            nodes.append(_text_node(text[cursor : match.start()]))
        if match.group("bold") is not None:
            nodes.append(_text_node(match.group("bold"), {"type": "strong"}))
        elif match.group("italic") is not None:
            nodes.append(_text_node(match.group("italic"), {"type": "em"}))
        else:
            nodes.append(
                _text_node(
                    match.group("link_text"),
                    {"type": "link", "attrs": {"href": match.group("link_url")}},
                )
            )
        cursor = match.end()
    if cursor < len(text):
        nodes.append(_text_node(text[cursor:]))
    return nodes


def _paragraph(text: str, line_no: int) -> dict[str, Any]:
    return {
        "type": "paragraph",
        "attrs": {"textAlign": None},
        "content": _inline_nodes(text, line_no),
    }


def _guard_block_start(line: str, line_no: int) -> None:
    """Raise for any block-level construct outside the subset."""
    stripped = line.strip()
    indent = line[: len(line) - len(line.lstrip())]

    if "\t" in indent or len(indent) >= 4:
        raise _unsupported("indented code block", line_no)
    if indent and (_BULLET_RE.match(stripped) or _ORDERED_RE.match(stripped)):
        raise _unsupported("nested list", line_no)
    if stripped.startswith(("```", "~~~")):
        raise _unsupported("fenced code block", line_no)
    if stripped.startswith(">"):
        raise _unsupported("block quote", line_no)
    if stripped.startswith("|"):
        raise _unsupported("table row", line_no)
    if _HTML_RE.match(stripped):
        raise _unsupported("raw html", line_no)

    heading = _HEADING_RE.match(stripped)
    if heading is not None and len(heading.group(1)) > 3:
        raise _unsupported(
            f"heading level {len(heading.group(1))} (only # to ### are supported)", line_no
        )


def _is_block_start(line: str) -> bool:
    """True if `line` begins a new block rather than continuing a paragraph."""
    stripped = line.strip()
    if not stripped:
        return True
    return bool(
        _HEADING_RE.match(stripped)
        or _BULLET_RE.match(stripped)
        or _ORDERED_RE.match(stripped)
        or _IMAGE_LINE_RE.match(stripped)
    )


def _collect_list(
    lines: list[str], start: int, marker: re.Pattern[str]
) -> tuple[list[dict[str, Any]], int]:
    items: list[dict[str, Any]] = []
    index = start
    while index < len(lines):
        line = lines[index]
        _guard_block_start(line, index + 1)
        match = marker.match(line.strip())
        if match is None:
            break
        text = line.strip()[match.end() :].strip()
        items.append({"type": "listItem", "content": [_paragraph(text, index + 1)]})
        index += 1
    return items, index


def markdown_to_prosemirror(markdown: str) -> dict[str, Any]:
    """Convert the supported markdown subset into a ProseMirror document.

    Raises ``CliError(EXIT_USER_ERROR)`` (exit 1) for any construct outside
    the subset, naming both the construct and the ``--body-json`` escape
    hatch. Never silently drops content.
    """
    lines = (markdown or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    content: list[dict[str, Any]] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue

        _guard_block_start(line, index + 1)
        stripped = line.strip()
        line_no = index + 1

        heading = _HEADING_RE.match(stripped)
        if heading is not None:
            level = len(heading.group(1))
            content.append(
                {
                    "type": "heading",
                    "attrs": {"level": level},
                    "content": _inline_nodes(stripped[heading.end() :].strip(), line_no),
                }
            )
            index += 1
            continue

        image = _IMAGE_LINE_RE.match(stripped)
        if image is not None:
            content.append({"type": "image2", "attrs": {"src": image.group(2)}})
            index += 1
            continue

        if _BULLET_RE.match(stripped):
            items, index = _collect_list(lines, index, _BULLET_RE)
            content.append({"type": "bulletList", "content": items})
            continue

        if _ORDERED_RE.match(stripped):
            items, index = _collect_list(lines, index, _ORDERED_RE)
            content.append({"type": "orderedList", "content": items})
            continue

        # Paragraph: consume wrapped continuation lines.
        parts = [stripped]
        index += 1
        while index < len(lines) and not _is_block_start(lines[index]):
            _guard_block_start(lines[index], index + 1)
            parts.append(lines[index].strip())
            index += 1
        content.append(_paragraph(" ".join(parts), line_no))

    return {"type": "doc", "content": content}


def to_draft_body(markdown: str) -> str:
    """Return the ``draft_body`` string Substack expects (a serialized doc)."""
    return json.dumps(markdown_to_prosemirror(markdown), ensure_ascii=False)
