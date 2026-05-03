"""FastMCP server — wires engines + tools into a single stdio MCP endpoint."""
from __future__ import annotations

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
        deployment,
        experience,
        graph_enforcer_control,
        guide,
        memory,
        metadata,
        patterns,
        proxy,
        resync,
        snapshot,
        trends,
    )
    from jig.tools import (
        config as config_tools,
    )
    from jig.tools import (
        next_task as next_task_tools,
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
    resync.register_resync_tools(mcp)

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

    # DeltaCodeCube has been extracted to the standalone ``delta-cube`` package.
    # The vendored engines/dcc/ folder has been removed.  Users who want DCC
    # analysis tools should install the package and register it as an MCP proxy:
    #
    #   uvx delta-cube          (runs the MCP server)
    #   proxy_add("dcc", "uvx", ["delta-cube"])
    #
    # Once registered, all cube_* tools are discoverable via proxy_tools_search
    # and callable via execute_mcp_tool("dcc", …) exactly as before.
    log.debug("[jig.server] DCC internal proxy skipped — use standalone delta-cube package")


def _install_proxy_cleanup() -> None:
    """Make sure proxied MCP subprocesses die when jig itself exits.

    Two paths:
      - `atexit` for clean exits (FastMCP loop returns normally).
      - SIGTERM/SIGINT/SIGHUP handlers for signal-driven shutdowns,
        including the SIGTERM that PR_SET_PDEATHSIG sends when the
        parent Claude session dies.

    Both invoke `terminate_all_sync`, which signals each proxy's
    process group directly — no asyncio loop required, since by this
    point FastMCP's loop is already torn down. After the cleanup
    completes, signal handlers re-raise the original signal under the
    default disposition so the process actually exits with the
    expected status.
    """
    import atexit
    import os
    import signal as _signal

    from jig.engines.proxy_pool import terminate_all_sync

    _ran = False

    def _cleanup() -> None:
        nonlocal _ran
        if _ran:
            return
        _ran = True
        try:
            killed = terminate_all_sync()
            if killed:
                print(
                    f"[jig] terminated {len(killed)} proxied MCP(s): "
                    f"{', '.join(killed)}",
                    file=sys.stderr,
                )
        except Exception as e:
            print(f"[jig] proxy cleanup failed: {e}", file=sys.stderr)

    atexit.register(_cleanup)

    def _on_signal(signum: int, _frame) -> None:
        _cleanup()
        _signal.signal(signum, _signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    for sig in (_signal.SIGTERM, _signal.SIGINT, _signal.SIGHUP):
        try:
            _signal.signal(sig, _on_signal)
        except (OSError, ValueError):
            pass


def _install_parent_death_signal() -> None:
    """On Linux, ask the kernel to SIGTERM us if the parent (claude) dies.

    Why: when the Claude Code session exits without cleanly closing stdio,
    the FastMCP loop can stay alive holding ~2 GB of fastembed weights.
    PR_SET_PDEATHSIG is a kernel-level guarantee — no polling needed.
    """
    if not sys.platform.startswith("linux"):
        return
    try:
        import ctypes
        import signal as _signal

        PR_SET_PDEATHSIG = 1
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.prctl(PR_SET_PDEATHSIG, _signal.SIGTERM, 0, 0, 0)
    except Exception as e:
        log.debug("[jig.server] PR_SET_PDEATHSIG not installed: %s", e)


def serve() -> None:
    """Start the MCP server on stdio. Blocks until the client disconnects."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )
    _install_parent_death_signal()
    _install_proxy_cleanup()
    print(f"[jig] starting MCP server v{__version__}", file=sys.stderr)
    _register_tools()
    mcp.run()


if __name__ == "__main__":
    serve()
