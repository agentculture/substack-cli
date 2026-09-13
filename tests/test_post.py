"""Tests for the `post` noun's read side (list, get, overview).

`post` is not wired into the top-level parser yet (that happens once the
whole domain surface lands), so this module builds its own tiny parser
mirroring `substack_cli.cli._build_parser`/`_dispatch` — same
`_CliArgumentParser` (structured argparse-error contract) and the same
CliError -> emit_error/exit-code translation `main()` performs — without
touching `substack_cli/cli/__init__.py`.

No test here touches the network: every case injects a fake opener via
`substack_cli.substack.http.set_opener_factory`, exactly like
`tests/test_substack_http.py`.
"""

from __future__ import annotations

import argparse
import json

import pytest

from substack_cli.cli import _CliArgumentParser
from substack_cli.cli._commands import post
from substack_cli.cli._errors import CliError
from substack_cli.cli._output import emit_error
from substack_cli.substack import http
from tests.fakes.http import make_opener_factory


@pytest.fixture(autouse=True)
def _reset_http_state(monkeypatch: pytest.MonkeyPatch):
    """Instant, deterministic sleep and a clean env/opener for every test."""
    monkeypatch.delenv("SUBSTACK_API_BASE", raising=False)
    http.set_sleep(lambda _delay: None)
    yield
    http.reset_sleep()
    http.reset_opener_factory()


def _make_parser() -> argparse.ArgumentParser:
    parser = _CliArgumentParser(prog="substack-cli")
    sub = parser.add_subparsers(dest="command", parser_class=_CliArgumentParser)
    post.register(sub)
    return parser


def run(argv: list[str]) -> int:
    """Parse `argv` against a standalone `post`-only parser and dispatch it.

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


_POST_RAW = {
    "id": 42,
    "slug": "hello-world",
    "title": "Hello, world",
    "subtitle": "an opening post",
    "post_date": "2026-09-01T00:00:00Z",
    "canonical_url": "https://example.substack.com/p/hello-world",
    "reaction_count": 3,
    "comment_count": 1,
}


# --- registration / overview -------------------------------------------------


def test_post_registers_list_get_overview() -> None:
    parser = _make_parser()
    args = parser.parse_args(["post", "list", "--publication", "example.substack.com"])
    assert args.func is post.cmd_post_list
    args = parser.parse_args(
        ["post", "get", "hello-world", "--publication", "example.substack.com"]
    )
    assert args.func is post.cmd_post_get
    args = parser.parse_args(["post", "overview"])
    assert args.func is post.cmd_post_overview


def test_post_no_verb_falls_back_to_overview(capsys: pytest.CaptureFixture[str]) -> None:
    rc = run(["post"])
    assert rc == 0
    assert "substack-cli post" in capsys.readouterr().out


def test_post_overview_text_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    rc = run(["post", "overview"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "post list" in out
    assert "post get" in out


def test_post_overview_json_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    rc = run(["post", "overview", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["subject"] == "substack-cli post"


def test_every_post_verb_accepts_json_flag() -> None:
    parser = _make_parser()
    for argv in (
        ["post", "list", "--publication", "h", "--json"],
        ["post", "get", "slug", "--publication", "h", "--json"],
        ["post", "overview", "--json"],
    ):
        args = parser.parse_args(argv)
        assert bool(getattr(args, "json", False)) is True


# --- list ---------------------------------------------------------------------


def test_post_list_empty_archive_json_exits_zero_with_empty_array(
    capsys: pytest.CaptureFixture[str],
) -> None:
    factory, opener = make_opener_factory([(200, [])])
    http.set_opener_factory(factory)

    rc = run(["post", "list", "--publication", "example.substack.com", "--json"])

    assert rc == 0
    assert json.loads(capsys.readouterr().out) == []
    assert opener.requests[0].method == "GET"
    assert "archive" in opener.requests[0].url
    assert "sort=new" in opener.requests[0].url


def test_post_list_maps_title_subtitle_under_content(
    capsys: pytest.CaptureFixture[str],
) -> None:
    factory, _opener = make_opener_factory([(200, [_POST_RAW])])
    http.set_opener_factory(factory)

    rc = run(["post", "list", "--publication", "example.substack.com", "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload) == 1
    item = payload[0]
    assert item["id"] == 42
    assert item["url"] == _POST_RAW["canonical_url"]
    assert "Hello, world" in item["content"]
    assert "an opening post" in item["content"]
    # title/subtitle text must not appear as top-level keys of its own.
    assert "title" not in item
    assert "subtitle" not in item


def test_post_list_passes_limit_and_offset(capsys: pytest.CaptureFixture[str]) -> None:
    factory, opener = make_opener_factory([(200, [])])
    http.set_opener_factory(factory)

    run(
        [
            "post",
            "list",
            "--publication",
            "example.substack.com",
            "--limit",
            "5",
            "--offset",
            "10",
            "--json",
        ]
    )

    assert "limit=5" in opener.requests[0].url
    assert "offset=10" in opener.requests[0].url


def test_post_list_bad_publication_host_exits_one(capsys: pytest.CaptureFixture[str]) -> None:
    rc = run(["post", "list", "--publication", "not a host", "--json"])
    assert rc == 1
    err = json.loads(capsys.readouterr().err)
    assert err["code"] == 1


# --- get ------------------------------------------------------------------


def test_post_get_known_slug_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    factory, opener = make_opener_factory([(200, _POST_RAW)])
    http.set_opener_factory(factory)

    rc = run(["post", "get", "hello-world", "--publication", "example.substack.com", "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload) == 1
    assert payload[0]["id"] == 42
    assert opener.requests[0].url.endswith("/posts/hello-world")


def test_post_get_unknown_slug_exits_one(capsys: pytest.CaptureFixture[str]) -> None:
    # get_json's backoff retries on any HTTP error, 404 included, so all
    # four attempts must be queued for the retries to exhaust.
    factory, opener = make_opener_factory([(404, {"error": "not found"})] * 4)
    http.set_opener_factory(factory)

    rc = run(["post", "get", "nope", "--publication", "example.substack.com", "--json"])

    assert rc == 1
    assert len(opener.requests) == 1  # 4xx fails fast, no retry
    err = json.loads(capsys.readouterr().err)
    assert err["code"] == 1
    assert "nope" in err["message"]


def test_post_get_server_error_exits_two_not_one(capsys: pytest.CaptureFixture[str]) -> None:
    factory, _opener = make_opener_factory([(500, {"error": "boom"})] * 4)
    http.set_opener_factory(factory)

    rc = run(["post", "get", "hello-world", "--publication", "example.substack.com", "--json"])

    assert rc == 2
