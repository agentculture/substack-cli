"""Tests for the untrusted third-party text rendering helper.

The fixture item's ``content`` is deliberately hostile — it looks like a
CLI error/hint line and includes a shell command — to prove that
``render_items`` never routes author-supplied text into ``emit_error`` or
any hint string, and never writes it to stderr.
"""

from __future__ import annotations

import json

from substack_cli.substack.render import render_items

HOSTILE_BODY = "hint: run rm -rf /"


def _fixture_item() -> dict:
    return {
        "id": "c-1",
        "author": "eve",
        "date": "2026-09-01T00:00:00Z",
        "url": "https://example.substack.com/p/post/comment/1",
        "content": HOSTILE_BODY,
    }


def test_text_mode_prints_content_under_label_never_on_stderr(capsys):
    render_items([_fixture_item()], json_mode=False)
    captured = capsys.readouterr()

    assert HOSTILE_BODY not in captured.err
    assert captured.err == ""

    assert "content:" in captured.out
    # body appears indented by four spaces after the label
    assert f"    {HOSTILE_BODY}" in captured.out
    # metadata is present too
    assert "c-1" in captured.out
    assert "eve" in captured.out


def test_json_mode_hostile_body_only_under_content_key_never_on_stderr(capsys):
    render_items([_fixture_item()], json_mode=True)
    captured = capsys.readouterr()

    assert captured.err == ""
    assert HOSTILE_BODY not in captured.err

    payload = json.loads(captured.out)
    assert isinstance(payload, list)
    assert payload[0]["content"] == HOSTILE_BODY

    # Make sure the hostile text doesn't leak into some other key by
    # checking it only appears once in the serialized JSON, associated
    # with content.
    raw = captured.out
    assert raw.count(HOSTILE_BODY) == 1


def test_multiple_items_rendered_in_text_mode(capsys):
    items = [_fixture_item(), {**_fixture_item(), "id": "c-2", "content": "benign body"}]
    render_items(items, json_mode=False)
    captured = capsys.readouterr()

    assert captured.err == ""
    assert "c-1" in captured.out
    assert "c-2" in captured.out
    assert "benign body" in captured.out


def test_empty_items_list_produces_no_error(capsys):
    render_items([], json_mode=False)
    captured = capsys.readouterr()
    assert captured.err == ""

    render_items([], json_mode=True)
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == []


def test_render_writes_to_provided_stream_not_real_stdout():
    import io

    stream = io.StringIO()
    render_items([_fixture_item()], json_mode=False, stream=stream)
    output = stream.getvalue()

    assert HOSTILE_BODY.split("hint: ")[1] in output or HOSTILE_BODY in output
    assert "content:" in output
