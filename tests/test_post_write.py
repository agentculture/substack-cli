"""Tests for the `post` noun's write side (publish, schedule, unpublish, delete).

Every owner-side call goes through the webglass adapter, so no test here
touches a network or a browser: a fake `webglass` executable
(tests/fakes/webglass/webglass) is prepended to PATH and fed a *sequence* of
canned WebOperationResults — one per call in the flow — via
``WEBGLASS_FAKE_SEQUENCE_DIR``. The same directory collects every
invocation's argv in ``calls.jsonl``, which is how these tests assert on the
exact method, URL and JSON body of each request (the endpoints under test are
the ones observed in docs/api/substack-endpoints.md, "Post, owner side").
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pytest

from substack_cli.cli import _CliArgumentParser
from substack_cli.cli._commands import post
from substack_cli.cli._errors import CliError
from substack_cli.cli._output import emit_error

FAKES_DIR = Path(__file__).parent / "fakes" / "webglass"

HOST = "example.substack.com"
API = f"https://{HOST}/api/v1"


# --- harness ----------------------------------------------------------------


def _make_parser() -> argparse.ArgumentParser:
    parser = _CliArgumentParser(prog="substack-cli")
    sub = parser.add_subparsers(dest="command", parser_class=_CliArgumentParser)
    post.register(sub)
    return parser


def run(argv: list[str]) -> int:
    """Parse and dispatch `argv` exactly as `substack_cli.cli.main` would."""
    _CliArgumentParser._json_hint = any(
        tok == "--json" or tok.startswith("--json=") for tok in argv
    )
    parser = _make_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_exc:  # argparse-level error already rendered
        return int(exit_exc.code or 0)
    json_mode = bool(getattr(args, "json", False))
    try:
        rc = args.func(args)
    except CliError as err:
        emit_error(err, json_mode=json_mode)
        return err.code
    return rc if rc is not None else 0


def _ok(body: object, status: int = 200) -> dict:
    return {
        "schema_version": 1,
        "operation_id": "operation-test",
        "kind": "request",
        "lifecycle_state": "succeeded",
        "content": {
            "trusted": {"response": {"status": status, "body": json.dumps(body), "headers": {}}},
            "untrusted": {},
            "sensitive": {},
            "derived": {},
        },
        "error": None,
    }


def _failed(status: int, body: str) -> dict:
    result = _ok({}, status=status)
    result["lifecycle_state"] = "failed"
    result["content"]["trusted"]["response"] = {"status": status, "body": body, "headers": {}}
    return result


class Fake:
    """A sequenced fake-webglass session for one test."""

    def __init__(self, directory: Path) -> None:
        self.dir = directory

    @property
    def calls(self) -> list[list[str]]:
        path = self.dir / "calls.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def call(self, index: int) -> dict:
        """Return {method, url, body} for the `index`-th webglass invocation."""
        argv = self.calls[index]
        parsed: dict = {"method": None, "url": None, "body": None}
        for flag, key in (("--method", "method"), ("--url", "url")):
            if flag in argv:
                parsed[key] = argv[argv.index(flag) + 1]
        if "--json-body" in argv:
            parsed["body"] = json.loads(argv[argv.index("--json-body") + 1])
        return parsed


@pytest.fixture
def fake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Fake:
    """Fake webglass on PATH with a live session and an empty response sequence."""
    monkeypatch.setenv("PATH", f"{FAKES_DIR}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("SUBSTACK_WEBGLASS_SESSION", "wg-1")
    monkeypatch.delenv("WEBGLASS_FAKE_RESPONSE", raising=False)
    monkeypatch.delenv("WEBGLASS_FAKE_RESPONSE_FILE", raising=False)
    directory = tmp_path / "webglass"
    directory.mkdir()
    monkeypatch.setenv("WEBGLASS_FAKE_SEQUENCE_DIR", str(directory))
    return Fake(directory)


def queue(fake: Fake, *responses: dict) -> None:
    for index, response in enumerate(responses):
        (fake.dir / f"response-{index}.json").write_text(json.dumps(response), encoding="utf-8")


SUBSCRIPTION = _ok({"user_id": 7, "publication_id": 99})
DRAFT_CREATED = _ok({"id": 123, "slug": "hello-world", "draft_title": "Hello"})
PUBLISHED = _ok({"id": 123, "slug": "hello-world", "is_published": True})


def _markdown_file(tmp_path: Path, text: str = "# Hello\n\nbody text") -> str:
    path = tmp_path / "post.md"
    path.write_text(text, encoding="utf-8")
    return str(path)


# --- registration -----------------------------------------------------------


def test_write_verbs_are_registered() -> None:
    parser = _make_parser()
    args = parser.parse_args(
        ["post", "publish", "--publication", HOST, "--markdown", "x.md", "--title", "T"]
    )
    assert args.func is post.cmd_post_publish
    args = parser.parse_args(
        ["post", "schedule", "--publication", HOST, "--draft", "55", "--at", "2026-10-01T09:00:00"]
    )
    assert args.func is post.cmd_post_schedule
    args = parser.parse_args(["post", "unpublish", "55", "--publication", HOST])
    assert args.func is post.cmd_post_unpublish
    args = parser.parse_args(["post", "delete", "55", "--publication", HOST])
    assert args.func is post.cmd_post_delete


def test_every_write_verb_accepts_json_flag() -> None:
    parser = _make_parser()
    for argv in (
        ["post", "publish", "--publication", HOST, "--markdown", "x.md", "--title", "T", "--json"],
        [
            "post",
            "schedule",
            "--publication",
            HOST,
            "--draft",
            "55",
            "--at",
            "2026-10-01T09:00:00",
            "--json",
        ],
        ["post", "unpublish", "55", "--publication", HOST, "--json"],
        ["post", "delete", "55", "--publication", HOST, "--json"],
    ):
        assert bool(getattr(parser.parse_args(argv), "json", False)) is True


def test_overview_lists_the_write_verbs(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(["post", "overview"]) == 0
    out = capsys.readouterr().out
    for verb in ("post publish", "post schedule", "post unpublish", "post delete"):
        assert verb in out


# --- publish: draft only ----------------------------------------------------


def test_publish_without_send_creates_draft_only(
    fake: Fake, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    queue(fake, SUBSCRIPTION, DRAFT_CREATED)

    rc = run(
        [
            "post",
            "publish",
            "--publication",
            HOST,
            "--markdown",
            _markdown_file(tmp_path),
            "--title",
            "Hello",
            "--subtitle",
            "a subtitle",
            "--json",
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["id"] == 123
    assert payload["url"] == f"https://{HOST}/p/hello-world"
    assert payload["published"] is False

    # exactly two calls: whoami-ish subscription read, then the draft create.
    assert len(fake.calls) == 2
    subscription = fake.call(0)
    assert subscription["method"] == "GET"
    assert subscription["url"] == f"{API}/subscription"

    create = fake.call(1)
    assert create["method"] == "POST"
    assert create["url"] == f"{API}/drafts"
    assert create["body"]["draft_title"] == "Hello"
    assert create["body"]["draft_subtitle"] == "a subtitle"
    assert create["body"]["type"] == "newsletter"
    assert create["body"]["audience"] == "everyone"
    assert create["body"]["draft_bylines"] == [{"id": 7, "is_guest": False}]
    # draft_body is a ProseMirror document serialized as a *string*
    assert isinstance(create["body"]["draft_body"], str)
    assert json.loads(create["body"]["draft_body"])["type"] == "doc"


def test_publish_text_mode_prints_id_and_url(
    fake: Fake, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    queue(fake, SUBSCRIPTION, DRAFT_CREATED)
    rc = run(
        [
            "post",
            "publish",
            "--publication",
            HOST,
            "--markdown",
            _markdown_file(tmp_path),
            "--title",
            "Hello",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "123" in out
    assert f"https://{HOST}/p/hello-world" in out


def test_publish_url_falls_back_to_editor_url_without_slug(
    fake: Fake, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    queue(fake, SUBSCRIPTION, _ok({"id": 123}))
    rc = run(
        [
            "post",
            "publish",
            "--publication",
            HOST,
            "--markdown",
            _markdown_file(tmp_path),
            "--title",
            "Hello",
            "--json",
        ]
    )
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["url"] == f"https://{HOST}/publish/post/123"


# --- publish: --send / --no-email -------------------------------------------


def test_publish_send_no_email_sets_send_false(
    fake: Fake, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    queue(fake, SUBSCRIPTION, DRAFT_CREATED, PUBLISHED)

    rc = run(
        [
            "post",
            "publish",
            "--publication",
            HOST,
            "--markdown",
            _markdown_file(tmp_path),
            "--title",
            "Hello",
            "--send",
            "--no-email",
            "--json",
        ]
    )

    assert rc == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["published"] is True
    assert payload["id"] == 123

    publish = fake.call(2)
    assert publish["method"] == "POST"
    assert publish["url"] == f"{API}/drafts/123/publish"
    assert publish["body"] == {"send": False, "saved_segment_id": None}
    # no-email is the quiet path: no emailing warning on stderr
    assert "email" not in captured.err.lower()


def test_publish_send_emails_subscribers_and_warns_on_stderr(
    fake: Fake, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    queue(fake, SUBSCRIPTION, DRAFT_CREATED, PUBLISHED)

    rc = run(
        [
            "post",
            "publish",
            "--publication",
            HOST,
            "--markdown",
            _markdown_file(tmp_path),
            "--title",
            "Hello",
            "--send",
            "--json",
        ]
    )

    assert rc == 0
    captured = capsys.readouterr()
    assert fake.call(2)["body"] == {"send": True, "saved_segment_id": None}
    assert "email" in captured.err.lower()
    # the warning is a diagnostic: stdout stays pure result JSON
    assert json.loads(captured.out)["published"] is True


# --- publish: partial state --------------------------------------------------


def test_publish_failure_after_draft_creation_reports_draft_and_exits_two(
    fake: Fake, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    queue(fake, SUBSCRIPTION, DRAFT_CREATED, _failed(500, "boom"))

    rc = run(
        [
            "post",
            "publish",
            "--publication",
            HOST,
            "--markdown",
            _markdown_file(tmp_path),
            "--title",
            "Hello",
            "--send",
            "--no-email",
            "--json",
        ]
    )

    assert rc == 2
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["draft_id"] == 123
    assert payload["published"] is False
    assert payload["url"] == f"https://{HOST}/p/hello-world"
    assert payload["error"]
    assert captured.err  # the underlying failure is still reported on stderr
    assert len(fake.calls) == 3  # never retried


def test_publish_404_after_draft_creation_still_exits_two(
    fake: Fake, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A user-shaped (404) publish failure is still a partial-state exit 2."""
    queue(fake, SUBSCRIPTION, DRAFT_CREATED, _failed(404, "no such draft"))

    rc = run(
        [
            "post",
            "publish",
            "--publication",
            HOST,
            "--markdown",
            _markdown_file(tmp_path),
            "--title",
            "Hello",
            "--send",
            "--no-email",
            "--json",
        ]
    )

    assert rc == 2
    assert json.loads(capsys.readouterr().out)["draft_id"] == 123


# --- publish: input handling -------------------------------------------------


def test_publish_body_json_file_is_sent_verbatim(
    fake: Fake, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    queue(fake, SUBSCRIPTION, DRAFT_CREATED)
    doc = {"type": "doc", "content": []}
    body_file = tmp_path / "body.json"
    body_file.write_text(json.dumps(doc), encoding="utf-8")

    rc = run(
        [
            "post",
            "publish",
            "--publication",
            HOST,
            "--body-json",
            str(body_file),
            "--title",
            "Hello",
            "--json",
        ]
    )

    assert rc == 0
    assert json.loads(fake.call(1)["body"]["draft_body"]) == doc


def test_publish_invalid_body_json_exits_one_before_any_call(
    fake: Fake, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body_file = tmp_path / "body.json"
    body_file.write_text("{not json", encoding="utf-8")

    rc = run(
        [
            "post",
            "publish",
            "--publication",
            HOST,
            "--body-json",
            str(body_file),
            "--title",
            "Hello",
            "--json",
        ]
    )

    assert rc == 1
    assert json.loads(capsys.readouterr().err)["code"] == 1
    assert fake.calls == []


def test_publish_unsupported_markdown_exits_one_before_any_call(
    fake: Fake, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _markdown_file(tmp_path, "> a block quote")

    rc = run(
        ["post", "publish", "--publication", HOST, "--markdown", path, "--title", "T", "--json"]
    )

    assert rc == 1
    err = json.loads(capsys.readouterr().err)
    assert err["code"] == 1
    assert "--body-json" in err["remediation"]
    assert fake.calls == []


def test_publish_missing_markdown_file_exits_two(
    fake: Fake, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = run(
        [
            "post",
            "publish",
            "--publication",
            HOST,
            "--markdown",
            str(tmp_path / "nope.md"),
            "--title",
            "T",
            "--json",
        ]
    )
    assert rc == 2
    assert fake.calls == []


def test_publish_requires_a_body_source(capsys: pytest.CaptureFixture[str]) -> None:
    rc = run(["post", "publish", "--publication", HOST, "--title", "T", "--json"])
    assert rc == 1


def test_publish_bad_publication_host_exits_one(
    fake: Fake, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = run(
        [
            "post",
            "publish",
            "--publication",
            "not a host",
            "--markdown",
            _markdown_file(tmp_path),
            "--title",
            "T",
            "--json",
        ]
    )
    assert rc == 1
    assert fake.calls == []


# --- schedule ----------------------------------------------------------------


def test_schedule_posts_scheduled_release(fake: Fake, capsys: pytest.CaptureFixture[str]) -> None:
    queue(fake, _ok({"id": 55, "slug": "later-post"}))

    rc = run(
        [
            "post",
            "schedule",
            "--publication",
            HOST,
            "--draft",
            "55",
            "--at",
            "2026-10-01T09:00:00Z",
            "--json",
        ]
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["id"] == 55
    assert payload["url"] == f"https://{HOST}/p/later-post"
    assert payload["scheduled_at"] == "2026-10-01T09:00:00Z"

    assert len(fake.calls) == 1
    call = fake.call(0)
    assert call["method"] == "POST"
    assert call["url"] == f"{API}/drafts/55/scheduled_release"
    assert call["body"] == {
        "trigger_at": "2026-10-01T09:00:00Z",
        "post_audience": "everyone",
        "saved_segment_id": None,
    }


def test_schedule_rejects_a_non_iso_timestamp(
    fake: Fake, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = run(
        ["post", "schedule", "--publication", HOST, "--draft", "55", "--at", "tomorrow", "--json"]
    )
    assert rc == 1
    assert json.loads(capsys.readouterr().err)["code"] == 1
    assert fake.calls == []


# --- unpublish / delete -------------------------------------------------------


def test_unpublish_posts_empty_body(fake: Fake, capsys: pytest.CaptureFixture[str]) -> None:
    queue(fake, _ok({}))

    rc = run(["post", "unpublish", "55", "--publication", HOST, "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["id"] == "55"
    assert payload["url"] == f"https://{HOST}/publish/post/55"
    assert payload["published"] is False

    call = fake.call(0)
    assert call["method"] == "POST"
    assert call["url"] == f"{API}/drafts/55/unpublish"
    assert call["body"] == {}
    assert len(fake.calls) == 1


def test_delete_sends_delete_on_the_draft(fake: Fake, capsys: pytest.CaptureFixture[str]) -> None:
    queue(fake, _ok({}))

    rc = run(["post", "delete", "55", "--publication", HOST, "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["id"] == "55"
    assert payload["url"] == f"https://{HOST}/publish/post/55"
    assert payload["deleted"] is True

    call = fake.call(0)
    assert call["method"] == "DELETE"
    assert call["url"] == f"{API}/drafts/55"
    assert len(fake.calls) == 1


# --- no session / no retries --------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["post", "publish", "--publication", HOST, "--title", "T", "--json"],
        [
            "post",
            "schedule",
            "--publication",
            HOST,
            "--draft",
            "55",
            "--at",
            "2026-10-01T09:00:00Z",
            "--json",
        ],
        ["post", "unpublish", "55", "--publication", HOST, "--json"],
        ["post", "delete", "55", "--publication", HOST, "--json"],
    ],
)
def test_write_verbs_exit_two_without_a_session(
    fake: Fake,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
) -> None:
    monkeypatch.delenv("SUBSTACK_WEBGLASS_SESSION", raising=False)
    if argv[1] == "publish":
        argv = argv + ["--markdown", _markdown_file(tmp_path)]

    rc = run(argv)

    assert rc == 2
    assert json.loads(capsys.readouterr().err)["code"] == 2
    assert fake.calls == []


@pytest.mark.parametrize(
    "argv",
    [
        ["post", "unpublish", "55", "--publication", HOST, "--json"],
        ["post", "delete", "55", "--publication", HOST, "--json"],
    ],
)
def test_write_verbs_never_retry_a_failed_call(
    fake: Fake, capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    queue(fake, _failed(500, "boom"))

    rc = run(argv)

    assert rc == 2
    assert len(fake.calls) == 1
