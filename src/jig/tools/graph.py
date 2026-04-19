"""Unified graph tool surface.

Registers all 24 graph_* tools on the MCP, then archives 18 of them to an
internal proxy (``execute_mcp_tool("graph", ...)``), leaving only the hot
path on jig's top-level surface. See ``_graph_split._SURFACED`` for the
short list.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP

from jig.tools import _graph_builder, _graph_core, _graph_management, _graph_split


log = logging.getLogger(__name__)


def register_all(mcp: "FastMCP") -> None:
    """Register every graph_* tool, then split surfaced vs. archived."""
    _graph_core.register_graph_core_tools(mcp)
    _graph_management.register_graph_management_tools(mcp)
    _graph_builder.register_graph_builder_tools(mcp)

    moved = asyncio.run(_graph_split.split(mcp))
    log.info("[jig.graph] %d graph_* tools archived to internal proxy", moved)
