"""FastMCP server entry point.

Minimal bootstrap skeleton. Sprint 1 ports engines/ and tools/ and wires the full
registration. Sprint 2a adds fastembed warmup in the lifespan. This file stays thin
on purpose — domain logic lives in engines/ and tools/.
"""
from __future__ import annotations

import sys

from fastmcp import FastMCP

from jig import __version__

mcp: FastMCP = FastMCP(
    name="jig",
    instructions=(
        "jig enforces disciplined, phase-gated workflows for AI coding agents and "
        "exposes a semantic catalog of proxied MCP tools. Call jig_guide(topic='getting-started') "
        "for orientation."
    ),
)


@mcp.tool()
def jig_version() -> dict[str, str]:
    """Return the installed jig version. Placeholder until the full tool surface lands."""
    return {"version": __version__}


def serve() -> None:
    """Start the MCP server on stdio. Blocks until the client disconnects."""
    print(f"[jig] starting MCP server v{__version__}", file=sys.stderr)
    mcp.run()


if __name__ == "__main__":
    serve()
