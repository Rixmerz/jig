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
    """Register all tool modules on the MCP instance."""
    from jig.tools import guide, proxy, snapshot

    proxy.register(mcp)
    snapshot.register(mcp)
    guide.register(mcp)

    # Graph tools (legacy port; register via compatibility shim)
    try:
        from jig.tools.graph import register_all as register_graph

        register_graph(mcp)
    except Exception as e:  # pragma: no cover
        log.warning("[jig.server] failed to register graph tools: %s", e)


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
