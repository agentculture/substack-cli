"""Verify the five Substack nouns are wired into the real top-level parser.

t13 wires ``account``/``post``/``comment``/``reaction``/``feed`` into
``substack_cli.cli._build_parser`` (previously each noun module built its own
tiny parser in its own test module for isolation). This module walks the
*real* parser tree built by ``_build_parser`` and asserts:

* each noun's ``overview`` verb exits 0 in both text and ``--json`` mode
  (through the top-level ``main()`` entry point, not a hand-rolled parser);
* every registered verb under every noun accepts a ``--json`` option;
* ``learn --json`` lists exactly the v1 verb paths, each tagged with an
  ``access`` key;
* neither ``learn`` nor ``explain`` output mentions the old "clonable
  template" scaffold wording.
"""

from __future__ import annotations

import argparse
import json

import pytest

from substack_cli.cli import _build_parser, main

_NOUNS = ["account", "post", "comment", "reaction", "feed"]

_EXPECTED_LEARN_PATHS = {
    ("whoami",): "local",
    ("learn",): "local",
    ("explain",): "local",
    ("overview",): "local",
    ("doctor",): "local",
    ("cli", "overview"): "local",
    ("account", "whoami"): "owner",
    ("account", "overview"): "local",
    ("post", "list"): "public",
    ("post", "get"): "public",
    ("post", "publish"): "owner",
    ("post", "schedule"): "owner",
    ("post", "unpublish"): "owner",
    ("post", "delete"): "owner",
    ("post", "overview"): "local",
    ("comment", "list"): "public",
    ("comment", "reply"): "owner",
    ("comment", "delete"): "owner",
    ("comment", "overview"): "local",
    ("reaction", "list"): "public",
    ("reaction", "add"): "owner",
    ("reaction", "remove"): "owner",
    ("reaction", "overview"): "local",
    ("feed", "read"): "owner",
    ("feed", "overview"): "local",
}


def _subparsers_choices(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    """Return {name: subparser} for a parser's ``add_subparsers()`` action, if any."""
    for action in parser._subparsers._group_actions if parser._subparsers else []:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


def _has_json_option(parser: argparse.ArgumentParser) -> bool:
    return any("--json" in action.option_strings for action in parser._actions)


# --- noun registration ------------------------------------------------------


def test_all_five_nouns_registered() -> None:
    parser = _build_parser()
    top_level = _subparsers_choices(parser)
    for noun in _NOUNS:
        assert noun in top_level, f"{noun} not registered in _build_parser"


@pytest.mark.parametrize("noun", _NOUNS)
def test_noun_overview_exits_zero_text(noun: str, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main([noun, "overview"])
    assert rc == 0
    assert capsys.readouterr().out.strip()


@pytest.mark.parametrize("noun", _NOUNS)
def test_noun_overview_exits_zero_json(noun: str, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main([noun, "overview", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload


@pytest.mark.parametrize("noun", _NOUNS)
def test_every_verb_under_noun_accepts_json(noun: str) -> None:
    parser = _build_parser()
    top_level = _subparsers_choices(parser)
    noun_parser = top_level[noun]
    verbs = _subparsers_choices(noun_parser)
    assert verbs, f"{noun} has no registered verbs"
    for verb_name, verb_parser in verbs.items():
        assert _has_json_option(verb_parser), f"{noun} {verb_name} is missing a --json option"


# --- learn --json -------------------------------------------------------


def test_learn_json_lists_exactly_the_v1_paths(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["learn", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    got = {tuple(c["path"]): c["access"] for c in payload["commands"]}
    assert got == _EXPECTED_LEARN_PATHS


def test_learn_json_has_no_subscriber_or_stats_paths(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["learn", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    for command in payload["commands"]:
        path = command["path"]
        assert "subscriber" not in path
        assert "stats" not in path


def test_learn_json_access_values_are_known(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["learn", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    for command in payload["commands"]:
        assert command["access"] in {"public", "owner", "local"}


# --- no scaffold wording left behind -----------------------------------


def test_learn_text_has_no_clonable_template_wording(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(["learn"])
    assert rc == 0
    assert "clonable template" not in capsys.readouterr().out


def test_explain_root_has_no_clonable_template_wording(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(["explain"])
    assert rc == 0
    assert "clonable template" not in capsys.readouterr().out


def test_parser_description_has_no_clonable_template_wording() -> None:
    parser = _build_parser()
    assert "clonable template" not in (parser.description or "")
