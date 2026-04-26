"""Tests for `jig graph` CLI subcommands.

Covers the recovery escape hatch: clearing graph state on disk without
needing the MCP server. Regression guard against the deadlock pattern
where a stale state blob keeps the PreToolUse enforcer blocking after
the MCP disconnects.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from jig.cli.main import main


@pytest.fixture
def fake_project(tmp_path: Path) -> Path:
    """A bare directory that looks like a project to graph_state utilities."""
    (tmp_path / ".claude" / "workflow").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def fake_state_file(tmp_path: Path, fake_project: Path, monkeypatch) -> Path:
    """Redirect XDG data dir into tmp_path so we don't pollute the user's hub."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    from jig.engines.graph_state import get_graph_state_file
    return get_graph_state_file(str(fake_project))


def _write_active_state(state_file: Path, *, graph: str, node: str) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({
        "active_graph": graph,
        "current_nodes": [node],
        "node_visits": {node: 1},
        "execution_path": [
            {"from_node": None, "to_node": node, "edge_id": None,
             "timestamp": "2026-04-26T00:00:00", "reason": "init",
             "commit_sha": None}
        ],
        "total_transitions": 0,
    }))


def test_graph_reset_clears_active_state(
    fake_project: Path, fake_state_file: Path, capsys
):
    _write_active_state(fake_state_file, graph="debug", node="understand")
    assert fake_state_file.exists()

    rc = main(["graph", "reset", "--project", str(fake_project)])
    assert rc == 0

    cleared = json.loads(fake_state_file.read_text())
    assert cleared["active_graph"] is None
    assert cleared["current_nodes"] == []
    assert cleared["execution_path"] == []

    out = capsys.readouterr().out
    assert "Cleared" in out
    assert "debug" in out  # mentions previous graph
    assert "understand" in out  # mentions previous node


def test_graph_reset_dry_run_does_not_write(
    fake_project: Path, fake_state_file: Path, capsys
):
    _write_active_state(fake_state_file, graph="demo-feature", node="design")
    original = fake_state_file.read_text()

    rc = main([
        "graph", "reset", "--project", str(fake_project), "--dry-run"
    ])
    assert rc == 0

    assert fake_state_file.read_text() == original  # untouched
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert "demo-feature" in out


def test_graph_reset_no_state_is_noop(
    fake_project: Path, fake_state_file: Path, capsys
):
    assert not fake_state_file.exists()

    rc = main(["graph", "reset", "--project", str(fake_project)])
    assert rc == 0

    out = capsys.readouterr().out
    assert "Nothing to reset" in out
    assert not fake_state_file.exists()


def test_graph_status_shows_active_workflow(
    fake_project: Path, fake_state_file: Path, capsys
):
    _write_active_state(fake_state_file, graph="debug", node="understand")

    rc = main(["graph", "status", "--project", str(fake_project)])
    assert rc == 0

    out = capsys.readouterr().out
    assert "active_graph" in out
    assert "debug" in out
    assert "understand" in out


def test_graph_status_handles_missing_file(
    fake_project: Path, fake_state_file: Path, capsys
):
    assert not fake_state_file.exists()

    rc = main(["graph", "status", "--project", str(fake_project)])
    assert rc == 0

    out = capsys.readouterr().out
    assert "No state file" in out


def test_graph_reset_uses_cwd_when_no_project_arg(
    fake_project: Path, fake_state_file: Path, monkeypatch, capsys
):
    _write_active_state(fake_state_file, graph="debug", node="understand")
    monkeypatch.chdir(fake_project)

    rc = main(["graph", "reset"])
    assert rc == 0

    cleared = json.loads(fake_state_file.read_text())
    assert cleared["active_graph"] is None


def test_graph_no_subcommand_prints_help(fake_project: Path, capsys):
    rc = main(["graph"])
    assert rc == 1  # prints help and exits with non-zero
    out = capsys.readouterr().out
    assert "reset" in out
    assert "status" in out
