"""Proxy management + execution tools.

These are the 8 proxy_* tools plus `execute_mcp_tool`. They form the core of
jig's token-economy proposition: one MCP registered in .mcp.json (jig), which
transparently brokers every other MCP the user has configured.

Tool surface:
    proxy_add           — register + connect an MCP subprocess
    proxy_remove        — unregister + stop + purge cache
    proxy_reconnect     — force restart a proxy subprocess
    proxy_list          — list registered proxies + status
    proxy_list_tools    — enumerate tools for a specific proxy
    proxy_tools_search  — semantic search across proxied tools (cache-driven)
    proxy_refresh       — re-embed tools for a proxy (after upgrade/reinstall)
    proxy_keepalive     — extend idle timeout ad-hoc
    execute_mcp_tool    — invoke a tool on a proxied MCP
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp import FastMCP

from jig.core import embed_cache
from jig.engines import proxy_pool


def register(mcp: "FastMCP") -> None:
    @mcp.tool()
    async def proxy_add(
        name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        idle_timeout_seconds: float = proxy_pool.DEFAULT_IDLE_TIMEOUT,
        warmup: bool = True,
    ) -> dict[str, Any]:
        """Register a new MCP as a proxy and embed its tools.

        If warmup=True (default), spawns the subprocess, calls tools/list, and
        writes embeddings to the global cache so proxy_tools_search can return
        results immediately without another connection.
        """
        await proxy_pool.proxy_register(
            name, command, args=args, env=env, idle_timeout_seconds=idle_timeout_seconds
        )
        embedded = 0
        error: str | None = None
        if warmup:
            try:
                embedded = await proxy_pool.proxy_refresh_embeddings(name)
            except Exception as e:
                error = f"warmup failed: {e}"
        return {
            "registered": name,
            "embedded_tools": embedded,
            "warmup_error": error,
        }

    @mcp.tool()
    async def proxy_remove(name: str) -> dict[str, Any]:
        """Unregister a proxy, stop its process, and purge embeddings."""
        removed = await proxy_pool.proxy_unregister(name)
        return {"removed": removed, "name": name}

    @mcp.tool()
    async def proxy_reconnect(name: str) -> dict[str, Any]:
        """Force-restart a proxy subprocess. Use after the MCP misbehaves."""
        ok = await proxy_pool.proxy_reconnect(name)
        return {"reconnected": ok, "name": name}

    @mcp.tool()
    async def proxy_list() -> dict[str, Any]:
        """List all registered proxies with live status."""
        statuses = await proxy_pool.proxy_statuses()
        return {
            "proxies": [
                {
                    "name": s.name,
                    "connected": s.connected,
                    "tool_count": s.tool_count,
                    "last_error": s.last_error,
                }
                for s in statuses
            ]
        }

    @mcp.tool()
    async def proxy_list_tools(name: str) -> dict[str, Any]:
        """List tools for a specific proxied MCP (from the embedding cache)."""
        records = embed_cache.list_tools(mcp_name=name)
        return {
            "proxy": name,
            "tools": [
                {
                    "name": r.tool_name,
                    "description": r.description,
                    "input_schema": r.input_schema,
                }
                for r in records
            ],
        }

    @mcp.tool()
    async def proxy_tools_search(
        query: str,
        top_k: int = 10,
        proxy: str | None = None,
    ) -> dict[str, Any]:
        """Semantic search across proxied MCP tools.

        Reads the embedding cache directly — never requires a live connection.
        Returns tools ranked by similarity to the query. Use this to discover
        capabilities before calling `execute_mcp_tool`.

        Args:
            query: natural-language description of the capability you need
            top_k: max results (default 10)
            proxy: optional filter to a single proxied MCP
        """
        hits = embed_cache.search(query, top_k=top_k, mcp_name=proxy)
        return {
            "query": query,
            "results": [
                {
                    "mcp": rec.mcp_name,
                    "tool": rec.tool_name,
                    "description": rec.description,
                    "score": round(score, 4),
                }
                for rec, score in hits
            ],
        }

    @mcp.tool()
    async def proxy_refresh(name: str) -> dict[str, Any]:
        """Re-embed all tools for a proxy (after upgrading the MCP)."""
        count = await proxy_pool.proxy_refresh_embeddings(name)
        return {"proxy": name, "embedded_tools": count}

    @mcp.tool()
    async def proxy_keepalive(name: str) -> dict[str, Any]:
        """Touch the proxy's last-used timestamp to postpone idle shutdown."""
        conn = proxy_pool._pool.get(name)  # noqa: SLF001
        if conn is None:
            return {"ok": False, "reason": f"proxy {name} not currently connected"}
        conn.touch()
        return {"ok": True, "name": name}

    @mcp.tool()
    async def execute_mcp_tool(
        mcp_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Invoke a tool on a proxied MCP (subprocess).

        Use proxy_tools_search first to discover what is available.
        """
        conn = await proxy_pool.get_mcp_connection(mcp_name)
        if conn is None:
            return {
                "error": {
                    "code": -1,
                    "message": f"proxy '{mcp_name}' not registered. "
                               "Use proxy_add first or check proxy_list.",
                }
            }
        rid = proxy_pool.increment_request_counter()
        response = await conn.call_tool(tool_name, arguments or {}, rid)
        return response


__all__ = ["register"]
