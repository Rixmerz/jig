"""Unified graph tool surface.

Registers every ``graph_*`` tool. Archiving to the internal proxy
happens later in ``server._register_tools`` via ``_tool_archive`` so
all domains (graph, experience, trend, ...) split in a single pass.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP

from jig.tools import _graph_builder, _graph_core, _graph_management


def register_all(mcp: "FastMCP") -> None:
    """Register every graph_* tool on the MCP."""
    _graph_core.register_graph_core_tools(mcp)
    _graph_management.register_graph_management_tools(mcp)
    _graph_builder.register_graph_builder_tools(mcp)
