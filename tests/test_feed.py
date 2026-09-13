"""Tests for the `feed` noun's read side (read, overview).

`feed` is not wired into the top-level parser yet (that happens once the
whole domain surface lands), so this module builds its own tiny parser
mirroring `substack_cli.cli._build_parser`/`_dispatch` — same
`_CliArgumentParser` (structured argparse-error contract) and the same
CliError -> emit_error/exit-code translation `main()` performs — without
touching `substack_cli/cli/__init__.py`. Mirrors `tests/test_post.py`.

No test here touches the network or a real `webglass` binary: every case
injects the fake `webglass` executable from `tests/fakes/webglass/` onto
PATH and feeds it a canned WebOperationResult via `WEBGLASS_FAKE_RESPONSE`,
exactly like `tests/test_webglass_adapter.py`.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pytest

from substack_cli.cli import _CliArgumentParser
from substack_cli.cli._commands import feed
from substack_cli.cli._errors import CliError
from substack_cli.cli._output import emit_error

FAKES_DIR = Path(__file__).parent / "fakes" / "webglass"


def _prepend_fake_webglass_to_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", f"{FAKES_DIR}{os.pathsep}{os.environ.get('PATH', '')}")


def _http_result(*, status: int, body: object, lifecycle_state: str = "succeeded") -> dict:
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


def _set_canned_response(monkeypatch: pytest.MonkeyPatch, payload: dict) -> None:
    monkeypatch.setenv("WEBGLASS_FAKE_RESPONSE", json.dumps(payload))


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch: pytest.MonkeyPatch):
    """A clean env for every test: fake webglass on PATH, a session set."""
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-abc")
    monkeypatch.delenv("SUBSTACK_API_BASE", raising=False)
    yield


def _make_parser() -> argparse.ArgumentParser:
    parser = _CliArgumentParser(prog="substack-cli")
    sub = parser.add_subparsers(dest="command", parser_class=_CliArgumentParser)
    feed.register(sub)
    return parser


def run(argv: list[str]) -> int:
    """Parse `argv` against a standalone `feed`-only parser and dispatch it.

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


# --- registration / overview -------------------------------------------------


def test_feed_registers_read_and_overview() -> None:
    parser = _make_parser()
    args = parser.parse_args(["feed", "read"])
    assert args.func is feed.cmd_feed_read
    args = parser.parse_args(["feed", "overview"])
    assert args.func is feed.cmd_feed_overview


def test_feed_no_verb_falls_back_to_overview(capsys: pytest.CaptureFixture[str]) -> None:
    rc = run(["feed"])
    assert rc == 0
    assert "substack-cli feed" in capsys.readouterr().out


def test_feed_overview_text_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    rc = run(["feed", "overview"])
    assert rc == 0
    assert "feed read" in capsys.readouterr().out


def test_feed_overview_json_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    rc = run(["feed", "overview", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["subject"] == "substack-cli feed"


def test_every_feed_verb_accepts_json_flag() -> None:
    parser = _make_parser()
    for argv in (["feed", "read", "--json"], ["feed", "overview", "--json"]):
        args = parser.parse_args(argv)
        assert bool(getattr(args, "json", False)) is True


def test_feed_has_no_publication_flag() -> None:
    parser = _make_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["feed", "read", "--publication", "example.substack.com"])


# --- read: home (reader/feed) -------------------------------------------------


def test_feed_read_empty_home_feed_exits_zero_with_empty_items(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _set_canned_response(
        monkeypatch, _http_result(status=200, body={"items": [], "nextCursor": None})
    )

    rc = run(["feed", "read", "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"items": [], "next_cursor": None}


def test_feed_read_home_maps_items_and_surfaces_next_cursor(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    raw_item = {
        "id": 7,
        "author": {"name": "Ada Lovelace"},
        "date": "2026-09-01T00:00:00Z",
        "canonical_url": "https://substack.com/p/hello",
        "title": "Hello",
        "body": "a note body",
    }
    _set_canned_response(
        monkeypatch,
        _http_result(
            status=200,
            body={"items": [raw_item], "nextCursor": "cursor-2", "trackingParameters": {}},
        ),
    )

    rc = run(["feed", "read", "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["next_cursor"] == "cursor-2"
    assert len(payload["items"]) == 1
    item = payload["items"][0]
    assert item["id"] == 7
    assert item["author"] == "Ada Lovelace"
    assert item["date"] == raw_item["date"]
    assert item["url"] == raw_item["canonical_url"]
    assert "Hello" in item["content"]
    assert "a note body" in item["content"]
    assert "title" not in item
    assert "body" not in item


def test_feed_read_home_passes_limit_and_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_canned_response(monkeypatch, _http_result(status=200, body={"items": []}))

    captured: dict[str, list[str]] = {}
    from substack_cli.substack import webglass as webglass_mod

    real_run = webglass_mod.subprocess.run

    def _spy(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        captured["cmd"] = cmd
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(webglass_mod.subprocess, "run", _spy)

    run(["feed", "read", "--limit", "5", "--cursor", "abc123", "--json"])

    url = next(part for part in captured["cmd"] if "reader/feed" in part)
    assert "limit=5" in url
    assert "cursor=abc123" in url
    assert url.startswith("https://substack.com/api/v1/")


def test_feed_read_home_text_mode_renders_via_render_items(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    raw_item = {"id": 1, "name": "Grace Hopper", "text": "note text"}
    _set_canned_response(
        monkeypatch, _http_result(status=200, body={"items": [raw_item], "nextCursor": None})
    )

    rc = run(["feed", "read"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "id: 1" in out
    assert "author: Grace Hopper" in out
    assert "note text" in out


# --- read: following ----------------------------------------------------------


def test_feed_read_following_empty_array_exits_zero_with_empty_list(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _set_canned_response(monkeypatch, _http_result(status=200, body=[]))

    rc = run(["feed", "read", "--source", "following", "--json"])

    assert rc == 0
    assert json.loads(capsys.readouterr().out) == {"items": [], "next_cursor": None}


def test_feed_read_following_maps_items_and_next_cursor_is_null(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    raw_item = {"id": 3, "name": "Bell", "url": "https://substack.com/p/x", "title": "Note"}
    _set_canned_response(monkeypatch, _http_result(status=200, body=[raw_item]))

    rc = run(["feed", "read", "--source", "following", "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["next_cursor"] is None
    assert payload["items"][0]["id"] == 3
    assert payload["items"][0]["author"] == "Bell"
    assert payload["items"][0]["url"] == raw_item["url"]


def test_feed_read_following_uses_feed_following_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_canned_response(monkeypatch, _http_result(status=200, body=[]))

    captured: dict[str, list[str]] = {}
    from substack_cli.substack import webglass as webglass_mod

    real_run = webglass_mod.subprocess.run

    def _spy(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        captured["cmd"] = cmd
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(webglass_mod.subprocess, "run", _spy)

    run(["feed", "read", "--source", "following", "--limit", "9", "--json"])

    url = next(part for part in captured["cmd"] if "feed/following" in part)
    assert "limit=9" in url
    assert url.startswith("https://substack.com/api/v1/")


# --- session / error mapping ---------------------------------------------------


def test_feed_read_without_session_exits_two(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SUBSTACK_WEBGLASS_SESSION", raising=False)

    rc = run(["feed", "read", "--json"])

    assert rc == 2
    err = json.loads(capsys.readouterr().err)
    assert err["code"] == 2


def test_feed_read_anonymous_401_exits_two(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _set_canned_response(
        monkeypatch,
        _http_result(
            status=401,
            body='{"errors":[{"msg":"Please sign in"}]}',
            lifecycle_state="failed",
        ),
    )

    rc = run(["feed", "read", "--json"])

    assert rc == 2
    err = json.loads(capsys.readouterr().err)
    assert err["code"] == 2
    assert "sign in" in err["message"].lower() or "log in" in err["remediation"].lower()


# --- query encoding -----------------------------------------------------------


def _spy_on_webglass(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    from substack_cli.substack import webglass as webglass_mod

    captured: dict[str, list[str]] = {}
    real_run = webglass_mod.subprocess.run

    def _spy(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        captured["cmd"] = cmd
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(webglass_mod.subprocess, "run", _spy)
    return captured


def test_feed_read_percent_encodes_a_hostile_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    """A cursor with &, #, + and % must not be able to forge query params."""
    from urllib.parse import parse_qs, urlsplit

    _set_canned_response(monkeypatch, _http_result(status=200, body={"items": []}))
    captured = _spy_on_webglass(monkeypatch)
    cursor = "a&b=c#d+e%f"

    rc = run(["feed", "read", "--limit", "5", "--cursor", cursor, "--json"])

    assert rc == 0
    url = next(part for part in captured["cmd"] if "reader/feed" in part)
    split = urlsplit(url)
    assert split.fragment == ""
    assert "a&b=c" not in split.query
    assert parse_qs(split.query, keep_blank_values=True) == {"limit": ["5"], "cursor": [cursor]}


def test_feed_read_following_encodes_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    from urllib.parse import parse_qs, urlsplit

    _set_canned_response(monkeypatch, _http_result(status=200, body=[]))
    captured = _spy_on_webglass(monkeypatch)

    rc = run(["feed", "read", "--source", "following", "--limit", "3", "--json"])

    assert rc == 0
    url = next(part for part in captured["cmd"] if "feed/following" in part)
    assert parse_qs(urlsplit(url).query) == {"limit": ["3"]}


def test_feed_read_omits_the_cursor_param_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    from urllib.parse import parse_qs, urlsplit

    _set_canned_response(monkeypatch, _http_result(status=200, body={"items": []}))
    captured = _spy_on_webglass(monkeypatch)

    assert run(["feed", "read", "--json"]) == 0

    url = next(part for part in captured["cmd"] if "reader/feed" in part)
    assert parse_qs(urlsplit(url).query) == {"limit": ["20"]}
