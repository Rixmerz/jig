"""FastMCP server — wires engines + tools into a single stdio MCP endpoint."""
from __future__ import annotations

import asyncio
import logging
import sys

from fastmcp import FastMCP

from jig import __version__

log = logging.getLogger(__name__)

mcp: FastMCP = FastMCP(
    name="jig",
    instructions=(
        "jig enforces phase-gated workflows and proxies every other MCP you have "
        "configured, exposing them on demand via proxy_tools_search + "
        "execute_mcp_tool. Start with jig_guide(topic='getting-started')."
    ),
)


@mcp.tool()
def jig_version() -> dict[str, str]:
    """Return the installed jig version."""
    return {"version": __version__}


def _register_tools() -> None:
    """Register all tool modules on the MCP instance, then archive the
    seldom-used ones to internal proxies per ``_tool_archive.ARCHIVE_MAP``.
    """
    import asyncio

    from jig.tools import (
        _tool_archive,
        config as config_tools,
        deployment,
        experience,
        graph_enforcer_control,
        guide,
        metadata,
        memory,
        next_task as next_task_tools,
        patterns,
        proxy,
        snapshot,
        trends,
    )

    proxy.register(mcp)
    snapshot.register(mcp)
    guide.register(mcp)
    experience.register_experience_tools(mcp)
    patterns.register_pattern_catalog_tools(mcp)
    metadata.register_project_metadata_tools(mcp)
    trends.register_trend_tools(mcp)
    deployment.register_deployment_tools(mcp)
    config_tools.register_config_tools(mcp)
    next_task_tools.register_next_task_tools(mcp)
    graph_enforcer_control.register_graph_enforcer_control_tools(mcp)
    memory.register_memory_tools(mcp)

    try:
        from jig.tools.graph import register_all as register_graph

        register_graph(mcp)
    except Exception as e:  # pragma: no cover
        log.warning("[jig.server] failed to register graph tools: %s", e)

    try:
        moved = asyncio.run(_tool_archive.archive_all(mcp))
        total = sum(moved.values())
        log.info(
            "[jig.server] archived %d tools to internal proxies: %s",
            total,
            moved,
        )
    except Exception as e:  # pragma: no cover
        log.warning("[jig.server] tool archival failed: %s", e)

    # Expose the vendored DeltaCodeCube as an internal proxy so its
    # ~40 analysis tools are callable via ``execute_mcp_tool("dcc", …)``
    # and discoverable via ``proxy_tools_search`` without the user
    # having to register an external DCC MCP with ``proxy_add``.
    try:
        from fastmcp import FastMCP
        from jig.engines.dcc.tools import register_all_tools as _dcc_register

        dcc_holder = FastMCP(name="_dcc_holder")
        _dcc_register(dcc_holder)
        dcc_count = asyncio.run(_tool_archive.archive_external_mcp(dcc_holder, "dcc"))
        log.info("[jig.server] DCC internal proxy: %d tools", dcc_count)
    except Exception as e:  # pragma: no cover
        log.warning("[jig.server] DCC internal proxy registration failed: %s", e)


async def _warmup_embed_model() -> None:
    """Touch fastembed in background so the first search isn't slow."""
    try:
        from jig.core.embeddings import get_embedder

        emb = get_embedder()
        if emb.available:
            await asyncio.to_thread(emb.embed_one, "warmup")
            log.info("[jig.server] embedding model warm")
    except Exception as e:
        log.debug("[jig.server] embed warmup skipped: %s", e)


def serve() -> None:
    """Start the MCP server on stdio. Blocks until the client disconnects."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )
    print(f"[jig] starting MCP server v{__version__}", file=sys.stderr)
    _register_tools()

    # Warmup in background — don't block startup
    try:
        loop = asyncio.new_event_loop()
        loop.create_task(_warmup_embed_model())
    except Exception:
        pass

    mcp.run()


if __name__ == "__main__":
    serve()
