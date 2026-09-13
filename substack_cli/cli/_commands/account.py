"""``substack-cli account`` — account-identity probe over the webglass session.

Endpoint facts this module is built on (observed in the owner's logged-in
browser; see task t5 / ``.devague`` plan for provenance):

* ``GET https://<publication-host>/api/v1/subscription`` (session required)
  returns ``{id, user_id, publication_id, email_disabled, ...}`` — this *is*
  the whoami source: ``user_id`` is the signed-in user's account id.
* ``GET https://<publication-host>/api/v1/publication`` returns the owner's
  publication object (``id``, ``subdomain``, ``name``, ``custom_domain``
  among its keys) when signed in, and answers ``403`` when not.
* ``GET https://substack.com/api/v1/user/self`` answers ``403`` **even when
  signed in** — it is *not* a whoami source, so this module never calls it.
* The sign-out signal is HTTP ``401`` with a JSON body shaped
  ``{"errors": [{"msg": "Please sign in", ...}]}`` — this is exactly what
  :func:`substack_cli.substack.webglass.map_failure` already maps to an
  environment error with a "log in again" remediation, so ``whoami`` does
  not re-implement that mapping; it just lets ``webglass.request`` raise.

``whoami`` makes two ``webglass.request("GET", ...)`` calls against the
*publication* API base for the required ``--publication`` host — never the
network directly, and never ``substack.com/api/v1/user/self`` — in this
order: ``/subscription`` first (for ``user_id``), then ``/publication`` (for
the publication block). Three states, all driven through
``webglass.request``/``session_required``/``map_failure``:

1. no ``$SUBSTACK_WEBGLASS_SESSION`` configured -> ``CliError(EXIT_ENV_ERROR)``
   from :func:`webglass.session_required` ("no session named"), raised before
   either call runs.
2. a session is configured but either call answers 401 -> the same
   ``CliError(EXIT_ENV_ERROR)`` webglass's ``map_failure`` already raises for
   a dead session, with a "log in again" remediation. ``/subscription`` is
   called first, so a dead session never reaches ``/publication``.
3. both calls answer 200 -> ``whoami`` parses the JSON bodies and reports
   ``{user_id, publication: {id, subdomain, name, custom_domain}}`` on
   stdout, exit 0.

The webglass-on-PATH/version check lives here (``account overview``), not in
``doctor.py`` — ``doctor`` only diagnoses the agent-identity invariants
(prompt file / backend consistency), and h7 requires it stay that way.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess  # nosec B404 - subprocess is the whole point of this probe
from typing import Any

from substack_cli.cli._commands._help import JSON_HELP
from substack_cli.cli._errors import EXIT_ENV_ERROR, CliError
from substack_cli.cli._output import emit_result
from substack_cli.substack import http, webglass

_WEBGLASS_BINARY = "webglass"

_PUBLICATION_FIELDS = ("id", "subdomain", "name", "custom_domain")


def _webglass_version() -> str | None:
    """Best-effort ``webglass --version`` string, or ``None`` if unavailable.

    Never raises: any failure to run or parse just means "unknown version",
    which ``overview`` reports rather than treating as a hard error --
    descriptive verbs must not hard-fail (rubric bundle 7).
    """
    if shutil.which(_WEBGLASS_BINARY) is None:
        return None
    try:
        completed = subprocess.run(  # nosec B603 - fixed binary name
            [_WEBGLASS_BINARY, "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    text = (completed.stdout or completed.stderr or "").strip()
    return text or None


def _response_body(result: dict[str, Any]) -> str:
    response = result.get("content", {}).get("trusted", {}).get("response", {})
    return str(response.get("body") or "")


def _json_object_from_body(body: str, *, url: str) -> dict[str, Any]:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise CliError(
            EXIT_ENV_ERROR,
            f"webglass's response body from {url} was not valid JSON",
            f"run 'webglass request --method GET --url {url} --json' manually "
            "to inspect what came back",
        ) from exc
    if not isinstance(parsed, dict):
        raise CliError(
            EXIT_ENV_ERROR,
            f"webglass's response body from {url} was not a JSON object",
            f"run 'webglass request --method GET --url {url} --json' manually "
            "to inspect what came back",
        )
    return parsed


def whoami_report(publication_host_arg: str) -> dict[str, Any]:
    """Probe the webglass session and return the ``{user_id, publication}`` report.

    Two calls, in order: ``/subscription`` first (its ``user_id`` field is
    the signed-in user's account id — see module docstring), then
    ``/publication`` (the publication block). Raises ``CliError`` (via
    ``http.publication_host``, ``webglass.request``, or this function's own
    body-parsing) for every non-authenticated state; only returns normally
    once *both* calls answered 200 with a JSON object.
    """
    host = http.publication_host(publication_host_arg)
    base = http.publication_base(host)

    subscription_url = f"{base}/subscription"
    subscription_result = webglass.request("GET", subscription_url)
    # webglass.request already calls map_failure and raises on anything but a
    # succeeded lifecycle_state, so by this point the request succeeded.
    subscription = _json_object_from_body(_response_body(subscription_result), url=subscription_url)

    publication_url = f"{base}/publication"
    publication_result = webglass.request("GET", publication_url)
    publication_body = _json_object_from_body(
        _response_body(publication_result), url=publication_url
    )
    publication = {field: publication_body.get(field) for field in _PUBLICATION_FIELDS}

    return {
        "user_id": subscription.get("user_id"),
        "publication": publication,
    }


def cmd_account_whoami(args: argparse.Namespace) -> int:
    report = whoami_report(args.publication)
    json_mode = bool(getattr(args, "json", False))
    if json_mode:
        emit_result(report, json_mode=True)
        return 0
    publication = report["publication"]
    lines = [
        f"user_id: {report['user_id']}",
        f"publication.id: {publication.get('id')}",
        f"publication.subdomain: {publication.get('subdomain')}",
        f"publication.name: {publication.get('name')}",
        f"publication.custom_domain: {publication.get('custom_domain')}",
    ]
    emit_result("\n".join(lines), json_mode=False)
    return 0


def account_overview_report() -> dict[str, Any]:
    present = shutil.which(_WEBGLASS_BINARY) is not None
    return {
        "webglass_on_path": present,
        "webglass_version": _webglass_version() if present else None,
    }


def cmd_account_overview(args: argparse.Namespace) -> int:
    report = account_overview_report()
    json_mode = bool(getattr(args, "json", False))
    if json_mode:
        emit_result(report, json_mode=True)
        return 0
    lines = [
        f"webglass on PATH: {'yes' if report['webglass_on_path'] else 'no'}",
        f"webglass version: {report['webglass_version'] or 'unknown'}",
    ]
    emit_result("\n".join(lines), json_mode=False)
    return 0


def _no_verb(args: argparse.Namespace) -> int:
    # `substack-cli account` with no sub-verb prints the noun's overview.
    return cmd_account_overview(args)


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "account",
        help="Account identity probe over the webglass session "
        "(see 'substack-cli account overview').",
    )
    p.add_argument("--json", action="store_true", help=JSON_HELP)
    p.set_defaults(func=_no_verb, json=False)
    # `p` is a _CliArgumentParser (the top-level subparsers were built with that
    # parser_class); propagate it so `account whoami`/`account overview` parse
    # errors route through the structured error contract instead of argparse's
    # default stderr/exit 2.
    noun_sub = p.add_subparsers(dest="account_command", parser_class=type(p))

    who = noun_sub.add_parser(
        "whoami",
        help="Probe the webglass session against a publication's API and report "
        "the authenticated account (three-state: no session, dead session, "
        "authenticated).",
    )
    who.add_argument("--json", action="store_true", help=JSON_HELP)
    who.add_argument(
        "--publication",
        required=True,
        help="Publication host to probe, e.g. example.substack.com "
        "(required; validated as a bare hostname).",
    )
    who.set_defaults(func=cmd_account_whoami)

    ov = noun_sub.add_parser(
        "overview",
        help="Report whether webglass is available for account operations "
        "(presence + version); never fails on a missing webglass install.",
    )
    ov.add_argument("--json", action="store_true", help=JSON_HELP)
    ov.set_defaults(func=cmd_account_overview)
