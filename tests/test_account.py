"""Tests for the ``account`` noun (whoami auth probe, overview).

t11 wires ``account`` into the real top-level parser
(``substack_cli.cli._build_parser``); until then this module builds its own
tiny parser via the same ``_CliArgumentParser`` + ``register(sub)`` pattern
``_build_parser`` uses, so the error contract (``error:``/``hint:``, --json
mirroring) is exercised identically to how the real CLI will dispatch once
wired in.

Every case drives the three webglass auth states through the fake `webglass`
executable (tests/fakes/webglass/webglass) — never the network:

* no ``$SUBSTACK_WEBGLASS_SESSION`` -> "no session named" (env error, code 2)
* a session is set but the publication endpoint answers 401 -> "session
  present but dead" (env error, code 2)
* a session is set and the endpoint answers 200 -> authenticated (code 0)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from substack_cli.cli import _argv_has_json, _CliArgumentParser, _dispatch
from substack_cli.cli._commands import account
from substack_cli.cli._errors import EXIT_ENV_ERROR, EXIT_SUCCESS, EXIT_USER_ERROR

FAKES_DIR = Path(__file__).parent / "fakes" / "webglass"


def _build_test_parser() -> _CliArgumentParser:
    """Mimic ``substack_cli.cli._build_parser`` for the ``account`` noun alone."""
    parser = _CliArgumentParser(prog="substack-cli")
    sub = parser.add_subparsers(dest="command", parser_class=_CliArgumentParser)
    account.register(sub)
    return parser


def run(argv: list[str]) -> int:
    """Mimic ``substack_cli.cli.main`` for the local ``account``-only parser."""
    _CliArgumentParser._json_hint = _argv_has_json(argv)
    parser = _build_test_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    return _dispatch(args)


def _prepend_fake_webglass_to_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", f"{FAKES_DIR}{os.pathsep}{os.environ.get('PATH', '')}")


def _no_webglass_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "/nonexistent-empty-dir")


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


def _set_canned_response(monkeypatch: pytest.MonkeyPatch, payload: dict) -> None:
    monkeypatch.setenv("WEBGLASS_FAKE_RESPONSE", json.dumps(payload))


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUBSTACK_WEBGLASS_SESSION", raising=False)
    monkeypatch.delenv("WEBGLASS_FAKE_RESPONSE", raising=False)
    monkeypatch.delenv("SUBSTACK_API_BASE", raising=False)


# --- registration / argparse error contract --------------------------------


def test_account_registers_whoami_and_overview() -> None:
    parser = _build_test_parser()
    # argparse exposes the registered subparser names via the action choices.
    group_actions = parser._subparsers._group_actions  # type: ignore[union-attr]
    account_action = next(a for a in group_actions if a.dest == "command")
    account_parser = account_action.choices["account"]
    noun_action = next(
        a
        for a in account_parser._subparsers._group_actions  # type: ignore[union-attr]
        if a.dest == "account_command"
    )
    assert set(noun_action.choices) == {"whoami", "overview"}


def test_account_whoami_bogus_flag_exits_1_text(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(SystemExit) as exc:
        run(["account", "whoami", "--bogus"])
    assert exc.value.code == EXIT_USER_ERROR
    err = capsys.readouterr().err
    assert err.startswith("error:")
    assert "hint:" in err


def test_account_whoami_bogus_flag_exits_1_json(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(SystemExit) as exc:
        run(["account", "whoami", "--bogus", "--json"])
    assert exc.value.code == EXIT_USER_ERROR
    payload = json.loads(capsys.readouterr().err)
    assert payload["code"] == EXIT_USER_ERROR
    assert payload["message"]
    assert payload["remediation"]


def test_account_whoami_missing_publication_exits_1(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc:
        run(["account", "whoami"])
    assert exc.value.code == EXIT_USER_ERROR
    err = capsys.readouterr().err
    assert err.startswith("error:")
    assert "hint:" in err


# --- whoami: three auth states, all through the fake webglass executable ---


def test_account_whoami_no_session_named_is_env_error(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.delenv("SUBSTACK_WEBGLASS_SESSION", raising=False)

    rc = run(["account", "whoami", "--publication", "example.substack.com"])
    assert rc == EXIT_ENV_ERROR
    err = capsys.readouterr().err
    assert err.startswith("error:")
    assert "hint:" in err
    assert "SUBSTACK_WEBGLASS_SESSION" in err


def test_account_whoami_session_present_but_401_is_env_error(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-abc")
    _set_canned_response(
        monkeypatch,
        _http_result(
            status=401,
            body=json.dumps({"errors": [{"msg": "Please sign in", "code": "unauthorized"}]}),
            lifecycle_state="failed",
        ),
    )

    rc = run(["account", "whoami", "--publication", "example.substack.com"])
    assert rc == EXIT_ENV_ERROR
    err = capsys.readouterr().err
    assert err.startswith("error:")
    assert "hint:" in err
    assert "log in again" in err.lower()


def test_account_whoami_authenticated_reports_publication_json(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-abc")
    publication = {
        "id": 4242,
        "subdomain": "example",
        "name": "Example Publication",
        "custom_domain": None,
    }
    _set_canned_response(
        monkeypatch,
        _http_result(status=200, body=json.dumps(publication)),
    )

    rc = run(["account", "whoami", "--publication", "example.substack.com", "--json"])
    assert rc == EXIT_SUCCESS
    payload = json.loads(capsys.readouterr().out)
    assert payload["publication"] == publication
    assert "user_id" in payload


def test_account_whoami_authenticated_reports_publication_text(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-abc")
    publication = {
        "id": 4242,
        "subdomain": "example",
        "name": "Example Publication",
        "custom_domain": "example.com",
    }
    _set_canned_response(
        monkeypatch,
        _http_result(status=200, body=json.dumps(publication)),
    )

    rc = run(["account", "whoami", "--publication", "example.substack.com"])
    assert rc == EXIT_SUCCESS
    out = capsys.readouterr().out
    assert "example" in out
    assert "Example Publication" in out
    assert "example.com" in out


def test_account_whoami_invalid_publication_host_is_user_error(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-abc")

    rc = run(["account", "whoami", "--publication", "not a host"])
    assert rc == EXIT_USER_ERROR
    err = capsys.readouterr().err
    assert err.startswith("error:")
    assert "hint:" in err


def test_account_whoami_malformed_publication_body_is_env_error(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-abc")
    _set_canned_response(monkeypatch, _http_result(status=200, body="not-json-at-all"))

    rc = run(["account", "whoami", "--publication", "example.substack.com"])
    assert rc == EXIT_ENV_ERROR
    err = capsys.readouterr().err
    assert err.startswith("error:")
    assert "hint:" in err


# --- overview: reports webglass presence + version, exits 0 either way -----


def test_account_overview_exits_0_with_webglass_on_path(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)

    rc = run(["account", "overview", "--json"])
    assert rc == EXIT_SUCCESS
    payload = json.loads(capsys.readouterr().out)
    assert payload["webglass_on_path"] is True
    assert payload["webglass_version"]


def test_account_overview_exits_0_without_webglass_on_path(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_webglass_on_path(monkeypatch)

    rc = run(["account", "overview", "--json"])
    assert rc == EXIT_SUCCESS
    payload = json.loads(capsys.readouterr().out)
    assert payload["webglass_on_path"] is False
    assert payload["webglass_version"] is None


def test_account_overview_text_mode(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_webglass_on_path(monkeypatch)

    rc = run(["account", "overview"])
    assert rc == EXIT_SUCCESS
    out = capsys.readouterr().out
    assert "webglass" in out.lower()


def test_account_bare_defaults_to_overview(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_webglass_on_path(monkeypatch)

    rc = run(["account"])
    assert rc == EXIT_SUCCESS
    assert capsys.readouterr().out.strip()
