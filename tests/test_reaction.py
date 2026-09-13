"""Tests for the `reaction` noun (list, add, remove, overview).

`reaction` is not wired into the top-level parser yet (that happens once the
whole domain surface lands), so this module builds its own tiny parser
mirroring `substack_cli.cli._build_parser`/`_dispatch` -- same
`_CliArgumentParser` (structured argparse-error contract) and the same
CliError -> emit_error/exit-code translation `main()` performs -- without
touching `substack_cli/cli/__init__.py`.

`list` never touches the network: it injects a fake opener via
`substack_cli.substack.http.set_opener_factory`, exactly like
`tests/test_post.py`. `add`/`remove` never invoke the real `webglass`
binary: they inject the fake `webglass` executable
(`tests/fakes/webglass/webglass`) onto PATH and feed it a canned
`WebOperationResult` via `$WEBGLASS_FAKE_RESPONSE`, exactly like
`tests/test_webglass_adapter.py`.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pytest

from substack_cli.cli import _CliArgumentParser
from substack_cli.cli._commands import reaction
from substack_cli.cli._errors import CliError
from substack_cli.cli._output import emit_error
from substack_cli.substack import http, webglass
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


def _http_result(*, status: int, body: str, lifecycle_state: str = "succeeded") -> dict:
    return {
        "schema_version": 1,
        "operation_id": "operation-test",
        "kind": "request",
        "lifecycle_state": lifecycle_state,
        "content": {
            "trusted": {"response": {"status": status, "body": body, "headers": {}}},
            "untrusted": {},
            "sensitive": {},
            "derived": {},
        },
        "error": None,
    }


def _make_parser() -> argparse.ArgumentParser:
    parser = _CliArgumentParser(prog="substack-cli")
    sub = parser.add_subparsers(dest="command", parser_class=_CliArgumentParser)
    reaction.register(sub)
    return parser


def run(argv: list[str]) -> int:
    """Parse `argv` against a standalone `reaction`-only parser and dispatch it.

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


def test_reaction_registers_list_add_remove_overview() -> None:
    parser = _make_parser()
    args = parser.parse_args(
        ["reaction", "list", "--publication", "example.substack.com", "--post", "hello-world"]
    )
    assert args.func is reaction.cmd_reaction_list
    args = parser.parse_args(
        ["reaction", "add", "--publication", "example.substack.com", "--post", "42"]
    )
    assert args.func is reaction.cmd_reaction_add
    args = parser.parse_args(
        ["reaction", "remove", "--publication", "example.substack.com", "--post", "42"]
    )
    assert args.func is reaction.cmd_reaction_remove
    args = parser.parse_args(["reaction", "overview"])
    assert args.func is reaction.cmd_reaction_overview


def test_reaction_no_verb_falls_back_to_overview(capsys: pytest.CaptureFixture[str]) -> None:
    rc = run(["reaction"])
    assert rc == 0
    assert "substack-cli reaction" in capsys.readouterr().out


def test_reaction_overview_text_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    rc = run(["reaction", "overview"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "reaction list" in out
    assert "reaction add" in out
    assert "reaction remove" in out


def test_reaction_overview_json_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    rc = run(["reaction", "overview", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["subject"] == "substack-cli reaction"


def test_every_reaction_verb_accepts_json_flag() -> None:
    parser = _make_parser()
    for argv in (
        ["reaction", "list", "--publication", "h", "--post", "s", "--json"],
        ["reaction", "add", "--publication", "h", "--post", "1", "--json"],
        ["reaction", "remove", "--publication", "h", "--post", "1", "--json"],
        ["reaction", "overview", "--json"],
    ):
        args = parser.parse_args(argv)
        assert bool(getattr(args, "json", False)) is True


# --- list ---------------------------------------------------------------------


def test_reaction_list_no_reactions_exits_zero_with_empty_array(
    capsys: pytest.CaptureFixture[str],
) -> None:
    factory, opener = make_opener_factory([(200, {"id": 1, "reactions": {}})])
    http.set_opener_factory(factory)

    rc = run(
        [
            "reaction",
            "list",
            "--publication",
            "example.substack.com",
            "--post",
            "hello-world",
            "--json",
        ]
    )

    assert rc == 0
    assert json.loads(capsys.readouterr().out) == []
    assert opener.requests[0].method == "GET"
    assert opener.requests[0].url.endswith("/posts/hello-world")


def test_reaction_list_missing_reactions_key_exits_zero_with_empty_array(
    capsys: pytest.CaptureFixture[str],
) -> None:
    factory, _opener = make_opener_factory([(200, {"id": 1})])
    http.set_opener_factory(factory)

    rc = run(
        [
            "reaction",
            "list",
            "--publication",
            "example.substack.com",
            "--post",
            "hello-world",
            "--json",
        ]
    )

    assert rc == 0
    assert json.loads(capsys.readouterr().out) == []


def test_reaction_list_maps_reactions_map_to_list(capsys: pytest.CaptureFixture[str]) -> None:
    factory, _opener = make_opener_factory([(200, {"id": 1, "reactions": {"❤": 3}})])
    http.set_opener_factory(factory)

    rc = run(
        [
            "reaction",
            "list",
            "--publication",
            "example.substack.com",
            "--post",
            "hello-world",
            "--json",
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == [{"reaction": "❤", "count": 3}]


def test_reaction_list_unknown_post_exits_one(capsys: pytest.CaptureFixture[str]) -> None:
    # get_json's backoff retries on any HTTP error, 404 included, so all
    # four attempts must be queued for the retries to exhaust.
    factory, opener = make_opener_factory([(404, {"error": "not found"})] * 4)
    http.set_opener_factory(factory)

    rc = run(
        [
            "reaction",
            "list",
            "--publication",
            "example.substack.com",
            "--post",
            "nope",
            "--json",
        ]
    )

    assert rc == 1
    assert len(opener.requests) == 1  # 4xx fails fast, no retry
    err = json.loads(capsys.readouterr().err)
    assert err["code"] == 1
    assert "nope" in err["message"]


def test_reaction_list_server_error_exits_two_not_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    factory, _opener = make_opener_factory([(500, {"error": "boom"})] * 4)
    http.set_opener_factory(factory)

    rc = run(
        [
            "reaction",
            "list",
            "--publication",
            "example.substack.com",
            "--post",
            "hello-world",
            "--json",
        ]
    )

    assert rc == 2


def test_reaction_list_bad_publication_host_exits_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = run(
        [
            "reaction",
            "list",
            "--publication",
            "not a host",
            "--post",
            "hello-world",
            "--json",
        ]
    )
    assert rc == 1
    err = json.loads(capsys.readouterr().err)
    assert err["code"] == 1


def test_reaction_list_text_mode_no_reactions(capsys: pytest.CaptureFixture[str]) -> None:
    factory, _opener = make_opener_factory([(200, {"id": 1, "reactions": {}})])
    http.set_opener_factory(factory)

    rc = run(["reaction", "list", "--publication", "example.substack.com", "--post", "hello-world"])

    assert rc == 0
    assert "no reactions" in capsys.readouterr().out


# --- add / remove: argument validation ---------------------------------------


def test_reaction_add_requires_post_or_comment() -> None:
    parser = _make_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["reaction", "add", "--publication", "example.substack.com"])
    assert exc.value.code == 1


def test_reaction_add_rejects_both_post_and_comment() -> None:
    parser = _make_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(
            [
                "reaction",
                "add",
                "--publication",
                "example.substack.com",
                "--post",
                "1",
                "--comment",
                "2",
            ]
        )
    assert exc.value.code == 1


def test_reaction_add_default_emoji_is_heart() -> None:
    parser = _make_parser()
    args = parser.parse_args(
        ["reaction", "add", "--publication", "example.substack.com", "--post", "1"]
    )
    assert args.emoji == "❤"


# --- add / remove: webglass adapter ------------------------------------------


def test_reaction_add_post_succeeds_and_reports_id_target_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-abc")
    _set_canned_response(monkeypatch, _http_result(status=200, body="{}"))

    rc = run(
        [
            "reaction",
            "add",
            "--publication",
            "example.substack.com",
            "--post",
            "42",
            "--json",
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "id": "42",
        "target": "post",
        "reaction": "❤",
        "url": "https://example.substack.com/p/42",
    }


def test_reaction_add_comment_uses_comment_target(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-abc")
    _set_canned_response(monkeypatch, _http_result(status=200, body="{}"))

    rc = run(
        [
            "reaction",
            "add",
            "--publication",
            "example.substack.com",
            "--comment",
            "99",
            "--json",
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["target"] == "comment"
    assert payload["id"] == "99"


def test_reaction_add_passes_method_url_and_emoji_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-abc")
    _set_canned_response(monkeypatch, _http_result(status=200, body="{}"))

    captured: dict[str, list[str]] = {}
    real_run = webglass.subprocess.run

    def _spy(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        captured["cmd"] = cmd
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(webglass.subprocess, "run", _spy)

    run(["reaction", "add", "--publication", "example.substack.com", "--post", "42", "--json"])

    cmd = captured["cmd"]
    assert "POST" in cmd
    assert "https://example.substack.com/api/v1/post/42/reaction" in cmd
    # json.dumps defaults to ensure_ascii=True, so the heart lands escaped.
    assert any("reaction" in part and "2764" in part for part in cmd if isinstance(part, str))


def test_reaction_add_custom_emoji(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-abc")
    _set_canned_response(monkeypatch, _http_result(status=200, body="{}"))

    rc = run(
        [
            "reaction",
            "add",
            "--publication",
            "example.substack.com",
            "--post",
            "42",
            "--emoji",
            "\U0001f525",
            "--json",
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["reaction"] == "\U0001f525"


def test_reaction_add_without_session_exits_two_and_never_runs_subprocess(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.delenv("SUBSTACK_WEBGLASS_SESSION", raising=False)

    def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("subprocess must not run when session is missing")

    monkeypatch.setattr(webglass.subprocess, "run", _boom)

    rc = run(["reaction", "add", "--publication", "example.substack.com", "--post", "42", "--json"])

    assert rc == 2
    err = json.loads(capsys.readouterr().err)
    assert err["code"] == 2


def test_reaction_add_maps_401_to_env_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-abc")
    _set_canned_response(
        monkeypatch, _http_result(status=401, body="Please sign in", lifecycle_state="failed")
    )

    rc = run(["reaction", "add", "--publication", "example.substack.com", "--post", "42", "--json"])

    assert rc == 2
    err = json.loads(capsys.readouterr().err)
    assert "log in again" in err["remediation"].lower()


def test_reaction_add_maps_404_to_user_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-abc")
    _set_canned_response(
        monkeypatch, _http_result(status=404, body="No such post.", lifecycle_state="failed")
    )

    rc = run(["reaction", "add", "--publication", "example.substack.com", "--post", "42", "--json"])

    assert rc == 1


def test_reaction_remove_post_succeeds_and_reports_id_target_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-abc")
    _set_canned_response(monkeypatch, _http_result(status=200, body="{}"))

    rc = run(
        [
            "reaction",
            "remove",
            "--publication",
            "example.substack.com",
            "--post",
            "42",
            "--json",
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "id": "42",
        "target": "post",
        "reaction": "❤",
        "url": "https://example.substack.com/p/42",
    }


def test_reaction_remove_comment_uses_comment_target(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-abc")
    _set_canned_response(monkeypatch, _http_result(status=200, body="{}"))

    rc = run(
        [
            "reaction",
            "remove",
            "--publication",
            "example.substack.com",
            "--comment",
            "7",
            "--json",
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["target"] == "comment"
    assert payload["id"] == "7"


def test_reaction_remove_passes_delete_method_and_no_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-abc")
    _set_canned_response(monkeypatch, _http_result(status=200, body="{}"))

    captured: dict[str, list[str]] = {}
    real_run = webglass.subprocess.run

    def _spy(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        captured["cmd"] = cmd
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(webglass.subprocess, "run", _spy)

    run(["reaction", "remove", "--publication", "example.substack.com", "--post", "42", "--json"])

    cmd = captured["cmd"]
    assert "DELETE" in cmd
    assert "https://example.substack.com/api/v1/post/42/reaction" in cmd
    assert "--json-body" not in cmd


def test_reaction_remove_without_session_exits_two_and_never_runs_subprocess(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.delenv("SUBSTACK_WEBGLASS_SESSION", raising=False)

    def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("subprocess must not run when session is missing")

    monkeypatch.setattr(webglass.subprocess, "run", _boom)

    rc = run(
        [
            "reaction",
            "remove",
            "--publication",
            "example.substack.com",
            "--post",
            "42",
            "--json",
        ]
    )

    assert rc == 2
    err = json.loads(capsys.readouterr().err)
    assert err["code"] == 2


def test_reaction_add_bad_publication_host_exits_one_before_subprocess(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-abc")

    def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("subprocess must not run for an invalid publication host")

    monkeypatch.setattr(webglass.subprocess, "run", _boom)

    rc = run(["reaction", "add", "--publication", "not a host", "--post", "42", "--json"])

    assert rc == 1
    err = json.loads(capsys.readouterr().err)
    assert err["code"] == 1
