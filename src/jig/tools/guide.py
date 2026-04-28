"""`jig_guide(topic)` — serve markdown documentation from package data.

Guides live at src/jig/assets/guides/*.md and are loaded via importlib.resources
so they work identically from editable installs, wheels, and uvx.
"""
from __future__ import annotations

from importlib import resources
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp import FastMCP


def list_topics() -> list[str]:
    try:
        import jig.assets as assets_pkg
        guides = resources.files(assets_pkg) / "guides"
        if not guides.is_dir():
            return []
        return sorted(
            e.name.removesuffix(".md")
            for e in guides.iterdir()
            if e.is_file() and e.name.endswith(".md")
        )
    except Exception:
        return []


def load_topic(topic: str) -> str | None:
    """Return guide markdown or None if the topic is unknown."""
    try:
        import jig.assets as assets_pkg
        guides = resources.files(assets_pkg) / "guides"
        path = guides / f"{topic}.md"
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def register(mcp: "FastMCP") -> None:
    @mcp.tool()
    def jig_guide(topic: str = "") -> dict[str, Any]:
        """Serve jig's bundled method/reference documentation.

        Call with topic="" to list available topics. Topics cover creating
        workflows, designing proxies, using snapshots, interpreting tensions,
        and more. Agents should call this before unfamiliar operations.

        Args:
            topic: guide name (without the .md extension). Empty lists all.
        """
        topics = list_topics()
        if not topic:
            return {
                "topics": topics,
                "usage": "jig_guide(topic='create-workflow')",
            }
        content = load_topic(topic)
        if content is None:
            return {
                "error": f"unknown topic '{topic}'",
                "available": topics,
            }
        return {"topic": topic, "content": content}


# `jig_guide` is the MCP tool name but is defined inside `register()` (not module-level).
__all__ = ["list_topics", "load_topic", "register"]
