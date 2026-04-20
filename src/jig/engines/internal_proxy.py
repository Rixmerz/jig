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
import json
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


def _coerce_arg(value: Any, schema: dict[str, Any]) -> Any:
    """Best-effort coercion for a single argument against its JSON-schema.

    The MCP protocol passes JSON, but LLMs occasionally serialize list-
    valued args as JSON strings (``"[\\"Edit\\", \\"Write\\"]"``) instead
    of actual JSON arrays. Surface tools are shielded from this by
    FastMCP/pydantic validation at the protocol boundary, but archived
    tools are dispatched by ``handler.fn(**args)`` which runs the raw
    Python function — no validation. Without this coercion a stringified
    list becomes a ``for c in s`` character-by-character iteration,
    producing garbage YAML and silently neutralising enforcement (B2).

    Rules:
    - If schema wants ``array`` and value is a string: try ``json.loads``;
      if the result is a list, use it; otherwise wrap as ``[value]``.
    - If schema wants ``object`` and value is a string: try ``json.loads``;
      if result is a dict, use it; otherwise leave as-is.
    - Everything else: pass through untouched.
    """
    if value is None:
        return None
    # Unwrap anyOf / oneOf unions — pick the first non-null subtype
    sub = schema
    if "anyOf" in schema or "oneOf" in schema:
        for alt in schema.get("anyOf", schema.get("oneOf", [])):
            if alt.get("type") != "null":
                sub = alt
                break
    declared = sub.get("type")
    if declared == "array" and isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return [value]
        if isinstance(parsed, list):
            return parsed
        return [value]
    if declared == "object" and isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return value
        if isinstance(parsed, dict):
            return parsed
        return value
    return value


def _coerce_arguments(
    arguments: dict[str, Any] | None,
    input_schema: dict[str, Any],
) -> dict[str, Any]:
    if not arguments:
        return {}
    props = input_schema.get("properties") or {}
    return {k: _coerce_arg(v, props.get(k, {})) for k, v in arguments.items()}


async def invoke(handler: InternalHandler, arguments: dict[str, Any] | None) -> Any:
    coerced = _coerce_arguments(arguments, handler.input_schema)
    result = handler.fn(**coerced)
    if inspect.isawaitable(result):
        result = await result
    return result
