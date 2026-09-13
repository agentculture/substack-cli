"""Repo-wide invariants that CI gates must keep true.

These are cheap, static checks — no import of `substack_cli` required for
most of them — that protect properties the CLAUDE.md commits to: no browser
automation dependency, no interactive-input code path (this is a
non-interactive agent-first CLI), an empty runtime dependency list, and a
fixed set of paths that this task must not have touched.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SUBSTACK_CLI = REPO_ROOT / "substack_cli"

# Paths this task (t16) must leave byte-for-byte identical to `main` — owned
# by other tasks in the plan.
_PROTECTED_PATHS = (
    "substack_cli/cli/_commands/doctor.py",
    ".claude/skills",
    "scripts/harness-smoke.py",
    ".github/workflows/publish.yml",
    "sonar-project.properties",
)


def _iter_source_files() -> list[Path]:
    return [p for p in SUBSTACK_CLI.rglob("*.py") if p.is_file()]


def test_no_playwright_reference() -> None:
    offenders = []
    for path in _iter_source_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "playwright" in text.lower():
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"unexpected 'playwright' reference in: {offenders}"


def test_no_input_call() -> None:
    offenders = []
    for path in _iter_source_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "input(" in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, f"unexpected 'input(' call in: {offenders}"


def test_pyproject_has_no_runtime_dependencies() -> None:
    with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
        data = tomllib.load(fh)
    assert data["project"]["dependencies"] == []


def _resolve_main_ref() -> str | None:
    for ref in ("main", "origin/main"):
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", ref],
            cwd=REPO_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            return ref
    return None


def test_protected_paths_unchanged_from_main() -> None:
    if not shutil_which("git"):
        pytest.skip("git binary not available")

    main_ref = _resolve_main_ref()
    if main_ref is None:
        pytest.skip("no 'main' or 'origin/main' ref available to diff against")

    result = subprocess.run(
        ["git", "diff", "--quiet", main_ref, "--", *_PROTECTED_PATHS],
        cwd=REPO_ROOT,
    )
    assert (
        result.returncode == 0
    ), f"protected paths differ from {main_ref}: {', '.join(_PROTECTED_PATHS)}"


def shutil_which(cmd: str) -> str | None:
    import shutil

    return shutil.which(cmd)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
