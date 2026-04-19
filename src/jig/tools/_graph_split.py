"""Archive most graph_* tools off jig's top-level surface.

After `register_graph_core_tools`, `register_graph_management_tools`, and
`register_graph_builder_tools` have registered all 24 graph tools, this
module removes the ones not in ``_SURFACED`` from the MCP surface and
re-registers them as an internal proxy named ``graph``. They stay
discoverable via ``proxy_tools_search`` and callable via
``execute_mcp_tool("graph", ...)``.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from jig.core import embed_cache
from jig.engines import internal_proxy

if TYPE_CHECKING:
    from fastmcp import FastMCP


log = logging.getLogger(__name__)


_SURFACED: frozenset[str] = frozenset({
    "graph_activate",
    "graph_status",
    "graph_traverse",
    "graph_reset",
    "graph_list_available",
    "graph_timeline",
})


async def split(mcp: "FastMCP") -> int:
    """Move archived graph_* tools to the internal proxy. Return count moved."""
    tools = await mcp.list_tools()
    moved = 0
    cache_payload: list[dict[str, object]] = []

    for t in tools:
        name = t.name
        if not name.startswith("graph_"):
            continue
        if name in _SURFACED:
            continue
        handler = internal_proxy.InternalHandler(
            name=name,
            description=t.description or "",
            input_schema=t.parameters or {},
            fn=t.fn,
        )
        internal_proxy.register("graph", handler)
        cache_payload.append({
            "name": name,
            "description": handler.description,
            "input_schema": handler.input_schema,
        })
        mcp.local_provider.remove_tool(name)
        moved += 1

    if cache_payload:
        try:
            embed_cache.upsert_tools("graph", cache_payload)
        except Exception as e:  # pragma: no cover
            log.warning("[jig.graph_split] embed_cache upsert failed: %s", e)

    return moved
