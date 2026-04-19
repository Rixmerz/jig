"""MCP proxy pool.

Lazy subprocess-per-MCP JSON-RPC stdio connections with idle timeout, reconnect
on stale stdio, and automatic tool-description embedding at connect time.

This module replaces `mcp_connection.py` from workflow-manager. The public
`get_mcp_connection` and `increment_request_counter` helpers keep the same
signatures so `dcc_integration.py` and other callers work unchanged.

Config sources (in precedence order):
    1. Proxy registrations made at runtime via `proxy_add` (persisted to
       ~/.config/jig/proxy.toml)
    2. Legacy MCP configs from `hub_config.load_mcp_configs()` (agentcockpit
       compatibility — will be deprecated once the init migration is universal)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from jig.core import paths
from jig.core.embed_cache import remove_mcp, upsert_tools

try:  # tomllib available 3.11+; tomli fallback if older
    import tomllib  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

log = logging.getLogger(__name__)

_SLOW_TOOLS: frozenset[str] = frozenset({
    "cube_generate_timeline", "cube_generate_heatmap", "cube_generate_architecture",
    "cube_generate_matrix", "cube_export_html", "cube_get_temporal_features",
    "cube_simulate_wave", "cube_get_deltas", "cube_detect_clones",
    "cube_analyze_graph", "cube_cluster_files",
})

DEFAULT_IDLE_TIMEOUT = 600.0  # 10 minutes


@dataclass(slots=True)
class ProxyConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    idle_timeout_seconds: float = DEFAULT_IDLE_TIMEOUT


# ---------------------------------------------------------------------------
# Config I/O
# ---------------------------------------------------------------------------

def proxy_config_path() -> "paths.Path":
    return paths.ensure(paths.config_dir()) / "proxy.toml"


def load_proxy_configs() -> dict[str, ProxyConfig]:
    """Load proxy definitions from ~/.config/jig/proxy.toml."""
    path = proxy_config_path()
    if not path.exists():
        return {}
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except Exception as e:  # pragma: no cover
        log.warning("[jig.proxy] failed to parse %s: %s", path, e)
        return {}

    configs: dict[str, ProxyConfig] = {}
    proxies = data.get("proxies", {})
    if not isinstance(proxies, dict):
        return configs
    for name, spec in proxies.items():
        if not isinstance(spec, dict):
            continue
        configs[name] = ProxyConfig(
            name=name,
            command=str(spec.get("command", "")),
            args=list(spec.get("args", [])),
            env={str(k): str(v) for k, v in dict(spec.get("env", {})).items()},
            idle_timeout_seconds=float(
                spec.get("idle_timeout_seconds", DEFAULT_IDLE_TIMEOUT)
            ),
        )
    return configs


def save_proxy_configs(configs: dict[str, ProxyConfig]) -> None:
    """Write proxy definitions to ~/.config/jig/proxy.toml (TOML by hand)."""
    path = proxy_config_path()
    lines: list[str] = [
        "# jig proxy configuration — managed by proxy_add / proxy_remove",
        "",
    ]
    for name in sorted(configs):
        cfg = configs[name]
        lines.append(f"[proxies.{name}]")
        lines.append(f'command = "{_toml_escape(cfg.command)}"')
        if cfg.args:
            args_repr = ", ".join(f'"{_toml_escape(a)}"' for a in cfg.args)
            lines.append(f"args = [{args_repr}]")
        if cfg.env:
            lines.append("env = {" + ", ".join(
                f'{k} = "{_toml_escape(v)}"' for k, v in cfg.env.items()
            ) + "}")
        if cfg.idle_timeout_seconds != DEFAULT_IDLE_TIMEOUT:
            lines.append(f"idle_timeout_seconds = {cfg.idle_timeout_seconds}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _toml_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ProxyStatus:
    name: str
    connected: bool
    tool_count: int
    last_error: str | None = None
    last_used: float = 0.0


class McpConnection:
    """MCP subprocess connection with idle auto-stop + init handshake.

    Drop-in compatible with workflow-manager's `McpConnection`: exposes `name`,
    `start`, `call_tool`, `stop`, plus new `list_tools`, `touch`, `is_alive`.
    """

    def __init__(self, cfg: ProxyConfig) -> None:
        self.name = cfg.name
        self.command = cfg.command
        self.args = cfg.args
        self.env = cfg.env
        self.idle_timeout_seconds = cfg.idle_timeout_seconds

        self.process: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._initialized = False
        self._init_request_id = 0
        self._last_used = time.monotonic()
        self._idle_task: asyncio.Task[None] | None = None
        self.last_error: str | None = None

    # --- subprocess lifecycle --------------------------------------------------

    def is_alive(self) -> bool:
        return self.process is not None and self.process.returncode is None

    def touch(self) -> None:
        self._last_used = time.monotonic()

    async def start(self) -> None:
        if self.is_alive():
            return

        full_env = os.environ.copy()
        full_env.update(self.env)
        try:
            self.process = await asyncio.create_subprocess_exec(
                self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=full_env,
            )
        except FileNotFoundError as e:
            self.last_error = f"command not found: {self.command}"
            raise RuntimeError(self.last_error) from e
        self._initialized = False
        self._last_used = time.monotonic()
        self._start_idle_watcher()

    async def stop(self) -> None:
        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()
        if self.is_alive():
            assert self.process is not None
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()

    def _start_idle_watcher(self) -> None:
        if self.idle_timeout_seconds <= 0:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # pragma: no cover
            return
        if self._idle_task and not self._idle_task.done():
            return
        self._idle_task = loop.create_task(self._idle_loop())

    async def _idle_loop(self) -> None:
        try:
            while self.is_alive():
                await asyncio.sleep(max(10.0, self.idle_timeout_seconds / 4))
                idle = time.monotonic() - self._last_used
                if idle >= self.idle_timeout_seconds:
                    log.info(
                        "[jig.proxy] stopping idle proxy %s (idle=%.1fs)",
                        self.name,
                        idle,
                    )
                    await self.stop()
                    return
        except asyncio.CancelledError:
            return

    # --- MCP JSON-RPC ----------------------------------------------------------

    async def _send(self, msg: dict[str, Any]) -> None:
        assert self.process is not None and self.process.stdin is not None
        self.process.stdin.write(json.dumps(msg).encode("utf-8") + b"\n")
        await self.process.stdin.drain()

    async def _recv(self, timeout: float = 120.0) -> dict[str, Any]:
        assert self.process is not None and self.process.stdout is not None
        while True:
            line = await asyncio.wait_for(
                self.process.stdout.readline(), timeout=timeout
            )
            if not line:
                raise RuntimeError("Connection closed")
            decoded = line.decode("utf-8", errors="replace").strip()
            if not decoded:
                continue
            try:
                return json.loads(decoded)
            except json.JSONDecodeError:
                continue

    async def _initialize(self) -> None:
        if self._initialized:
            return
        self._init_request_id += 1
        await self._send({
            "jsonrpc": "2.0",
            "id": self._init_request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "clientInfo": {"name": "jig", "version": "0.0.1"},
            },
        })
        init_response: dict[str, Any] | None = None
        for _ in range(10):
            msg = await self._recv(timeout=30.0)
            if msg.get("id") == self._init_request_id:
                init_response = msg
                break
        if init_response is None:
            raise RuntimeError("no initialize response")
        if "error" in init_response:
            raise RuntimeError(f"initialize failed: {init_response['error']}")
        await self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        await asyncio.sleep(0.1)
        self._initialized = True

    async def list_tools(self) -> list[dict[str, Any]]:
        """Query tools/list. Returns empty list on failure."""
        async with self._lock:
            if not self.is_alive():
                await self.start()
            if not self._initialized:
                await self._initialize()
            self.touch()
            self._init_request_id += 1
            rid = self._init_request_id
            await self._send({
                "jsonrpc": "2.0",
                "id": rid,
                "method": "tools/list",
                "params": {},
            })
            for _ in range(20):
                msg = await self._recv(timeout=15.0)
                if msg.get("id") == rid:
                    result = msg.get("result", {})
                    if isinstance(result, dict):
                        return list(result.get("tools", []))
                    return []
        return []

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        request_id: int,
    ) -> dict[str, Any]:
        async with self._lock:
            if not self.is_alive():
                await self.start()
            if not self._initialized:
                try:
                    await self._initialize()
                except Exception as e:
                    return {"error": {"code": -1, "message": f"init failed: {e}"}}
            self.touch()
            timeout = 360.0 if tool_name in _SLOW_TOOLS else 120.0
            try:
                await self._send({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": arguments},
                })
                return await self._recv(timeout=timeout)
            except asyncio.TimeoutError:
                return {
                    "error": {
                        "code": -1,
                        "message": f"timeout after {int(timeout)}s on {self.name}.{tool_name}",
                    },
                }
            except RuntimeError as e:
                return {"error": {"code": -1, "message": str(e)}}


# ---------------------------------------------------------------------------
# Module-level pool + public helpers (drop-in compat with workflow-manager)
# ---------------------------------------------------------------------------

_pool: dict[str, McpConnection] = {}
_request_counter = 0


def _resolve_config(mcp_name: str) -> ProxyConfig | None:
    configs = load_proxy_configs()
    if mcp_name in configs:
        return configs[mcp_name]
    # Legacy fallback via hub_config (agentcockpit MCPs)
    try:
        from jig.engines.hub_config import load_mcp_configs

        legacy = load_mcp_configs()
        raw = legacy.get(mcp_name)
        if raw and raw.get("command"):
            return ProxyConfig(
                name=mcp_name,
                command=str(raw["command"]),
                args=list(raw.get("args", [])),
                env={str(k): str(v) for k, v in dict(raw.get("env", {})).items()},
            )
    except Exception:
        pass
    return None


async def get_mcp_connection(mcp_name: str) -> McpConnection | None:
    """Get or create a pooled connection. Returns None if no config exists."""
    conn = _pool.get(mcp_name)
    if conn is not None:
        return conn
    cfg = _resolve_config(mcp_name)
    if cfg is None:
        return None
    conn = McpConnection(cfg)
    _pool[mcp_name] = conn
    return conn


async def close_all_connections() -> list[str]:
    closed: list[str] = []
    for name, conn in list(_pool.items()):
        try:
            await conn.stop()
            closed.append(name)
        except Exception as e:
            print(f"[jig.proxy] warning closing {name}: {e}", file=sys.stderr)
    _pool.clear()
    return closed


def get_request_counter() -> int:
    return _request_counter


def increment_request_counter() -> int:
    global _request_counter
    _request_counter += 1
    return _request_counter


# ---------------------------------------------------------------------------
# Proxy management (backing for tools/proxy.py)
# ---------------------------------------------------------------------------

async def proxy_register(
    name: str,
    command: str,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    idle_timeout_seconds: float = DEFAULT_IDLE_TIMEOUT,
) -> None:
    configs = load_proxy_configs()
    configs[name] = ProxyConfig(
        name=name,
        command=command,
        args=list(args or []),
        env=dict(env or {}),
        idle_timeout_seconds=idle_timeout_seconds,
    )
    save_proxy_configs(configs)


async def proxy_unregister(name: str) -> bool:
    configs = load_proxy_configs()
    if name not in configs:
        return False
    del configs[name]
    save_proxy_configs(configs)
    remove_mcp(name)
    conn = _pool.pop(name, None)
    if conn:
        await conn.stop()
    return True


async def proxy_refresh_embeddings(name: str) -> int:
    """(Re)embed all tools for this proxy. Returns count embedded."""
    conn = await get_mcp_connection(name)
    if conn is None:
        return 0
    tools = await conn.list_tools()
    if not tools:
        return 0
    return upsert_tools(name, tools)


async def proxy_reconnect(name: str) -> bool:
    conn = _pool.get(name)
    if conn is None:
        return False
    await conn.stop()
    await conn.start()
    await conn._initialize()  # noqa: SLF001 — intentional
    return True


async def proxy_statuses() -> list[ProxyStatus]:
    configs = load_proxy_configs()
    # Include legacy configs too, read-only visibility
    try:
        from jig.engines.hub_config import load_mcp_configs
        for name, raw in load_mcp_configs().items():
            if name not in configs and raw.get("command"):
                configs[name] = ProxyConfig(
                    name=name,
                    command=str(raw["command"]),
                    args=list(raw.get("args", [])),
                    env={str(k): str(v) for k, v in dict(raw.get("env", {})).items()},
                )
    except Exception:
        pass

    from jig.core.embed_cache import list_tools as _list_tools

    out: list[ProxyStatus] = []
    for name, _cfg in configs.items():
        conn = _pool.get(name)
        connected = conn.is_alive() if conn else False
        tool_count = len(_list_tools(mcp_name=name))
        out.append(ProxyStatus(
            name=name,
            connected=connected,
            tool_count=tool_count,
            last_error=(conn.last_error if conn else None),
            last_used=(conn._last_used if conn else 0.0),  # noqa: SLF001
        ))
    return out


__all__ = [
    "DEFAULT_IDLE_TIMEOUT",
    "McpConnection",
    "ProxyConfig",
    "ProxyStatus",
    "close_all_connections",
    "get_mcp_connection",
    "get_request_counter",
    "increment_request_counter",
    "load_proxy_configs",
    "proxy_config_path",
    "proxy_reconnect",
    "proxy_refresh_embeddings",
    "proxy_register",
    "proxy_statuses",
    "proxy_unregister",
    "save_proxy_configs",
]
