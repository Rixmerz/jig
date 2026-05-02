"""Tests for ``jig emit-cursor`` / :mod:`jig.cli.cursor_emit`."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from jig.cli.cursor_emit import emit_cursor_bundle


def test_emit_cursor_bundle_dry_run_minimal(tmp_path: Path) -> None:
    out = emit_cursor_bundle(
        tmp_path,
        py_exe=sys.executable,
        tech_stack=["python"],
        dry_run=True,
    )
    assert out.get("success") is True
    assert out.get("dry_run") is True
    assert "agents" in out and "skills" in out


def test_emit_cursor_writes_hooks_json_and_skills(tmp_path: Path) -> None:
    (tmp_path / ".gitkeep").write_text("", encoding="utf-8")
    out = emit_cursor_bundle(
        tmp_path,
        py_exe=sys.executable,
        tech_stack=None,
        dry_run=False,
    )
    assert out.get("success") is True
    hooks = tmp_path / ".cursor" / "hooks.json"
    assert hooks.is_file()
    data = json.loads(hooks.read_text(encoding="utf-8"))
    assert data.get("version") == 1
    assert "hooks" in data
    assert "preToolUse" in data["hooks"]
    runner = tmp_path / ".cursor" / "hooks" / "jig_cursor_hook_runner.py"
    assert runner.is_file()
    assert (tmp_path / ".cursor" / "README.jig-cursor.md").is_file()
    assert out.get("skills_copied"), "expected at least one skill directory"


def test_emit_cursor_hook_runner_translates_decision() -> None:
    from jig.hooks import jig_cursor_hook_runner as runner

    allow = json.loads(runner._translate_hook_stdout('{"decision":"approve"}'))
    assert allow.get("permission") == "allow"
    deny = json.loads(
        runner._translate_hook_stdout('{"decision":"block","message":"nope"}')
    )
    assert deny.get("permission") == "deny"
    assert "nope" in deny.get("user_message", "")
