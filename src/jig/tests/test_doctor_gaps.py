"""Tests for the three gaps closed in 0.1.0a27:

  Gap 1 — DCC injection config check (_check_dcc_injection)
  Gap 2 — Hook content drift detection (_drifted_hooks)
  Gap 3 — --dry-run unified diff (_render_dry_run_diffs)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from jig.cli.doctor import (
    _check_dcc_injection,
    _drifted_hooks,
    _render_dry_run_diffs,
    run,
    _EXPECTED_HOOKS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project(tmp_path: Path) -> Path:
    """Minimal jig-scaffolded project layout."""
    claude = tmp_path / ".claude"
    hooks = claude / "hooks"
    hooks.mkdir(parents=True)
    rules = claude / "rules"
    rules.mkdir()
    (rules / "jig-methodology.md").write_text("# jig-methodology\n")
    settings = {
        "hooks": {
            "PreToolUse": [],
            "PostToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"{sys.executable} \"$CLAUDE_PROJECT_DIR/.claude/hooks/snapshot_trigger.py\"",
                        }
                    ],
                }
            ],
        }
    }
    (claude / "settings.json").write_text(json.dumps(settings, indent=2))
    return tmp_path


def _populate_hooks_from_wheel(hooks_dir: Path) -> None:
    """Copy actual bundled hooks into hooks_dir."""
    from importlib import resources
    import jig.hooks as hooks_pkg

    bundled = resources.files(hooks_pkg)
    for entry in bundled.iterdir():
        if entry.name in _EXPECTED_HOOKS and entry.is_file():
            dest = hooks_dir / entry.name
            dest.write_bytes(entry.read_bytes())
            dest.chmod(dest.stat().st_mode | 0o111)


# ---------------------------------------------------------------------------
# Gap 1 — DCC injection config
# ---------------------------------------------------------------------------


class TestDccInjectionCheck:
    def test_no_dcc_db_returns_warning(self, tmp_path: Path) -> None:
        """When dcc.db doesn't exist, report ! with run-cube message."""
        with mock.patch("jig.cli.doctor.paths") as mock_paths:
            mock_paths.data_dir.return_value = tmp_path
            result = _check_dcc_injection(tmp_path)
        assert result is not None
        status, name, note = result
        assert status == "!"
        assert "cube_index_project" in note

    def test_empty_dcc_db_returns_warning(self, tmp_path: Path) -> None:
        """An empty dcc.db (size=0) should also warn."""
        db = tmp_path / "dcc.db"
        db.write_bytes(b"")
        with mock.patch("jig.cli.doctor.paths") as mock_paths:
            mock_paths.data_dir.return_value = tmp_path
            result = _check_dcc_injection(tmp_path)
        assert result is not None
        assert result[0] == "!"

    def test_populated_db_injection_enabled_returns_ok(self, tmp_path: Path) -> None:
        """Populated dcc.db + flags default to True → ✓."""
        db = tmp_path / "dcc.db"
        db.write_bytes(b"\x00" * 128)
        with mock.patch("jig.cli.doctor.paths") as mock_paths:
            mock_paths.data_dir.return_value = tmp_path
            with mock.patch(
                "jig.engines.hub_config.load_enforcer_config",
                return_value={"dcc_injection_enabled": True, "mid_phase_dcc": True},
            ):
                result = _check_dcc_injection(tmp_path)
        assert result is not None
        assert result[0] == "✓"

    def test_populated_db_injection_disabled_returns_warning(self, tmp_path: Path) -> None:
        """Populated dcc.db but dcc_injection_enabled=False → !."""
        db = tmp_path / "dcc.db"
        db.write_bytes(b"\x00" * 128)
        with mock.patch("jig.cli.doctor.paths") as mock_paths:
            mock_paths.data_dir.return_value = tmp_path
            with mock.patch(
                "jig.engines.hub_config.load_enforcer_config",
                return_value={"dcc_injection_enabled": False, "mid_phase_dcc": True},
            ):
                result = _check_dcc_injection(tmp_path)
        assert result is not None
        status, _, note = result
        assert status == "!"
        assert "dcc_injection_enabled=false" in note

    def test_mid_phase_disabled_returns_warning(self, tmp_path: Path) -> None:
        """mid_phase_dcc=False alone is enough to warn."""
        db = tmp_path / "dcc.db"
        db.write_bytes(b"\x00" * 128)
        with mock.patch("jig.cli.doctor.paths") as mock_paths:
            mock_paths.data_dir.return_value = tmp_path
            with mock.patch(
                "jig.engines.hub_config.load_enforcer_config",
                return_value={"dcc_injection_enabled": True, "mid_phase_dcc": False},
            ):
                result = _check_dcc_injection(tmp_path)
        assert result is not None
        status, _, note = result
        assert status == "!"
        assert "mid_phase_dcc=false" in note

    def test_both_disabled_note_contains_both(self, tmp_path: Path) -> None:
        """Both flags off → note lists both."""
        db = tmp_path / "dcc.db"
        db.write_bytes(b"\x00" * 128)
        with mock.patch("jig.cli.doctor.paths") as mock_paths:
            mock_paths.data_dir.return_value = tmp_path
            with mock.patch(
                "jig.engines.hub_config.load_enforcer_config",
                return_value={"dcc_injection_enabled": False, "mid_phase_dcc": False},
            ):
                result = _check_dcc_injection(tmp_path)
        assert result is not None
        note = result[2]
        assert "dcc_injection_enabled=false" in note
        assert "mid_phase_dcc=false" in note


# ---------------------------------------------------------------------------
# Gap 2 — Hook content drift
# ---------------------------------------------------------------------------


class TestDriftedHooks:
    def test_no_hooks_dir_returns_empty(self, tmp_path: Path) -> None:
        assert _drifted_hooks(tmp_path / "nonexistent") == []

    def test_matching_hooks_returns_empty(self, tmp_path: Path) -> None:
        """Hooks copied verbatim from wheel → no drift."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        _populate_hooks_from_wheel(hooks_dir)
        drifted = _drifted_hooks(hooks_dir)
        assert drifted == [], f"unexpected drift: {drifted}"

    def test_modified_hook_is_detected(self, tmp_path: Path) -> None:
        """A single byte change in one hook file → reported as drifted."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        _populate_hooks_from_wheel(hooks_dir)

        # Pick any hook from the expected set that actually exists
        target = next(
            (hooks_dir / name) for name in sorted(_EXPECTED_HOOKS)
            if (hooks_dir / name).exists()
        )
        original = target.read_bytes()
        target.write_bytes(original + b"\n# custom edit\n")

        drifted = _drifted_hooks(hooks_dir)
        assert target.name in drifted

    def test_extra_files_not_reported(self, tmp_path: Path) -> None:
        """Files not in _EXPECTED_HOOKS are silently ignored."""
        hooks_dir = tmp_path / "hooks"
        hooks_dir.mkdir()
        _populate_hooks_from_wheel(hooks_dir)
        (hooks_dir / "custom_hook.py").write_text("# user script\n")

        drifted = _drifted_hooks(hooks_dir)
        assert "custom_hook.py" not in drifted

    def test_drift_not_in_repair_plan(self, tmp_path: Path) -> None:
        """Drift is detected but NOT added to repair_plan (destructive opt-in)."""
        proj = _make_project(tmp_path)
        hooks_dir = proj / ".claude" / "hooks"
        _populate_hooks_from_wheel(hooks_dir)

        # Corrupt one hook
        first = next(
            (hooks_dir / name) for name in sorted(_EXPECTED_HOOKS)
            if (hooks_dir / name).exists()
        )
        first.write_bytes(first.read_bytes() + b"\n# drift\n")

        ns = argparse.Namespace(project=str(proj), repair=True, dry_run=False)
        captured_plan: list = []

        original_apply = __import__(
            "jig.cli.doctor", fromlist=["_apply_repair"]
        )._apply_repair

        with mock.patch("jig.cli.doctor._apply_repair") as mock_apply:
            with mock.patch("jig.cli.doctor.paths") as mock_paths:
                # Suppress DCC check by having no dcc.db
                mock_paths.data_dir.return_value = tmp_path / "no_data"
                (tmp_path / "no_data").mkdir()
                run(ns)
            for call in mock_apply.call_args_list:
                captured_plan.append(call.args[0])  # action string

        # drift repair should never appear
        assert "drift" not in " ".join(captured_plan)


# ---------------------------------------------------------------------------
# Gap 3 — --dry-run unified diff
# ---------------------------------------------------------------------------


class TestDryRunDiff:
    def _make_stale_settings(self, path: Path) -> None:
        settings = {
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {
                                "type": "command",
                                "command": 'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/snapshot_trigger.py"',
                            }
                        ],
                    }
                ]
            }
        }
        path.write_text(json.dumps(settings, indent=2))

    def test_diff_contains_minus_python3(self, tmp_path: Path) -> None:
        """Dry-run diff shows -python3 line."""
        settings_path = tmp_path / "settings.json"
        self._make_stale_settings(settings_path)
        plan = [("rewrite-settings", settings_path)]
        diff = _render_dry_run_diffs(plan)
        assert diff, "expected non-empty diff"
        assert '-' in diff
        assert "python3" in diff

    def test_diff_contains_plus_sys_executable(self, tmp_path: Path) -> None:
        """Dry-run diff shows +<absolute python> line."""
        settings_path = tmp_path / "settings.json"
        self._make_stale_settings(settings_path)
        plan = [("rewrite-settings", settings_path)]
        diff = _render_dry_run_diffs(plan)
        assert sys.executable in diff

    def test_diff_empty_when_no_stale_commands(self, tmp_path: Path) -> None:
        """No stale commands → diff is empty string."""
        settings_path = tmp_path / "settings.json"
        settings_path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "PostToolUse": [
                            {
                                "type": "command",
                                "command": f"{sys.executable} snapshot_trigger.py",
                            }
                        ]
                    }
                }
            )
        )
        plan = [("rewrite-settings", settings_path)]
        diff = _render_dry_run_diffs(plan)
        assert diff == ""

    def test_dry_run_flag_prevents_file_modification(self, tmp_path: Path) -> None:
        """With --dry-run, settings.json must NOT be modified."""
        proj = _make_project(tmp_path)
        settings_path = proj / ".claude" / "settings.json"
        # Inject a stale command
        raw = settings_path.read_text()
        stale = raw.replace(sys.executable, "python3")
        settings_path.write_text(stale)
        original_content = settings_path.read_text()

        # Populate hooks so hook checks pass
        hooks_dir = proj / ".claude" / "hooks"
        _populate_hooks_from_wheel(hooks_dir)

        ns = argparse.Namespace(project=str(proj), repair=True, dry_run=True)
        with mock.patch("jig.cli.doctor.paths") as mock_paths:
            mock_paths.data_dir.return_value = tmp_path / "no_data"
            (tmp_path / "no_data").mkdir(exist_ok=True)
            run(ns)

        assert settings_path.read_text() == original_content, (
            "settings.json was modified despite --dry-run"
        )

    def test_repair_without_dry_run_does_modify(self, tmp_path: Path) -> None:
        """Without --dry-run, settings.json IS rewritten."""
        proj = _make_project(tmp_path)
        settings_path = proj / ".claude" / "settings.json"
        raw = settings_path.read_text()
        stale = raw.replace(sys.executable, "python3")
        settings_path.write_text(stale)

        hooks_dir = proj / ".claude" / "hooks"
        _populate_hooks_from_wheel(hooks_dir)

        ns = argparse.Namespace(project=str(proj), repair=True, dry_run=False)
        with mock.patch("jig.cli.doctor.paths") as mock_paths:
            mock_paths.data_dir.return_value = tmp_path / "no_data"
            (tmp_path / "no_data").mkdir(exist_ok=True)
            run(ns)

        after = settings_path.read_text()
        assert sys.executable in after
        assert '"command": "python3 ' not in after
