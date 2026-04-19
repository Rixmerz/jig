"""Hub configuration for jig.

XDG-only. `hub_dir` points at ~/.local/share/jig, `workflows_dir`
holds YAML graph definitions, `states_dir` holds per-project graph
state. Everything resolves off `jig.core.paths.data_dir()`.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from jig.core import paths

_hub_config: dict | None = None


def _defaults() -> dict:
    return {
        "hub_dir": str(paths.data_dir()),
        "workflows_dir": "workflows",
        "states_dir": "states",
    }


def load_hub_config() -> dict:
    global _hub_config
    if _hub_config is None:
        _hub_config = _defaults()
    return _hub_config


def get_hub_dir() -> Path:
    return Path(load_hub_config()["hub_dir"])


def get_global_workflows_dir() -> Path:
    config = load_hub_config()
    return Path(config["hub_dir"]) / config["workflows_dir"]


def get_project_state_dir(project_dir: str) -> Path:
    config = load_hub_config()
    project_name = Path(project_dir).name
    return Path(config["hub_dir"]) / config["states_dir"] / project_name


def get_workflow_dir(project_dir: str) -> Path:
    """Per-project workflow directory: {project_dir}/.claude/workflow/."""
    if not project_dir:
        raise ValueError("project_dir is required.")
    project_path = Path(project_dir)
    if not project_path.exists():
        raise ValueError(f"Project directory does not exist: {project_dir}")
    return project_path / ".claude" / "workflow"


def get_workflows_library_dir(project_dir: str | None = None) -> Path:
    """Global workflows library (shared across projects)."""
    return get_global_workflows_dir()


CLAUDE_CODE_CONFIG = Path.home() / ".claude.json"


def load_mcp_configs() -> dict[str, dict]:
    """Load MCP configurations from ~/.claude.json (Claude Code user config)."""
    try:
        if CLAUDE_CODE_CONFIG.exists():
            config = json.loads(CLAUDE_CODE_CONFIG.read_text())
            return config.get("mcpServers", {})
    except Exception as e:
        print(f"[jig] warning: failed to read Claude Code config: {e}", file=sys.stderr)
    return {}


# ============================================================================
# Enforcer Configuration
# ============================================================================


def get_enforcer_config_file(project_dir: str) -> Path:
    return get_project_state_dir(project_dir) / "config.json"


def load_enforcer_config(project_dir: str) -> dict:
    config_file = get_enforcer_config_file(project_dir)
    if config_file.exists():
        try:
            return json.loads(config_file.read_text())
        except Exception as e:
            print(f"[jig] warning: failed to load enforcer config: {e}", file=sys.stderr)
    return {"enforcer_enabled": True, "mid_phase_dcc": True}


def save_enforcer_config(project_dir: str, config: dict):
    config_file = get_enforcer_config_file(project_dir)
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config["last_updated"] = datetime.now().isoformat()
    config_file.write_text(json.dumps(config, indent=2))
