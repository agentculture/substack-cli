"""Subprocess adapter onto the sibling `webglass` CLI (webglass-cli).

substack-cli never talks to a browser directly (no headless-browser-automation
import anywhere under `substack_cli`, and `pyproject.toml`'s `dependencies`
stays `[]`): every guarded web operation is delegated to the `webglass` binary,
invoked as a subprocess with `--json`, whose stdout is a single
`WebOperationResult` JSON document — the same shape whether the operation
succeeded, was denied/blocked, or failed outright.

Exit-code mapping (see ``substack_cli.cli._errors``):

* no `webglass` on PATH, no `$SUBSTACK_WEBGLASS_SESSION`, a missing/garbled
  webglass process, or a webglass-reported backend/environment error ->
  ``CliError(EXIT_ENV_ERROR)``.
* an HTTP-shaped failure that is really "your input was wrong" (e.g. a 404
  on a post id) -> ``CliError(EXIT_USER_ERROR)``.
* an HTTP-shaped failure that means "your session is dead" (e.g. a 401 body
  saying to sign in) -> ``CliError(EXIT_ENV_ERROR)`` with a re-auth hint,
  since fixing it means running webglass session setup again, not retrying
  with different arguments.

Every invocation runs under a finite timeout
(:data:`DEFAULT_WEBGLASS_TIMEOUT`, 120s, overridable in seconds via
``SUBSTACK_WEBGLASS_TIMEOUT``; a non-numeric or non-positive value is
``CliError(EXIT_USER_ERROR)``). A timeout raises
``CliError(EXIT_ENV_ERROR)`` naming the variable, so a wedged browser
session can never hang an agent's command forever.

The authenticated-request verb does not exist yet in webglass-cli
(agentculture/webglass-cli#17): its name and argument shape are kept behind
the single ``request()`` function below so that once #17 lands, only this
function's body needs to change. Until then, an installed webglass asked
for that verb answers with an argparse usage/unknown-verb error; that is
recognised here and mapped to ``CliError(EXIT_ENV_ERROR)`` saying so
explicitly and citing #17, rather than the generic "did not print valid
JSON". The verbs stay registered: the gap is upstream, not in this CLI's
surface.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess  # nosec B404 - subprocess is the whole point of this adapter
from typing import Any

from substack_cli.cli._errors import EXIT_ENV_ERROR, EXIT_USER_ERROR, CliError

_BINARY = "webglass"
_SESSION_ENV_VAR = "SUBSTACK_WEBGLASS_SESSION"

#: Seconds a single ``webglass`` invocation may take before it is killed.
#: webglass drives a real browser, so this is far more generous than the HTTP
#: transport's timeout -- but it is finite: an agent-facing CLI must never
#: hang forever on a wedged subprocess.
DEFAULT_WEBGLASS_TIMEOUT = 120.0

#: Environment variable overriding :data:`DEFAULT_WEBGLASS_TIMEOUT` (seconds).
WEBGLASS_TIMEOUT_ENV_VAR = "SUBSTACK_WEBGLASS_TIMEOUT"

# webglass-cli 0.8.3 has no authenticated-request verb (issue #17). Asked for
# one, it answers like any argparse CLI asked for an unknown subcommand: a
# nonzero exit plus a usage/invalid-choice line on stderr. That is an
# environment problem ("the installed webglass cannot do this yet"), not a bad
# argument from the caller, so it maps to EXIT_ENV_ERROR with a message that
# names the real cause instead of the generic "did not print valid JSON".
_MISSING_REQUEST_VERB_MESSAGE = "webglass-cli does not provide an authenticated request verb yet"
_MISSING_REQUEST_VERB_REMEDIATION = (
    "this is tracked upstream as agentculture/webglass-cli#17; the owner/"
    "authenticated verbs cannot run until a webglass-cli release ships that "
    "verb -- upgrade webglass-cli once #17 lands, then retry"
)

# Markers of an argparse-style "I do not know that subcommand" answer.
_UNKNOWN_VERB_MARKERS = (
    "invalid choice",
    "unrecognized argument",
    "unknown command",
    "unknown verb",
    "usage:",
)

# The webglass-cli verb this adapter asks for an authenticated HTTP-shaped
# operation. Not real yet (webglass-cli#17) - isolated here so the eventual
# real verb/argument shape only needs to change in one place.
_REQUEST_VERB = "request"


def session_required() -> str:
    """Return the configured webglass session id, or raise ``CliError(2)``.

    Checked, in order, *before any subprocess runs*:

    1. Is a ``webglass`` executable on PATH at all?
    2. Is ``$SUBSTACK_WEBGLASS_SESSION`` set?

    Either failing is an environment problem (exit 2), not a user-input
    problem: there is nothing about *this command's arguments* to fix.
    """
    if shutil.which(_BINARY) is None:
        raise CliError(
            EXIT_ENV_ERROR,
            "the webglass-cli binary ('webglass') was not found on PATH",
            "install webglass-cli (see agentculture/webglass-cli) and ensure "
            "'webglass' is on PATH, then retry",
        )

    session_id = os.environ.get(_SESSION_ENV_VAR)
    if not session_id:
        raise CliError(
            EXIT_ENV_ERROR,
            f"${_SESSION_ENV_VAR} is not set",
            f"create a webglass-cli session ('webglass session create --json') "
            f"and export its session id as ${_SESSION_ENV_VAR}, then retry",
        )

    return session_id


def webglass_timeout() -> float:
    """Seconds a webglass invocation may take, from the env var or the default.

    Raises ``CliError(EXIT_USER_ERROR)`` for a value that is not a finite
    positive number: a misconfigured variable is something the caller can
    correct, so it is a user error rather than an environment failure.
    """
    raw = os.environ.get(WEBGLASS_TIMEOUT_ENV_VAR)
    if raw is None or not raw.strip():
        return DEFAULT_WEBGLASS_TIMEOUT
    remediation = (
        f"set ${WEBGLASS_TIMEOUT_ENV_VAR} to a positive number of seconds "
        f"(e.g. {DEFAULT_WEBGLASS_TIMEOUT:g}), or unset it to use the default"
    )
    try:
        value = float(raw)
    except ValueError as exc:
        raise CliError(
            EXIT_USER_ERROR,
            f"${WEBGLASS_TIMEOUT_ENV_VAR} is not a number: {raw!r}",
            remediation,
        ) from exc
    if not math.isfinite(value) or value <= 0:
        raise CliError(
            EXIT_USER_ERROR,
            f"${WEBGLASS_TIMEOUT_ENV_VAR} must be a finite positive number, got {raw!r}",
            remediation,
        )
    return value


def _missing_request_verb_error() -> CliError:
    return CliError(
        EXIT_ENV_ERROR,
        _MISSING_REQUEST_VERB_MESSAGE,
        _MISSING_REQUEST_VERB_REMEDIATION,
    )


def _looks_like_unknown_verb(text: str) -> bool:
    # Underscores are normalised so an error *code* like "unknown_verb"
    # reads the same as a message saying "unknown verb".
    lowered = (text or "").lower().replace("_", " ")
    return any(marker in lowered for marker in _UNKNOWN_VERB_MARKERS)


def _result_reports_unknown_verb(result: dict[str, Any]) -> bool:
    """True when webglass's own error object says the verb is unknown."""
    error = result.get("error")
    if not isinstance(error, dict):
        return False
    message = str(error.get("message") or "")
    code = str(error.get("code") or "")
    return _looks_like_unknown_verb(message) or _looks_like_unknown_verb(code)


def run_webglass(args: list[str]) -> dict[str, Any]:
    """Run ``webglass <args...> --json`` and return the parsed result dict.

    Never calls the real binary in tests - tests inject a fake ``webglass``
    executable on PATH (see ``tests/fakes/webglass/``) that echoes a canned
    ``WebOperationResult`` JSON payload.

    Raises ``CliError(EXIT_ENV_ERROR)`` if the binary is missing, cannot be
    executed, or does not print valid JSON on stdout. Does *not* inspect the
    parsed result's ``lifecycle_state`` - that is ``map_failure``'s job.
    """
    if shutil.which(_BINARY) is None:
        raise CliError(
            EXIT_ENV_ERROR,
            "the webglass-cli binary ('webglass') was not found on PATH",
            "install webglass-cli (see agentculture/webglass-cli) and ensure "
            "'webglass' is on PATH, then retry",
        )

    timeout = webglass_timeout()
    cmd = [_BINARY, *args, "--json"]
    try:
        completed = subprocess.run(  # nosec B603 - fixed binary name, args are ours
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise CliError(
            EXIT_ENV_ERROR,
            f"webglass timed out after {timeout:g}s: {' '.join(cmd)}",
            f"the browser session may be wedged or awaiting input; raise "
            f"${WEBGLASS_TIMEOUT_ENV_VAR} (seconds, default "
            f"{DEFAULT_WEBGLASS_TIMEOUT:g}) or re-create the webglass session, then retry",
        ) from exc
    except OSError as exc:
        raise CliError(
            EXIT_ENV_ERROR,
            f"failed to execute webglass: {exc}",
            "confirm webglass-cli is installed correctly and 'webglass' is "
            "executable on PATH, then retry",
        ) from exc

    if completed.returncode != 0 and _looks_like_unknown_verb(completed.stderr or ""):
        raise _missing_request_verb_error()

    stdout = completed.stdout or ""
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise CliError(
            EXIT_ENV_ERROR,
            "webglass did not print valid JSON on stdout",
            "run the same 'webglass ... --json' command manually to see what "
            "it printed; this usually means webglass-cli itself is broken "
            "or out of date",
        ) from exc

    if not isinstance(result, dict):
        raise CliError(
            EXIT_ENV_ERROR,
            "webglass printed JSON that was not a WebOperationResult object",
            "run the same 'webglass ... --json' command manually to inspect its output",
        )

    if _result_reports_unknown_verb(result):
        raise _missing_request_verb_error()

    return result


def _http_response(result: dict[str, Any]) -> dict[str, Any] | None:
    """Pull the HTTP-shaped ``{status, body, headers}`` out of a result, if any."""
    content = result.get("content")
    if not isinstance(content, dict):
        return None
    trusted = content.get("trusted")
    if not isinstance(trusted, dict):
        return None
    response = trusted.get("response")
    return response if isinstance(response, dict) else None


def map_failure(result: dict[str, Any]) -> None:
    """Raise the appropriate ``CliError`` for a failed webglass result.

    Does nothing when ``lifecycle_state`` is ``"succeeded"``.

    HTTP-shaped failures (``content.trusted.response.status``/``body``) are
    mapped first, since they say the most about *why* an authenticated
    request failed:

    * a 401 whose body asks the caller to sign in -> ``CliError(2)`` with a
      "log in again" remediation hint (the session is dead, not the request).
    * any other 404 -> ``CliError(1)`` (the caller named something that does
      not exist - a user-input problem).

    Otherwise falls back to webglass's own ``error`` object (an environment
    problem, e.g. ``backend_unavailable``), and finally to a generic
    environment error naming the raw ``lifecycle_state`` for any
    denied/blocked/timed_out/cancelled result webglass did not explain.
    """
    lifecycle_state = result.get("lifecycle_state")
    if lifecycle_state == "succeeded":
        return

    response = _http_response(result)
    if response is not None:
        status = response.get("status")
        body = str(response.get("body") or "")

        if status == 401 or "please sign in" in body.lower():
            raise CliError(
                EXIT_ENV_ERROR,
                f"webglass request was rejected (401): {body.strip() or 'sign-in required'}",
                "the webglass session has expired or was signed out - log in "
                "again ('webglass session create --json') and export the new "
                f"session id as ${_SESSION_ENV_VAR}, then retry",
            )

        if status == 404:
            raise CliError(
                EXIT_USER_ERROR,
                f"webglass request returned 404: {body.strip() or 'not found'}",
                "check the id/URL you passed and try again",
            )

        if isinstance(status, int) and status >= 400:
            raise CliError(
                EXIT_ENV_ERROR,
                f"webglass request failed ({status}): {body.strip() or 'no body'}",
                "inspect the response body above; retry once the underlying " "issue is resolved",
            )

    error = result.get("error")
    if isinstance(error, dict) and error.get("message"):
        raise CliError(
            EXIT_ENV_ERROR,
            f"webglass reported {error.get('code', 'an error')}: {error['message']}",
            str(error.get("remediation") or "see the webglass-cli error above"),
        )

    raise CliError(
        EXIT_ENV_ERROR,
        f"webglass operation did not succeed (lifecycle_state={lifecycle_state!r})",
        "run the same 'webglass ... --json' command manually to see the full "
        "WebOperationResult and diagnose why",
    )


def request(method: str, url: str, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Make an authenticated request through webglass and return its result.

    This is the single chokepoint for webglass-cli#17 (the authenticated
    request verb does not exist in webglass-cli yet): only this function's
    body should need to change once that verb ships, since every caller in
    substack-cli goes through here rather than shelling out directly.

    Raises ``CliError(EXIT_ENV_ERROR)`` before any subprocess runs if no
    session is configured (see ``session_required``), and raises the
    appropriate ``CliError`` (via ``map_failure``) if the request itself
    fails, is denied, or the session turns out to be invalid.
    """
    session_id = session_required()

    args = [_REQUEST_VERB, "--session-id", session_id, "--method", method, "--url", url]
    if json_body is not None:
        args += ["--json-body", json.dumps(json_body)]

    result = run_webglass(args)
    map_failure(result)
    return result
