"""In-process proxy registry for tools bundled inside jig.

Used to archive tools off jig's top-level MCP surface while keeping them
discoverable via `proxy_tools_search` and callable via `execute_mcp_tool`.

Pattern (same shape as subprocess proxies, different dispatch path):

    from jig.engines import internal_proxy
    internal_proxy.register("graph", InternalHandler(
        name="graph_builder_create",
        description="...",
        input_schema={...},
        fn=_graph_builder_create_impl,  # sync or async callable
    ))

Lookup by ``execute_mcp_tool`` short-circuits to the Python callable, no
subprocess, no JSON-RPC, no embedding search. Descriptions are still
written to the embed cache at registration time so semantic search can
find them.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class InternalHandler:
    name: str
    description: str
    input_schema: dict[str, Any]
    fn: Callable[..., Any]


_REGISTRY: dict[str, dict[str, InternalHandler]] = {}


def register(mcp_name: str, handler: InternalHandler) -> None:
    _REGISTRY.setdefault(mcp_name, {})[handler.name] = handler


def get(mcp_name: str, tool_name: str) -> InternalHandler | None:
    return _REGISTRY.get(mcp_name, {}).get(tool_name)


def has_mcp(mcp_name: str) -> bool:
    return mcp_name in _REGISTRY


def list_mcps() -> list[str]:
    return list(_REGISTRY.keys())


def list_tools(mcp_name: str) -> list[InternalHandler]:
    return list(_REGISTRY.get(mcp_name, {}).values())


async def invoke(handler: InternalHandler, arguments: dict[str, Any] | None) -> Any:
    result = handler.fn(**(arguments or {}))
    if inspect.isawaitable(result):
        result = await result
    return result
