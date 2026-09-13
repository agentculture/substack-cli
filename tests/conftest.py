"""Repo-wide pytest fixtures.

The suite must never touch the real network: `substack_cli.substack.http`
tests use `tests/fakes/http.py` (an in-memory `urllib` opener) and the
webglass tests use a fake subprocess, so no test has a legitimate reason to
open a socket. This fixture makes any accidental network access a hard
failure instead of a silent hang or a flaky pass against a real endpoint.

Only socket *connection* is blocked. Subprocess spawning (the fake webglass
adapter tests) is unaffected — it doesn't go through `socket.socket.connect`
or `socket.create_connection`.
"""

from __future__ import annotations

import socket
from typing import Any

import pytest


def _blocked_connect(*_args: Any, **_kwargs: Any) -> None:
    raise RuntimeError("network access is disabled in the test suite")


def _blocked_create_connection(*_args: Any, **_kwargs: Any) -> None:
    raise RuntimeError("network access is disabled in the test suite")


@pytest.fixture(autouse=True)
def _block_network_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any test that opens a real network socket.

    Patched per-test via `monkeypatch` (not at import/session scope), so it
    is safe under `pytest-xdist`: each worker process patches its own
    `socket` module state independently and pytest's `monkeypatch` fixture
    reverts the patch after every test, with no shared state across workers
    or tests to race on.
    """
    monkeypatch.setattr(socket.socket, "connect", _blocked_connect)
    monkeypatch.setattr(socket, "create_connection", _blocked_create_connection)
