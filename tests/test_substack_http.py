"""Tests for the stdlib-only HTTP transport in substack_cli.substack.http.

No test in this module touches the network: every case injects a fake
opener via ``http.set_opener_factory`` (and a fake sleep via
``http.set_sleep``) before exercising the module, and restores the
defaults afterwards.
"""

from __future__ import annotations

import subprocess

import pytest

from substack_cli.cli._errors import CliError
from substack_cli.substack import http
from tests.fakes.http import make_opener_factory


@pytest.fixture(autouse=True)
def _reset_http_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test gets an instant, deterministic sleep and a clean env/opener."""
    monkeypatch.delenv("SUBSTACK_API_BASE", raising=False)
    sleeps: list[float] = []
    http.set_sleep(sleeps.append)
    yield
    http.reset_sleep()
    http.reset_opener_factory()


# --- bases -----------------------------------------------------------------


def test_public_base_is_per_host_template() -> None:
    assert http.PUBLIC_BASE == "https://{host}/api/v1"
    assert http.PUBLIC_BASE.format(host="example.substack.com") == (
        "https://example.substack.com/api/v1"
    )


def test_account_base_is_fixed_to_substack_com() -> None:
    assert http.account_base() == "https://substack.com/api/v1"


def test_api_base_overridable_by_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUBSTACK_API_BASE", "http://127.0.0.1:9999/{host}/v9")
    factory, opener = make_opener_factory([(200, {"ok": True})])
    http.set_opener_factory(factory)

    http.get_json("example.substack.com", "ping")

    assert opener.requests[0].url == "http://127.0.0.1:9999/example.substack.com/v9/ping"


def test_no_tracked_json_file_contains_substack_com() -> None:
    """No tracked *config/fixture* JSON hardcodes the account host.

    ``.devague/`` frame/plan artifacts are prose specs that legitimately
    *discuss* substack.com (e.g. this very task); they are not runtime
    config or test fixtures the HTTP transport reads, so they are excluded
    the same way ``scripts/scan-secrets.py`` scopes its endpoint check to
    structured config rather than every JSON file in the repo.
    """
    tracked = subprocess.run(
        ["git", "ls-files", "*.json"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    offenders = []
    for path in tracked:
        if not path or path.startswith(".devague/"):
            continue
        with open(path, encoding="utf-8") as handle:
            if "substack.com" in handle.read():
                offenders.append(path)
    assert offenders == []


# --- host validation ---------------------------------------------------------


def test_publication_host_accepts_valid_hostname() -> None:
    assert http.publication_host("example.substack.com") == "example.substack.com"


def test_publication_host_rejects_not_a_host() -> None:
    with pytest.raises(CliError) as exc_info:
        http.publication_host("not a host")
    assert exc_info.value.code == 1


def test_publication_host_rejects_empty_string() -> None:
    with pytest.raises(CliError) as exc_info:
        http.publication_host("")
    assert exc_info.value.code == 1


# --- GET backoff -------------------------------------------------------------


def test_get_json_retries_429_then_succeeds() -> None:
    factory, opener = make_opener_factory(
        [(429, {"error": "rate limited"}), (200, {"hello": "world"})]
    )
    http.set_opener_factory(factory)

    result = http.get_json("example.substack.com", "posts")

    assert result == {"hello": "world"}
    assert len(opener.requests) == 2
    assert all(r.method == "GET" for r in opener.requests)


def test_get_json_exhausts_backoff_and_raises_cli_error() -> None:
    factory, opener = make_opener_factory(
        [
            (500, {"error": "e1"}),
            (500, {"error": "e2"}),
            (500, {"error": "e3"}),
            (500, {"error": "e4"}),
        ]
    )
    http.set_opener_factory(factory)

    with pytest.raises(CliError) as exc_info:
        http.get_json("example.substack.com", "posts")

    assert exc_info.value.code == 2
    assert len(opener.requests) == 4


def test_get_json_requests_carry_no_cookie_header() -> None:
    factory, opener = make_opener_factory([(200, {"ok": True})])
    http.set_opener_factory(factory)

    http.get_json("example.substack.com", "posts")

    assert "Cookie" not in opener.requests[0].headers
    assert "cookie" not in {k.lower() for k in opener.requests[0].headers}


def test_get_json_backoff_sleeps_are_injectable_and_growing() -> None:
    sleeps: list[float] = []
    http.set_sleep(sleeps.append)
    factory, opener = make_opener_factory([(500, {}), (500, {}), (200, {"ok": True})])
    http.set_opener_factory(factory)

    http.get_json("example.substack.com", "posts")

    assert len(opener.requests) == 3
    assert sleeps == [0.5, 1]


# --- writes: single attempt, no retry ---------------------------------------


def test_write_500_yields_exactly_one_request_and_cli_error() -> None:
    factory, opener = make_opener_factory([(500, {"error": "boom"})])
    http.set_opener_factory(factory)

    with pytest.raises(CliError) as exc_info:
        http.request_json("example.substack.com", "posts", method="POST", data={"title": "hi"})

    assert exc_info.value.code == 2
    assert len(opener.requests) == 1
    assert opener.requests[0].method == "POST"


def test_write_success_returns_payload_single_request() -> None:
    factory, opener = make_opener_factory([(200, {"id": 1})])
    http.set_opener_factory(factory)

    result = http.request_json("example.substack.com", "posts", method="POST", data={"title": "hi"})

    assert result == {"id": 1}
    assert len(opener.requests) == 1


def test_request_json_rejects_get_method() -> None:
    with pytest.raises(CliError) as exc_info:
        http.request_json("example.substack.com", "posts", method="GET")
    assert exc_info.value.code == 1


def test_account_get_json_uses_account_host() -> None:
    factory, opener = make_opener_factory([(200, {"ok": True})])
    http.set_opener_factory(factory)

    result = http.get_account_json("subscriptions")

    assert result == {"ok": True}
    assert opener.requests[0].url == "https://substack.com/api/v1/subscriptions"


def test_account_request_json_write_no_retry() -> None:
    factory, opener = make_opener_factory([(500, {})])
    http.set_opener_factory(factory)

    with pytest.raises(CliError) as exc_info:
        http.account_request_json("subscriptions", method="DELETE")

    assert exc_info.value.code == 2
    assert len(opener.requests) == 1


def test_requests_carry_a_descriptive_user_agent() -> None:
    """Substack 403s urllib's default agent; we send substack-cli/<version>."""
    factory, opener = make_opener_factory([(200, [])])
    http.set_opener_factory(factory)

    http.get_json("example.substack.com", "archive")

    ua = opener.requests[0].headers.get("User-agent")
    assert ua is not None and ua.startswith("substack-cli/")
    assert "Python-urllib" not in ua


def test_get_does_not_retry_a_403() -> None:
    """4xx other than 429 is a definitive answer: exactly one attempt, exit 2."""
    factory, opener = make_opener_factory([(403, "Forbidden")] * 4)
    http.set_opener_factory(factory)

    with pytest.raises(CliError) as excinfo:
        http.get_json("example.substack.com", "archive")

    assert excinfo.value.code == 2
    assert len(opener.requests) == 1
    assert "HTTP Error 403" in excinfo.value.message
