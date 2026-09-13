"""Stdlib-only HTTP transport for the Substack API surface.

Two API bases:

* **publication base** -- ``https://<host>/api/v1``, where ``host`` is the
  target publication's domain (custom domain or ``<name>.substack.com``).
* **account base** -- ``https://substack.com/api/v1``, fixed: account-level
  endpoints (the calling user's own account) are not per-publication.

Both are templates of the form ``https://{host}/api/v1``; the publication
base fills ``{host}`` with the validated publication host, the account base
always fills it with :data:`ACCOUNT_HOST`. The template itself is
overridable via the ``SUBSTACK_API_BASE`` environment variable, so tests and
a future local/staging setup can point the client at ``http://127.0.0.1:...``
without any code change.

GET requests get serial backoff on failure: up to 3 retries, sleeping
0.5s / 1s / 2s between attempts (:data:`_RETRY_DELAYS`), for up to 4 requests
total. Writes (anything that is not a GET) never retry -- a single failure
raises :class:`~substack_cli.cli._errors.CliError` immediately, since
replaying a non-idempotent write on a flaky response is unsafe.

The urllib opener is never constructed directly by request code -- it is
always obtained through the module-level :func:`_opener_factory`, which
tests overwrite via :func:`set_opener_factory` so nothing here ever touches
the network in the test suite.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Optional

from substack_cli.cli._errors import CliError

#: Account-level endpoints always resolve against this host.
ACCOUNT_HOST = "substack.com"

#: Template for the publication API base. ``{host}`` is filled per call.
#: Overridable wholesale via the ``SUBSTACK_API_BASE`` environment variable.
PUBLIC_BASE = "https://{host}/api/v1"

# A conservative bare-hostname check (labels of letters/digits/hyphens,
# at least one dot, no scheme, no path, no whitespace). Good enough to
# reject obviously-wrong input like "not a host" without pretending to be
# a full RFC 1035 validator.
_HOST_RE = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))+$")

#: Seconds to sleep before each GET retry (3 retries -> up to 4 attempts).
_RETRY_DELAYS: tuple[float, ...] = (0.5, 1, 2)

_opener_factory: Callable[[], "urllib.request.OpenerDirector"] = urllib.request.build_opener
_sleep: Callable[[float], None] = time.sleep


def set_opener_factory(factory: Callable[[], "urllib.request.OpenerDirector"]) -> None:
    """Inject the zero-arg factory used to obtain the opener for every request.

    Tests use this to hand back a fake opener so no request ever reaches
    the network.
    """
    global _opener_factory
    _opener_factory = factory


def reset_opener_factory() -> None:
    """Restore the default stdlib opener factory."""
    global _opener_factory
    _opener_factory = urllib.request.build_opener


def set_sleep(fn: Callable[[float], None]) -> None:
    """Inject the function used to sleep between GET backoff attempts.

    Tests use this to run the retry loop instantly and record the delays
    that would have happened.
    """
    global _sleep
    _sleep = fn


def reset_sleep() -> None:
    """Restore the default ``time.sleep`` backoff sleep."""
    global _sleep
    _sleep = time.sleep


def _api_base_template() -> str:
    return os.environ.get("SUBSTACK_API_BASE", PUBLIC_BASE)


def account_base() -> str:
    """The account API base URL (fixed host, overridable via env var)."""
    return _api_base_template().format(host=ACCOUNT_HOST)


def publication_host(host: str) -> str:
    """Validate `host` as a bare hostname; return it unchanged if valid.

    Raises ``CliError(1)`` for anything that is not a plausible bare
    hostname (contains whitespace, a scheme, a path, or is empty).
    """
    if not isinstance(host, str) or not host or not _HOST_RE.match(host):
        raise CliError(
            code=1,
            message=f"invalid publication host: {host!r}",
            remediation="pass a bare hostname, e.g. example.substack.com",
        )
    return host


def _publication_base(host: str) -> str:
    return _api_base_template().format(host=publication_host(host))


def publication_base(host: str) -> str:
    """Public wrapper around :func:`_publication_base`.

    Callers that build a full URL for a non-``get_json``/``request_json``
    transport (e.g. :mod:`substack_cli.substack.webglass`'s authenticated
    ``request()``) need the same validated ``https://<host>/api/v1`` base
    this module already computes for its own GET/write helpers, without
    reaching into the private ``_publication_base``. Raises ``CliError(1)``
    for an invalid `host`, exactly like `_publication_base`.
    """
    return _publication_base(host)


def _join(base: str, path: str) -> str:
    return base.rstrip("/") + "/" + path.lstrip("/")


def _build_request(url: str, method: str, data: Optional[dict[str, Any]]) -> urllib.request.Request:
    headers = {"Accept": "application/json"}
    body: Optional[bytes] = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    return urllib.request.Request(url, data=body, headers=headers, method=method)


def _send_once(url: str, method: str, data: Optional[dict[str, Any]]) -> dict[str, Any]:
    opener = _opener_factory()
    request = _build_request(url, method, data)
    try:
        with opener.open(request) as response:
            payload = response.read()
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise CliError(
            code=2,
            message=f"{method} {url} failed: {exc}",
            remediation="check network connectivity, credentials, and SUBSTACK_API_BASE",
        ) from exc
    return json.loads(payload.decode("utf-8")) if payload else {}


def _get_with_backoff(url: str) -> dict[str, Any]:
    opener = _opener_factory()
    last_exc: Optional[Exception] = None
    delays = iter(_RETRY_DELAYS)
    attempts = 0
    while True:
        attempts += 1
        request = _build_request(url, "GET", None)
        try:
            with opener.open(request) as response:
                payload = response.read()
            return json.loads(payload.decode("utf-8")) if payload else {}
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            last_exc = exc
            try:
                delay = next(delays)
            except StopIteration:
                break
            _sleep(delay)
    raise CliError(
        code=2,
        message=f"GET {url} failed after {attempts} attempts: {last_exc}",
        remediation="check network connectivity and SUBSTACK_API_BASE",
    )


def get_json(host: str, path: str) -> dict[str, Any]:
    """GET `path` from the publication API for `host`.

    Retries on failure per the module backoff policy (3 retries, up to 4
    requests total). Raises ``CliError(1)`` for a malformed `host`, or
    ``CliError(2)`` once backoff is exhausted.
    """
    return _get_with_backoff(_join(_publication_base(host), path))


def get_account_json(path: str) -> dict[str, Any]:
    """GET `path` from the fixed account API base, with the same backoff as `get_json`."""
    return _get_with_backoff(_join(account_base(), path))


def request_json(
    host: str,
    path: str,
    method: str = "POST",
    data: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Send a single write request to the publication API for `host`.

    `method` must not be "GET" -- use :func:`get_json` for reads. Writes
    never retry: one failure raises ``CliError(2)`` immediately, since
    replaying a non-idempotent write against an unknown server state is
    unsafe.
    """
    if method.upper() == "GET":
        raise CliError(
            code=1,
            message="request_json is for writes; use get_json for GET requests",
            remediation="call get_json(host, path) instead",
        )
    return _send_once(_join(_publication_base(host), path), method.upper(), data)


def account_request_json(
    path: str,
    method: str = "POST",
    data: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Send a single write request to the fixed account API base.

    Same "GET is rejected, writes never retry" contract as `request_json`.
    """
    if method.upper() == "GET":
        raise CliError(
            code=1,
            message="account_request_json is for writes; use get_account_json for GET requests",
            remediation="call get_account_json(path) instead",
        )
    return _send_once(_join(account_base(), path), method.upper(), data)
