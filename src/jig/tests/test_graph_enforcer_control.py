"""Tests for graph_enforcer_toggle + the PreToolUse hook's hardcoded
allowlist that protects the toggle (and friends) from being blocked.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from jig.tools.graph_enforcer_control import (
    _read_config, _write_config, _config_path,
)
from jig.engines.graph_state import _get_centralized_state_dir


@pytest.fixture
def isolated_xdg(tmp_path: Path, monkeypatch):
    """Redirect both XDG_DATA_HOME (for engine code) and HOME (for the
    hook subprocess, which reads ``Path.home() / .local/share/jig``
    directly without going through jig.core.paths). Both must point
    inside tmp_path or the test pollutes the user's real hub."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local" / "share"))
    return home


@pytest.fixture
def fake_project(tmp_path: Path) -> str:
    p = tmp_path / "myproj"
    p.mkdir()
    return str(p)


def test_default_enforcer_enabled_when_no_config(isolated_xdg, fake_project):
    cfg = _read_config(fake_project)
    # Empty cfg means default behavior (enabled).
    assert cfg.get("enforcer_enabled", True) is True


def test_write_then_read_disabled(isolated_xdg, fake_project):
    _write_config(fake_project, {"enforcer_enabled": False})
    cfg = _read_config(fake_project)
    assert cfg["enforcer_enabled"] is False


def test_toggle_preserves_other_keys(isolated_xdg, fake_project):
    _write_config(fake_project, {
        "enforcer_enabled": True,
        "some_other_setting": "preserved",
    })
    cfg = _read_config(fake_project)
    cfg["enforcer_enabled"] = False
    _write_config(fake_project, cfg)

    cfg2 = _read_config(fake_project)
    assert cfg2["enforcer_enabled"] is False
    assert cfg2["some_other_setting"] == "preserved"


def test_config_path_uses_centralized_state_dir(isolated_xdg, fake_project):
    expected_dir = _get_centralized_state_dir(fake_project)
    assert _config_path(fake_project) == expected_dir / "config.json"


# ---- Hook-level integration: the allowlist short-circuit ---------------


HOOK_PATH = Path(__file__).resolve().parents[1] / "hooks" / "graph_enforcer.py"


def _run_hook(
    tool_name: str,
    project_dir: str,
    home: Path,
    tool_input: dict | None = None,
) -> dict:
    """Run the actual graph_enforcer.py hook as a subprocess with the
    given tool_name. Returns the parsed decision JSON. ``home`` controls
    where the hook reads its state (it uses ``Path.home()`` directly)."""
    payload: dict = {"tool_name": tool_name}
    if tool_input is not None:
        payload["tool_input"] = tool_input
    result = subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=json.dumps(payload),
        env={
            "CLAUDE_PROJECT_DIR": project_dir,
            "HOME": str(home),
            "PATH": "/usr/bin:/bin",
        },
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _seed_blocking_workflow(project_dir: str, isolated_xdg: Path) -> None:
    """Set up an active graph whose current node blocks ALL tools."""
    state_dir = _get_centralized_state_dir(project_dir)
    state_dir.mkdir(parents=True, exist_ok=True)

    # Write graph state pointing at a blocking node.
    (state_dir / "graph_state.json").write_text(json.dumps({
        "active_graph": "test-block-all",
        "current_nodes": ["locked"],
    }))

    # Write a graph YAML that blocks "*" at the current node.
    workflow_dir = Path(project_dir) / ".claude" / "workflow"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    (workflow_dir / "graph.yaml").write_text(
        "nodes:\n"
        "  - id: locked\n"
        "    tools_blocked:\n"
        "      - '*'\n"
    )


def test_hook_blocks_normal_tool_with_wildcard_workflow(
    isolated_xdg, fake_project
):
    _seed_blocking_workflow(fake_project, isolated_xdg)

    decision = _run_hook("Bash", fake_project, isolated_xdg)
    assert decision["decision"] == "block"


def test_hook_allows_graph_enforcer_toggle_even_with_wildcard(
    isolated_xdg, fake_project
):
    _seed_blocking_workflow(fake_project, isolated_xdg)

    decision = _run_hook(
        "mcp__jig__execute_mcp_tool",
        fake_project,
        isolated_xdg,
        tool_input={"mcp_name": "graph", "tool_name": "graph_enforcer_toggle", "arguments": {}},
    )
    assert decision["decision"] == "approve", (
        "graph_enforcer_toggle MUST always pass — it's the in-band "
        "recovery path. If this fails, the user can be deadlocked."
    )


def test_hook_allows_graph_reset_even_with_wildcard(
    isolated_xdg, fake_project
):
    _seed_blocking_workflow(fake_project, isolated_xdg)

    decision = _run_hook(
        "mcp__jig__execute_mcp_tool",
        fake_project,
        isolated_xdg,
        tool_input={"mcp_name": "graph", "tool_name": "graph_reset", "arguments": {}},
    )
    assert decision["decision"] == "approve"


def test_hook_allows_graph_status_even_with_wildcard(
    isolated_xdg, fake_project
):
    _seed_blocking_workflow(fake_project, isolated_xdg)

    decision = _run_hook(
        "mcp__jig__execute_mcp_tool",
        fake_project,
        isolated_xdg,
        tool_input={"mcp_name": "graph", "tool_name": "graph_status", "arguments": {}},
    )
    assert decision["decision"] == "approve"


def test_hook_respects_disabled_enforcer_flag(isolated_xdg, fake_project):
    _seed_blocking_workflow(fake_project, isolated_xdg)
    state_dir = _get_centralized_state_dir(fake_project)
    (state_dir / "config.json").write_text(json.dumps({
        "enforcer_enabled": False,
    }))

    decision = _run_hook("Bash", fake_project, isolated_xdg)
    assert decision["decision"] == "approve"


def test_hook_re_enables_when_flag_set_back_to_true(
    isolated_xdg, fake_project
):
    _seed_blocking_workflow(fake_project, isolated_xdg)
    state_dir = _get_centralized_state_dir(fake_project)
    config_path = state_dir / "config.json"

    config_path.write_text(json.dumps({"enforcer_enabled": False}))
    assert _run_hook("Bash", fake_project, isolated_xdg)["decision"] == "approve"

    config_path.write_text(json.dumps({"enforcer_enabled": True}))
    assert _run_hook("Bash", fake_project, isolated_xdg)["decision"] == "block"
