"""Tests for the markdown -> ProseMirror body builder (substack_cli.substack.body).

The builder is pure and offline: no HTTP, no webglass, no filesystem. Every
case here pins one of two things — the exact node shape the observed Substack
editor sends (docs/api/substack-endpoints.md, "Post, owner side"), or the
CliError(1) contract for a construct outside the supported subset.
"""

from __future__ import annotations

import json

import pytest

from substack_cli.cli._errors import EXIT_USER_ERROR, CliError
from substack_cli.substack import body


def _blocks(markdown: str) -> list[dict]:
    doc = body.markdown_to_prosemirror(markdown)
    assert doc["type"] == "doc"
    return doc["content"]


# --- document root ----------------------------------------------------------


def test_doc_root_shape() -> None:
    doc = body.markdown_to_prosemirror("hello")
    assert doc == {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "attrs": {"textAlign": None},
                "content": [{"type": "text", "text": "hello"}],
            }
        ],
    }


def test_empty_markdown_yields_empty_doc() -> None:
    assert body.markdown_to_prosemirror("   \n\n  ") == {"type": "doc", "content": []}


def test_document_serializes_to_json_string() -> None:
    # draft_body is sent as a JSON *string*, so the doc must be serializable.
    text = body.to_draft_body("# Title\n\nbody text")
    assert isinstance(text, str)
    assert json.loads(text)["type"] == "doc"


# --- headings ---------------------------------------------------------------


@pytest.mark.parametrize("level", [1, 2, 3])
def test_atx_headings_levels_one_to_three(level: int) -> None:
    blocks = _blocks(f"{'#' * level} Heading text")
    assert blocks[0]["type"] == "heading"
    assert blocks[0]["attrs"] == {"level": level}
    assert blocks[0]["content"] == [{"type": "text", "text": "Heading text"}]


def test_heading_level_four_is_unsupported() -> None:
    with pytest.raises(CliError) as exc:
        body.markdown_to_prosemirror("#### too deep")
    assert exc.value.code == EXIT_USER_ERROR
    assert "heading" in exc.value.message.lower()
    assert "--body-json" in exc.value.remediation


# --- paragraphs and inline marks --------------------------------------------


def test_paragraph_joins_wrapped_lines() -> None:
    blocks = _blocks("one line\nand its continuation")
    assert len(blocks) == 1
    assert blocks[0]["content"] == [{"type": "text", "text": "one line and its continuation"}]


def test_blank_line_separates_paragraphs() -> None:
    blocks = _blocks("first\n\nsecond")
    assert [b["type"] for b in blocks] == ["paragraph", "paragraph"]
    assert blocks[1]["content"][0]["text"] == "second"


def test_bold_mark() -> None:
    nodes = _blocks("a **bold** word")[0]["content"]
    assert nodes == [
        {"type": "text", "text": "a "},
        {"type": "text", "text": "bold", "marks": [{"type": "strong"}]},
        {"type": "text", "text": " word"},
    ]


def test_italic_mark() -> None:
    nodes = _blocks("an *italic* word")[0]["content"]
    assert nodes[1] == {"type": "text", "text": "italic", "marks": [{"type": "em"}]}


def test_link_mark_carries_href() -> None:
    nodes = _blocks("see [the docs](https://example.substack.com/p/hello)")[0]["content"]
    assert nodes[-1] == {
        "type": "text",
        "text": "the docs",
        "marks": [{"type": "link", "attrs": {"href": "https://example.substack.com/p/hello"}}],
    }


def test_bold_and_italic_in_one_paragraph() -> None:
    nodes = _blocks("**b** and *i*")[0]["content"]
    marks = [n.get("marks", [{}])[0].get("type") for n in nodes]
    assert "strong" in marks and "em" in marks


# --- lists ------------------------------------------------------------------


def test_bullet_list() -> None:
    blocks = _blocks("- one\n- two")
    assert blocks[0]["type"] == "bulletList"
    items = blocks[0]["content"]
    assert len(items) == 2
    assert items[0]["type"] == "listItem"
    assert items[0]["content"][0]["type"] == "paragraph"
    assert items[0]["content"][0]["content"][0]["text"] == "one"


def test_ordered_list() -> None:
    blocks = _blocks("1. first\n2. second")
    assert blocks[0]["type"] == "orderedList"
    assert len(blocks[0]["content"]) == 2
    assert blocks[0]["content"][1]["content"][0]["content"][0]["text"] == "second"


def test_list_item_keeps_inline_marks() -> None:
    blocks = _blocks("- a **bold** item")
    para = blocks[0]["content"][0]["content"][0]
    assert para["content"][1]["marks"] == [{"type": "strong"}]


def test_list_ends_at_blank_line() -> None:
    blocks = _blocks("- one\n\nafter")
    assert [b["type"] for b in blocks] == ["bulletList", "paragraph"]


def test_nested_list_is_unsupported() -> None:
    with pytest.raises(CliError) as exc:
        body.markdown_to_prosemirror("- one\n  - nested")
    assert exc.value.code == EXIT_USER_ERROR
    assert "nested list" in exc.value.message.lower()
    assert "--body-json" in exc.value.remediation


# --- images -----------------------------------------------------------------


def test_image_line_becomes_image2_node() -> None:
    blocks = _blocks("![alt text](https://example.substack.com/img.png)")
    assert blocks[0] == {
        "type": "image2",
        "attrs": {"src": "https://example.substack.com/img.png"},
    }


def test_inline_image_inside_a_paragraph_is_unsupported() -> None:
    with pytest.raises(CliError) as exc:
        body.markdown_to_prosemirror("text ![alt](https://example.substack.com/img.png) more")
    assert exc.value.code == EXIT_USER_ERROR
    assert "--body-json" in exc.value.remediation


# --- unsupported constructs -------------------------------------------------


@pytest.mark.parametrize(
    ("markdown", "needle"),
    [
        ("```\ncode\n```", "code"),
        ("~~~\ncode\n~~~", "code"),
        ("> quoted", "quote"),
        ("| a | b |\n| - | - |", "table"),
        ("<div>raw</div>", "html"),
        ("plain `code span` here", "code"),
        ("    indented code", "indent"),
    ],
)
def test_unsupported_constructs_raise_user_error(markdown: str, needle: str) -> None:
    with pytest.raises(CliError) as exc:
        body.markdown_to_prosemirror(markdown)
    assert exc.value.code == EXIT_USER_ERROR
    assert needle in exc.value.message.lower()
    # the remediation must name the escape hatch
    assert "--body-json" in exc.value.remediation


def test_unsupported_error_names_the_line_number() -> None:
    with pytest.raises(CliError) as exc:
        body.markdown_to_prosemirror("fine\n\n> quoted")
    assert "line 3" in exc.value.message


# --- module provenance ------------------------------------------------------


def test_module_cites_python_substack_as_shape_reference() -> None:
    assert "python-substack" in (body.__doc__ or "")
