"""Tests for the webglass subprocess adapter (substack_cli.substack.webglass).

These tests NEVER invoke the real webglass binary. They inject a fake
`webglass` executable (tests/fakes/webglass/webglass) onto PATH that echoes a
canned WebOperationResult JSON payload, so the adapter's parsing and
failure-mapping logic can be exercised deterministically and offline.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from substack_cli.cli._errors import EXIT_ENV_ERROR, EXIT_USER_ERROR, CliError
from substack_cli.substack import webglass

FAKES_DIR = Path(__file__).parent / "fakes" / "webglass"


def _prepend_fake_webglass_to_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", f"{FAKES_DIR}{os.pathsep}{os.environ.get('PATH', '')}")


def _set_canned_response(monkeypatch: pytest.MonkeyPatch, payload: dict) -> None:
    monkeypatch.setenv("WEBGLASS_FAKE_RESPONSE", json.dumps(payload))


def _succeeded_result(**content_trusted: object) -> dict:
    return {
        "schema_version": 1,
        "operation_id": "operation-test",
        "kind": "test.op",
        "lifecycle_state": "succeeded",
        "content": {"trusted": content_trusted, "untrusted": {}, "sensitive": {}, "derived": {}},
        "error": None,
    }


def _http_result(*, status: int, body: str, lifecycle_state: str = "failed") -> dict:
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


# --- session_required -------------------------------------------------------


def test_session_required_raises_env_error_when_no_webglass_on_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "/nonexistent-empty-dir")
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-abc")
    with pytest.raises(CliError) as exc:
        webglass.session_required()
    assert exc.value.code == EXIT_ENV_ERROR
    assert "webglass-cli" in exc.value.remediation
    assert "SUBSTACK_WEBGLASS_SESSION" in exc.value.remediation or "webglass" in exc.value.message


def test_session_required_raises_env_error_when_no_session_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.delenv("SUBSTACK_WEBGLASS_SESSION", raising=False)
    with pytest.raises(CliError) as exc:
        webglass.session_required()
    assert exc.value.code == EXIT_ENV_ERROR
    assert "webglass-cli" in exc.value.remediation
    assert "SUBSTACK_WEBGLASS_SESSION" in exc.value.remediation


def test_session_required_does_not_run_subprocess_before_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No webglass on PATH and no session set: fail before any subprocess call."""
    monkeypatch.setenv("PATH", "/nonexistent-empty-dir")
    monkeypatch.delenv("SUBSTACK_WEBGLASS_SESSION", raising=False)

    called = {"ran": False}

    def _boom(*args: object, **kwargs: object) -> None:
        called["ran"] = True
        raise AssertionError("subprocess must not run before session_required checks")

    monkeypatch.setattr(webglass.subprocess, "run", _boom)
    with pytest.raises(CliError) as exc:
        webglass.session_required()
    assert called["ran"] is False
    assert exc.value.code == EXIT_ENV_ERROR


def test_session_required_returns_session_value_when_healthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-xyz")
    assert webglass.session_required() == "session-xyz"


# --- run_webglass ------------------------------------------------------------


def test_run_webglass_parses_json_result(monkeypatch: pytest.MonkeyPatch) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    _set_canned_response(monkeypatch, _succeeded_result(hello="world"))
    result = webglass.run_webglass(["session", "overview"])
    assert result["lifecycle_state"] == "succeeded"
    assert result["content"]["trusted"]["hello"] == "world"


def test_run_webglass_passes_json_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    _set_canned_response(monkeypatch, _succeeded_result())

    captured: dict[str, list[str]] = {}
    real_run = webglass.subprocess.run

    def _spy(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        captured["cmd"] = cmd
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(webglass.subprocess, "run", _spy)
    webglass.run_webglass(["session", "overview"])
    assert captured["cmd"][0] == "webglass"
    assert "--json" in captured["cmd"]


def test_run_webglass_raises_env_error_when_binary_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "/nonexistent-empty-dir")
    with pytest.raises(CliError) as exc:
        webglass.run_webglass(["session", "overview"])
    assert exc.value.code == EXIT_ENV_ERROR
    assert "webglass-cli" in exc.value.remediation or "webglass-cli" in exc.value.message


def test_run_webglass_raises_env_error_on_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("WEBGLASS_FAKE_RESPONSE", "not-json-at-all")
    with pytest.raises(CliError) as exc:
        webglass.run_webglass(["session", "overview"])
    assert exc.value.code == EXIT_ENV_ERROR


# --- map_failure --------------------------------------------------------------


def test_map_failure_no_raise_on_success() -> None:
    result = _succeeded_result(hello="world")
    webglass.map_failure(result)  # should not raise


def test_map_failure_maps_401_please_sign_in_to_env_error_with_login_hint() -> None:
    result = _http_result(status=401, body="Please sign in to continue.")
    with pytest.raises(CliError) as exc:
        webglass.map_failure(result)
    assert exc.value.code == EXIT_ENV_ERROR
    assert "log in again" in exc.value.remediation.lower()


def test_map_failure_maps_404_to_user_error() -> None:
    result = _http_result(status=404, body="No such post.")
    with pytest.raises(CliError) as exc:
        webglass.map_failure(result)
    assert exc.value.code == EXIT_USER_ERROR


def test_map_failure_maps_generic_backend_error_to_env_error() -> None:
    result = {
        "schema_version": 1,
        "operation_id": "operation-test",
        "kind": "page.open",
        "lifecycle_state": "failed",
        "content": {"trusted": {}, "untrusted": {}, "sensitive": {}, "derived": {}},
        "error": {
            "code": "backend_unavailable",
            "message": "this operation needs a browser backend, and none was injected",
            "remediation": "construct WebGlassService(browser=...)",
        },
    }
    with pytest.raises(CliError) as exc:
        webglass.map_failure(result)
    assert exc.value.code == EXIT_ENV_ERROR
    assert "backend_unavailable" in exc.value.message or "browser backend" in exc.value.message


def test_map_failure_maps_denied_lifecycle_without_error_to_env_error() -> None:
    result = {
        "schema_version": 1,
        "operation_id": "operation-test",
        "kind": "page.open",
        "lifecycle_state": "denied",
        "content": {"trusted": {}, "untrusted": {}, "sensitive": {}, "derived": {}},
        "error": None,
    }
    with pytest.raises(CliError) as exc:
        webglass.map_failure(result)
    assert exc.value.code == EXIT_ENV_ERROR


# --- request ------------------------------------------------------------------


def test_request_returns_parsed_content_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-abc")
    _set_canned_response(
        monkeypatch, _http_result(status=200, body="ok", lifecycle_state="succeeded")
    )
    result = webglass.request("GET", "https://substack.example/api/posts/1")
    assert result["content"]["trusted"]["response"]["status"] == 200


def test_request_raises_before_subprocess_when_session_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.delenv("SUBSTACK_WEBGLASS_SESSION", raising=False)

    def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("subprocess must not run when session is missing")

    monkeypatch.setattr(webglass.subprocess, "run", _boom)
    with pytest.raises(CliError) as exc:
        webglass.request("GET", "https://substack.example/api/posts/1")
    assert exc.value.code == EXIT_ENV_ERROR


def test_request_maps_401_to_env_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-abc")
    _set_canned_response(monkeypatch, _http_result(status=401, body="Please sign in"))
    with pytest.raises(CliError) as exc:
        webglass.request("GET", "https://substack.example/api/posts/1")
    assert exc.value.code == EXIT_ENV_ERROR
    assert "log in again" in exc.value.remediation.lower()


def test_request_maps_404_to_user_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-abc")
    _set_canned_response(monkeypatch, _http_result(status=404, body="No such post."))
    with pytest.raises(CliError) as exc:
        webglass.request("GET", "https://substack.example/api/posts/does-not-exist")
    assert exc.value.code == EXIT_USER_ERROR


def test_request_passes_method_url_and_json_body(monkeypatch: pytest.MonkeyPatch) -> None:
    _prepend_fake_webglass_to_path(monkeypatch)
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "session-abc")
    _set_canned_response(
        monkeypatch, _http_result(status=200, body="{}", lifecycle_state="succeeded")
    )

    captured: dict[str, list[str]] = {}
    real_run = webglass.subprocess.run

    def _spy(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        captured["cmd"] = cmd
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(webglass.subprocess, "run", _spy)
    webglass.request("POST", "https://substack.example/api/posts", json_body={"title": "hi"})
    cmd = captured["cmd"]
    assert "POST" in cmd
    assert "https://substack.example/api/posts" in cmd
    assert any("hi" in part for part in cmd if isinstance(part, str))


def test_webglass_module_does_not_import_playwright() -> None:
    assert "playwright" not in sys.modules
    src = (Path(webglass.__file__)).read_text(encoding="utf-8")
    assert "import playwright" not in src.lower()
