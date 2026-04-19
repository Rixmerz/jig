"""XDG-compliant path resolution for jig state, config, cache, and data.

Directory layout:
    ~/.config/jig/         → user configuration (proxy.toml, global overrides)
    ~/.local/share/jig/    → persistent application data (embeddings, snapshots, DCC db)
    ~/.cache/jig/          → regenerable caches
    $PROJECT/.jig/         → per-project state (lockfiles, ephemeral)

All paths respect $XDG_CONFIG_HOME / $XDG_DATA_HOME / $XDG_CACHE_HOME when set.
"""
from __future__ import annotations

import os
from pathlib import Path

_APP = "jig"


def _xdg(var: str, default: Path) -> Path:
    raw = os.environ.get(var)
    return Path(raw).expanduser() if raw else default


def config_dir() -> Path:
    """User configuration: ~/.config/jig/ by default."""
    base = _xdg("XDG_CONFIG_HOME", Path.home() / ".config")
    return base / _APP


def data_dir() -> Path:
    """Persistent application data: ~/.local/share/jig/ by default."""
    base = _xdg("XDG_DATA_HOME", Path.home() / ".local" / "share")
    return base / _APP


def cache_dir() -> Path:
    """Regenerable cache: ~/.cache/jig/ by default."""
    base = _xdg("XDG_CACHE_HOME", Path.home() / ".cache")
    return base / _APP


def project_state_dir(project_dir: Path) -> Path:
    """Per-project ephemeral state: $PROJECT/.jig/."""
    return Path(project_dir) / ".jig"


def ensure(path: Path) -> Path:
    """Create the directory (parents included) and return the path."""
    path.mkdir(parents=True, exist_ok=True)
    return path


__all__ = [
    "cache_dir",
    "config_dir",
    "data_dir",
    "ensure",
    "project_state_dir",
]
