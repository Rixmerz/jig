"""Archive seldom-used tools off jig's top-level MCP surface.

Tools listed here are removed from the public MCP tool list after
registration and re-homed in the in-process ``internal_proxy`` registry.
They remain:

- Callable via ``execute_mcp_tool(<proxy>, <tool>, {...})``
- Discoverable via ``proxy_tools_search(<query>)`` (descriptions live
  in the embed cache)
- Imported as plain Python for internal jig callers (hooks, other
  engines) — registration doesn't move the function.

Archiving is the mechanism that keeps jig's top-level surface close to
the ~29-tool pitch. Add a tool here when analytics show it's called
<5% of sessions or is only used after another tool opens the door
(e.g. ``graph_builder_*`` only matters after ``graph_builder_create``).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from jig.core import embed_cache
from jig.engines import internal_proxy

if TYPE_CHECKING:
    from fastmcp import FastMCP


log = logging.getLogger(__name__)


# Map: internal-proxy name → tools archived under it.
# Keep proxy names domain-aligned with the tool prefixes so
# ``execute_mcp_tool("experience", "experience_list", ...)`` reads naturally.
ARCHIVE_MAP: dict[str, list[str]] = {
    "graph": [
        "graph_acknowledge_tensions",
        "graph_builder_add_edge",
        "graph_builder_add_node",
        "graph_builder_create",
        "graph_builder_delete",
        "graph_builder_list",
        "graph_builder_preview",
        "graph_builder_save",
        "graph_check_phrase",
        "graph_check_tool",
        "graph_get_ready_tasks",
        "graph_mid_phase_dcc",
        "graph_override_max_visits",
        "graph_record_output",
        "graph_set_node",
        "graph_task_complete",
        "graph_validate",
        "graph_visualize",
    ],
    "experience": [
        "experience_list",
        "experience_derive_checklist",
    ],
    "pattern": [
        "pattern_catalog_generate",
    ],
    "metadata": [
        "project_metadata_refresh",
    ],
    "trend": [
        "trend_record_snapshot",
        "trend_get_data",
    ],
    "workflow": [
        "workflow_set_enabled",
        "workflow_set_dcc_injection",
    ],
    "session": [
        "set_session",
    ],
    "snapshot": [
        "snapshot_create",
        "snapshot_list",
        "snapshot_diff",
        "snapshot_restore",
    ],
}


async def archive_all(mcp: "FastMCP") -> dict[str, int]:
    """Move every tool listed in ARCHIVE_MAP to its internal proxy.

    Returns a ``{proxy_name: moved_count}`` mapping.
    """
    tools_by_name = {t.name: t for t in await mcp.list_tools()}
    cache_payload: dict[str, list[dict[str, object]]] = {}
    moved: dict[str, int] = {}

    for proxy_name, tool_names in ARCHIVE_MAP.items():
        for name in tool_names:
            t = tools_by_name.get(name)
            if t is None:
                log.debug("[jig.archive] %s not registered, skipping", name)
                continue
            handler = internal_proxy.InternalHandler(
                name=name,
                description=t.description or "",
                input_schema=t.parameters or {},
                fn=t.fn,
            )
            internal_proxy.register(proxy_name, handler)
            cache_payload.setdefault(proxy_name, []).append({
                "name": name,
                "description": handler.description,
                "input_schema": handler.input_schema,
            })
            mcp.local_provider.remove_tool(name)
            moved[proxy_name] = moved.get(proxy_name, 0) + 1

    for proxy_name, records in cache_payload.items():
        try:
            embed_cache.upsert_tools(proxy_name, records)
        except Exception as e:  # pragma: no cover
            log.warning("[jig.archive] embed_cache upsert for %s failed: %s", proxy_name, e)

    return moved
