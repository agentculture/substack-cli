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

Every request carries a finite timeout (:data:`DEFAULT_HTTP_TIMEOUT`, 30s,
overridable in seconds via ``SUBSTACK_HTTP_TIMEOUT``; a non-numeric or
non-positive value is ``CliError(1)``). A timed-out GET is a retryable
transport failure like any other; a timed-out write raises ``CliError(2)``
immediately. A response body that is not valid UTF-8 JSON is never retried
either -- it raises ``CliError(2)`` naming the URL.

The urllib opener is never constructed directly by request code -- it is
always obtained through the module-level :func:`_opener_factory`, which
tests overwrite via :func:`set_opener_factory` so nothing here ever touches
the network in the test suite.
"""

from __future__ import annotations

import json
import math
import os
import re
import socket
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Optional

from substack_cli import __version__
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

#: Sent on every request. Substack answers 403 to urllib's default
#: ``Python-urllib/x.y`` agent but accepts a descriptive one (verified with curl
#: on 2026-09-13); we identify honestly rather than imitate a browser.
USER_AGENT = f"substack-cli/{__version__} (+https://github.com/agentculture/substack-cli)"

#: Seconds to sleep before each GET retry (3 retries -> up to 4 attempts).
_RETRY_DELAYS: tuple[float, ...] = (0.5, 1, 2)

#: Seconds any single request may take before it is abandoned. A request
#: without a timeout can hang forever (urllib's default is the global socket
#: timeout, normally ``None``), which for an agent-facing CLI means a command
#: that never returns and never reports an error.
DEFAULT_HTTP_TIMEOUT = 30.0

#: Environment variable overriding :data:`DEFAULT_HTTP_TIMEOUT` (seconds).
HTTP_TIMEOUT_ENV_VAR = "SUBSTACK_HTTP_TIMEOUT"

#: Transport-level timeouts that are not ``URLError`` subclasses.
#: ``socket.timeout`` is an alias of ``TimeoutError`` on Python 3.10+, but
#: both are named so the intent survives if that ever changes.
_TIMEOUT_EXCEPTIONS: tuple[type[BaseException], ...] = (socket.timeout, TimeoutError)

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


def publication_base(host: str) -> str:
    """The publication API base URL for `host` (validated, env-overridable).

    Public because the owner-side verbs need the same base URL without going
    through this module's urllib transport: their requests are made by the
    webglass adapter (the browser session holds the auth), so they build the
    URL here and hand it to `substack_cli.substack.webglass.request`.
    """
    return _api_base_template().format(host=publication_host(host))


def _publication_base(host: str) -> str:
    return publication_base(host)


def _join(base: str, path: str) -> str:
    return base.rstrip("/") + "/" + path.lstrip("/")


def request_timeout() -> float:
    """Seconds any single request may take, from the env var or the default.

    Raises ``CliError(1)`` for a value that is not a finite positive number:
    that is a misconfigured environment the caller can fix by correcting the
    variable, so it is a user error, not an environment failure.
    """
    raw = os.environ.get(HTTP_TIMEOUT_ENV_VAR)
    if raw is None or not raw.strip():
        return DEFAULT_HTTP_TIMEOUT
    remediation = (
        f"set ${HTTP_TIMEOUT_ENV_VAR} to a positive number of seconds "
        f"(e.g. {DEFAULT_HTTP_TIMEOUT:g}), or unset it to use the default"
    )
    try:
        value = float(raw)
    except ValueError as exc:
        raise CliError(
            code=1,
            message=f"${HTTP_TIMEOUT_ENV_VAR} is not a number: {raw!r}",
            remediation=remediation,
        ) from exc
    if not math.isfinite(value) or value <= 0:
        raise CliError(
            code=1,
            message=f"${HTTP_TIMEOUT_ENV_VAR} must be a finite positive number, got {raw!r}",
            remediation=remediation,
        )
    return value


def _decode(payload: bytes, method: str, url: str) -> dict[str, Any]:
    """Decode a response body as UTF-8 JSON, or raise ``CliError(2)``.

    A body that is not valid UTF-8 JSON (an HTML error/interstitial page, a
    truncated response) is never retried: replaying the same request will
    produce the same unusable payload, so it is reported once, naming the
    URL, as an environment error.
    """
    if not payload:
        return {}
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CliError(
            code=2,
            message=f"{method} {url} response was not valid JSON: {exc}",
            remediation="check SUBSTACK_API_BASE and whether the endpoint returned an "
            "HTML error page instead of JSON",
        ) from exc


def _timeout_error(method: str, url: str, exc: Exception) -> CliError:
    return CliError(
        code=2,
        message=f"{method} {url} timed out: {exc}",
        remediation=f"check network connectivity, or raise ${HTTP_TIMEOUT_ENV_VAR} "
        f"(seconds, default {DEFAULT_HTTP_TIMEOUT:g}) and retry",
    )


def _is_timeout(exc: Exception) -> bool:
    if isinstance(exc, _TIMEOUT_EXCEPTIONS):
        return True
    reason = getattr(exc, "reason", None)
    return isinstance(reason, _TIMEOUT_EXCEPTIONS)


def _build_request(url: str, method: str, data: Optional[dict[str, Any]]) -> urllib.request.Request:
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    body: Optional[bytes] = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    return urllib.request.Request(url, data=body, headers=headers, method=method)


def _send_once(url: str, method: str, data: Optional[dict[str, Any]]) -> dict[str, Any]:
    timeout = request_timeout()
    opener = _opener_factory()
    request = _build_request(url, method, data)
    try:
        with opener.open(request, timeout=timeout) as response:
            payload = response.read()
    except (urllib.error.URLError, *_TIMEOUT_EXCEPTIONS) as exc:
        if _is_timeout(exc):
            # A write never retries, and a timed-out write is no different:
            # the server may well have applied it, so one CliError(2) and out.
            raise _timeout_error(method, url, exc) from exc
        raise CliError(
            code=2,
            message=f"{method} {url} failed: {exc}",
            remediation="check network connectivity, credentials, and SUBSTACK_API_BASE",
        ) from exc
    return _decode(payload, method, url)


def _is_retryable(exc: Exception) -> bool:
    """Only 429, 5xx and transport-level failures are worth another GET.

    A 401/403/404 is a definitive answer from the server; retrying it three
    more times just delays the error the caller needs.
    """
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code == 429 or exc.code >= 500
    return True


def _get_with_backoff(url: str) -> dict[str, Any]:
    timeout = request_timeout()
    opener = _opener_factory()
    last_exc: Optional[Exception] = None
    delays = iter(_RETRY_DELAYS)
    attempts = 0
    while True:
        attempts += 1
        request = _build_request(url, "GET", None)
        try:
            with opener.open(request, timeout=timeout) as response:
                payload = response.read()
            # Decoding failures raise CliError(2) straight out of the loop:
            # a malformed payload is not a transport hiccup, so no retry.
            return _decode(payload, "GET", url)
        except (urllib.error.URLError, *_TIMEOUT_EXCEPTIONS) as exc:
            last_exc = exc
            if not _is_retryable(exc):
                break
            try:
                delay = next(delays)
            except StopIteration:
                break
            _sleep(delay)
    if last_exc is not None and _is_timeout(last_exc):
        raise _timeout_error("GET", url, last_exc)
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
