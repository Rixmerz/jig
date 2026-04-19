"""Unified graph tool surface.

This module re-exports registration functions from the three legacy tool modules
(_graph_core, _graph_management, _graph_builder) under a single namespace so
server.py has one `from jig.tools.graph import register_all` call.

The legacy modules are kept as implementation detail. They will be merged further
in follow-up refactors.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP

from jig.tools import _graph_builder, _graph_core, _graph_management


def register_all(mcp: "FastMCP") -> None:
    """Register every graph_* tool on the given MCP instance."""
    _graph_core.register_graph_core_tools(mcp)
    _graph_management.register_graph_management_tools(mcp)
    _graph_builder.register_graph_builder_tools(mcp)
