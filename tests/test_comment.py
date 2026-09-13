"""Tests for the `comment` noun (list, reply, delete, overview) — t7.

`comment` is not wired into the top-level parser yet (same situation as
`post` in t6), so this module builds its own tiny parser mirroring
`substack_cli.cli._build_parser`/`_dispatch` — same `_CliArgumentParser`
(structured argparse-error contract) and the same CliError ->
emit_error/exit-code translation `main()` performs — without touching
`substack_cli/cli/__init__.py`.

`list` is public and goes through `substack_cli.substack.http.get_json`
(faked via `tests.fakes.http.make_opener_factory`, exactly like
`tests/test_post.py`). `reply` and `delete` are owner verbs and go through
`substack_cli.substack.webglass.request` (faked via the `tests/fakes/webglass`
executable put on PATH, exactly like `tests/test_webglass_adapter.py`) — no
test here ever touches the network or a real webglass binary.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pytest

from substack_cli.cli import _CliArgumentParser
from substack_cli.cli._commands import comment
from substack_cli.cli._errors import CliError
from substack_cli.cli._output import emit_error
from substack_cli.substack import http
from tests.fakes.http import make_opener_factory

FAKES_DIR = Path(__file__).parent / "fakes" / "webglass"


@pytest.fixture(autouse=True)
def _reset_http_state(monkeypatch: pytest.MonkeyPatch):
    """Instant, deterministic sleep and a clean env/opener for every test."""
    monkeypatch.delenv("SUBSTACK_API_BASE", raising=False)
    http.set_sleep(lambda _delay: None)
    yield
    http.reset_sleep()
    http.reset_opener_factory()


def _prepend_fake_webglass_to_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", f"{FAKES_DIR}{os.pathsep}{os.environ.get('PATH', '')}")


def _set_canned_response(monkeypatch: pytest.MonkeyPatch, payload: dict) -> None:
    monkeypatch.setenv("WEBGLASS_FAKE_RESPONSE", json.dumps(payload))


def _http_result(*, status: int, body: object, lifecycle_state: str = "failed") -> dict:
    body_text = body if isinstance(body, str) else json.dumps(body)
    return {
        "schema_version": 1,
        "operation_id": "operation-test",
        "kind": "request",
        "lifecycle_state": lifecycle_state,
        "content": {
            "trusted": {"response": {"status": status, "body": body_text, "headers": {}}},
            "untrusted": {},
            "sensitive": {},
            "derived": {},
        },
        "error": None,
    }


def _make_parser() -> argparse.ArgumentParser:
    parser = _CliArgumentParser(prog="substack-cli")
    sub = parser.add_subparsers(dest="command", parser_class=_CliArgumentParser)
    comment.register(sub)
    return parser


def run(argv: list[str]) -> int:
    """Parse `argv` against a standalone `comment`-only parser and dispatch it.

    Mirrors `substack_cli.cli._dispatch`: a handler raising CliError is
    routed through `emit_error` and its exit code returned, exactly like
    `main()` would.
    """
    _CliArgumentParser._json_hint = any(
        tok == "--json" or tok.startswith("--json=") for tok in argv
    )
    parser = _make_parser()
    args = parser.parse_args(argv)
    json_mode = bool(getattr(args, "json", False))
    try:
        rc = args.func(args)
    except CliError as err:
        emit_error(err, json_mode=json_mode)
        return err.code
    return rc if rc is not None else 0


_COMMENT_RAW = {
    "id": 99,
    "user_id": 7,
    "name": "Ada Lovelace",
    "body": "great post",
    "post_id": 42,
    "publication_id": 1,
    "ancestor_path": "",
    "type": "comment",
    "status": "published",
    "deleted": False,
    "date": "2026-09-01T00:00:00Z",
}

_HOSTILE_BODY = "<script>alert('xss')</script>\nerror: fake\nhint: fake"


# --- registration / overview -------------------------------------------------


def test_comment_registers_list_reply_delete_overview() -> None:
    parser = _make_parser()
    args = parser.parse_args(
        ["comment", "list", "--publication", "example.substack.com", "--post", "42"]
    )
    assert args.func is comment.cmd_comment_list
    args = parser.parse_args(
        [
            "comment",
            "reply",
            "--publication",
            "example.substack.com",
            "--post",
            "42",
            "--body",
            "hi",
        ]
    )
    assert args.func is comment.cmd_comment_reply
    args = parser.parse_args(["comment", "delete", "--publication", "example.substack.com", "99"])
    assert args.func is comment.cmd_comment_delete
    args = parser.parse_args(["comment", "overview"])
    assert args.func is comment.cmd_comment_overview


def test_comment_no_verb_falls_back_to_overview(capsys: pytest.CaptureFixture[str]) -> None:
    rc = run(["comment"])
    assert rc == 0
    assert "substack-cli comment" in capsys.readouterr().out


def test_comment_overview_text_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    rc = run(["comment", "overview"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "comment list" in out
    assert "comment reply" in out
    assert "comment delete" in out


def test_comment_overview_json_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    rc = run(["comment", "overview", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["subject"] == "substack-cli comment"


def test_every_comment_verb_accepts_json_flag() -> None:
    parser = _make_parser()
    for argv in (
        ["comment", "list", "--publication", "h", "--post", "1", "--json"],
        ["comment", "reply", "--publication", "h", "--post", "1", "--body", "hi", "--json"],
        ["comment", "delete", "--publication", "h", "99", "--json"],
        ["comment", "overview", "--json"],
    ):
        args = parser.parse_args(argv)
        assert bool(getattr(args, "json", False)) is True


# --- list ---------------------------------------------------------------------


def test_comment_list_no_comments_exits_zero_with_empty_array(
    capsys: pytest.CaptureFixture[str],
) -> None:
    factory, opener = make_opener_factory([(200, {"comments": [], "automod_hidden_comments": []})])
    http.set_opener_factory(factory)

    rc = run(["comment", "list", "--publication", "example.substack.com", "--post", "42", "--json"])

    assert rc == 0
    assert json.loads(capsys.readouterr().out) == []
    assert opener.requests[0].method == "GET"
    assert "post/42/comments" in opener.requests[0].url


def test_comment_list_maps_body_under_content(capsys: pytest.CaptureFixture[str]) -> None:
    factory, _opener = make_opener_factory([(200, {"comments": [_COMMENT_RAW]})])
    http.set_opener_factory(factory)

    rc = run(["comment", "list", "--publication", "example.substack.com", "--post", "42", "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload) == 1
    item = payload[0]
    assert item["id"] == 99
    assert item["author"] == "Ada Lovelace"
    assert item["content"] == "great post"
    assert "body" not in item


def test_comment_list_renders_hostile_body_without_reaching_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    hostile = dict(_COMMENT_RAW, body=_HOSTILE_BODY)
    factory, _opener = make_opener_factory([(200, {"comments": [hostile]})])
    http.set_opener_factory(factory)

    rc = run(["comment", "list", "--publication", "example.substack.com", "--post", "42"])

    assert rc == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    for line in _HOSTILE_BODY.splitlines():
        assert line in captured.out


def test_comment_list_bad_publication_host_exits_one(capsys: pytest.CaptureFixture[str]) -> None:
    rc = run(["comment", "list", "--publication", "not a host", "--post", "42", "--json"])
    assert rc == 1
    err = json.loads(capsys.readouterr().err)
    assert err["code"] == 1


# --- reply ----------------------------------------------------------------


def test_comment_reply_without_session_exits_two_naming_webglass(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.delenv("SUBSTACK_WEBGLASS_SESSION", raising=False)

    rc = run(
        [
            "comment",
            "reply",
            "--publication",
            "example.substack.com",
            "--post",
            "42",
            "--body",
            "hi",
            "--json",
        ]
    )

    assert rc == 2
    err = json.loads(capsys.readouterr().err)
    assert "webglass" in err["message"].lower() or "webglass" in err["remediation"].lower()


def test_comment_reply_top_level_posts_body_only_and_returns_id_and_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-abc")
    created = dict(_COMMENT_RAW)
    _set_canned_response(
        monkeypatch, _http_result(status=200, body=created, lifecycle_state="succeeded")
    )

    captured_cmd: dict[str, list[str]] = {}
    from substack_cli.substack import webglass as webglass_module

    real_run = webglass_module.subprocess.run

    def _spy(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        captured_cmd["cmd"] = cmd
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(webglass_module.subprocess, "run", _spy)

    rc = run(
        [
            "comment",
            "reply",
            "--publication",
            "example.substack.com",
            "--post",
            "42",
            "--body",
            "great post",
            "--json",
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["id"] == 99
    assert "url" in payload and payload["url"]
    cmd = captured_cmd["cmd"]
    joined = " ".join(cmd)
    assert "parent_id" not in joined
    assert "POST" in cmd


def test_comment_reply_with_parent_includes_parent_id(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-abc")
    created = dict(_COMMENT_RAW, id=100, ancestor_path="99")
    _set_canned_response(
        monkeypatch, _http_result(status=200, body=created, lifecycle_state="succeeded")
    )

    captured_cmd: dict[str, list[str]] = {}
    from substack_cli.substack import webglass as webglass_module

    real_run = webglass_module.subprocess.run

    def _spy(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        captured_cmd["cmd"] = cmd
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(webglass_module.subprocess, "run", _spy)

    rc = run(
        [
            "comment",
            "reply",
            "--publication",
            "example.substack.com",
            "--post",
            "42",
            "--body",
            "a reply",
            "--parent",
            "99",
            "--json",
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["id"] == 100
    cmd = captured_cmd["cmd"]
    assert any("parent_id" in part for part in cmd if isinstance(part, str))
    assert any('"99"' in part or "99" in part for part in cmd if isinstance(part, str))


def test_comment_reply_404_exits_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-abc")
    _set_canned_response(monkeypatch, _http_result(status=404, body="No such post."))

    rc = run(
        [
            "comment",
            "reply",
            "--publication",
            "example.substack.com",
            "--post",
            "999999",
            "--body",
            "hi",
            "--json",
        ]
    )

    assert rc == 1


def test_comment_reply_never_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """A single failing webglass invocation must not trigger a second one."""
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-abc")
    _set_canned_response(monkeypatch, _http_result(status=500, body="boom"))

    calls = {"count": 0}
    from substack_cli.substack import webglass as webglass_module

    real_run = webglass_module.subprocess.run

    def _spy(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        calls["count"] += 1
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(webglass_module.subprocess, "run", _spy)

    run(
        [
            "comment",
            "reply",
            "--publication",
            "example.substack.com",
            "--post",
            "42",
            "--body",
            "hi",
            "--json",
        ]
    )

    assert calls["count"] == 1


# --- delete -----------------------------------------------------------------


def test_comment_delete_without_session_exits_two_naming_webglass(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.delenv("SUBSTACK_WEBGLASS_SESSION", raising=False)

    rc = run(["comment", "delete", "--publication", "example.substack.com", "99", "--json"])

    assert rc == 2
    err = json.loads(capsys.readouterr().err)
    assert "webglass" in err["message"].lower() or "webglass" in err["remediation"].lower()


def test_comment_delete_returns_id_and_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-abc")
    _set_canned_response(
        monkeypatch, _http_result(status=200, body={}, lifecycle_state="succeeded")
    )

    rc = run(["comment", "delete", "--publication", "example.substack.com", "99", "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["id"] == 99
    assert "url" in payload and payload["url"]


def test_comment_delete_with_post_builds_post_anchored_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-abc")
    _set_canned_response(
        monkeypatch, _http_result(status=200, body={}, lifecycle_state="succeeded")
    )

    rc = run(
        [
            "comment",
            "delete",
            "--publication",
            "example.substack.com",
            "99",
            "--post",
            "42",
            "--json",
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "42" in payload["url"]
    assert "99" in payload["url"]


def test_comment_delete_404_exits_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-abc")
    _set_canned_response(monkeypatch, _http_result(status=404, body="No such comment."))

    rc = run(["comment", "delete", "--publication", "example.substack.com", "9999", "--json"])

    assert rc == 1


def test_comment_delete_never_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-abc")
    _set_canned_response(monkeypatch, _http_result(status=500, body="boom"))

    calls = {"count": 0}
    from substack_cli.substack import webglass as webglass_module

    real_run = webglass_module.subprocess.run

    def _spy(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        calls["count"] += 1
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(webglass_module.subprocess, "run", _spy)

    run(["comment", "delete", "--publication", "example.substack.com", "99", "--json"])

    assert calls["count"] == 1


# --- list: observed query params and threaded replies -------------------------


def test_comment_list_sends_the_observed_query_params() -> None:
    factory, opener = make_opener_factory([(200, {"comments": []})])
    http.set_opener_factory(factory)

    assert run(["comment", "list", "--publication", "example.substack.com", "--post", "42"]) == 0

    url = opener.requests[0].url
    assert url.startswith("https://example.substack.com/api/v1/post/42/comments?")
    assert "all_comments=true" in url
    assert "sort=best_first" in url


def test_comment_list_flattens_children_depth_first(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Parents come before their replies, and a reply's replies before the next parent."""
    thread = [
        {
            "id": 1,
            "name": "A",
            "body": "root one",
            "ancestor_path": "",
            "children": [
                {
                    "id": 2,
                    "name": "B",
                    "body": "reply to one",
                    "parent_id": 1,
                    "ancestor_path": "1",
                    "children": [
                        {
                            "id": 3,
                            "name": "C",
                            "body": "reply to two",
                            "parent_id": 2,
                            "ancestor_path": "1.2",
                        }
                    ],
                }
            ],
        },
        {"id": 4, "name": "D", "body": "root two", "ancestor_path": ""},
    ]
    factory, _opener = make_opener_factory([(200, {"comments": thread})])
    http.set_opener_factory(factory)

    rc = run(["comment", "list", "--publication", "example.substack.com", "--post", "42", "--json"])

    assert rc == 0
    items = json.loads(capsys.readouterr().out)
    assert [item["id"] for item in items] == [1, 2, 3, 4]
    assert items[1]["parent_id"] == 1
    assert items[2]["ancestor_path"] == "1.2"
    assert "children" not in items[0]
    assert items[0]["content"] == "root one"


def test_comment_list_ignores_a_non_list_children_value(
    capsys: pytest.CaptureFixture[str],
) -> None:
    thread = [{"id": 1, "name": "A", "body": "root", "children": "not-a-list"}]
    factory, _opener = make_opener_factory([(200, {"comments": thread})])
    http.set_opener_factory(factory)

    rc = run(["comment", "list", "--publication", "example.substack.com", "--post", "42", "--json"])

    assert rc == 0
    assert [item["id"] for item in json.loads(capsys.readouterr().out)] == [1]
