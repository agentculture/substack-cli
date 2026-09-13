"""In-memory fake urllib opener for substack_cli.substack.http tests.

Nothing here touches the network. A :class:`FakeOpener` is queued with a
sequence of ``(status, payload)`` results and returned in order for every
``.open()`` call, recording each request it sees so tests can assert on
method/url/headers without a real socket.
"""

from __future__ import annotations

import io
import json as _json
import urllib.error
from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass
class FakeHTTPResponse:
    """Minimal stand-in for the object returned by ``OpenerDirector.open``."""

    status: int
    body: bytes

    def read(self) -> bytes:
        return self.body

    def getcode(self) -> int:
        return self.status

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False


@dataclass
class RecordedRequest:
    """One request as the fake opener saw it."""

    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    timeout: Any = None


class FakeOpener:
    """Fake ``OpenerDirector``: replays queued ``(status, payload)`` results.

    A status >= 400 raises :class:`urllib.error.HTTPError`, matching the
    real ``urllib`` opener's behaviour, so production error-handling code
    is exercised unchanged. A queued payload that *is* an exception
    instance is raised instead of returned, so transport-level failures (a
    socket timeout, a bare ``URLError``) can be replayed too.
    """

    def __init__(self, responses: Iterable[tuple[int, Any]]) -> None:
        self._responses: list[tuple[int, Any]] = list(responses)
        self.requests: list[RecordedRequest] = []

    def open(self, req: Any, timeout: float | None = None) -> FakeHTTPResponse:
        headers = {key: value for key, value in req.header_items()}
        self.requests.append(
            RecordedRequest(
                method=req.get_method(), url=req.full_url, headers=headers, timeout=timeout
            )
        )
        if not self._responses:
            raise AssertionError("FakeOpener: no more queued responses")
        status, payload = self._responses.pop(0)
        if isinstance(payload, BaseException):
            raise payload
        body = payload if isinstance(payload, bytes) else _json.dumps(payload).encode("utf-8")
        if status >= 400:
            raise urllib.error.HTTPError(
                req.full_url, status, "fake-http-error", {}, io.BytesIO(body)
            )
        return FakeHTTPResponse(status=status, body=body)


def make_opener_factory(responses: Iterable[tuple[int, Any]]) -> tuple[Any, FakeOpener]:
    """Build a zero-arg opener factory backed by one :class:`FakeOpener`.

    Returns ``(factory, opener)`` — pass ``factory`` to
    ``substack_cli.substack.http.set_opener_factory`` and inspect
    ``opener.requests`` afterwards.
    """

    opener = FakeOpener(responses)

    def factory() -> FakeOpener:
        return opener

    return factory, opener
