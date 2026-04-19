# Proxy subsystem

jig's reason for existing: one MCP registered in `.mcp.json`, many
MCPs brokered transparently. A proxy is either a **subprocess** (an
external stdio MCP jig spawns on demand) or **internal** (in-process
Python handlers, zero spawn cost).

## Lifecycle

```
proxy_add(name, command, args)
  ├── write config → ~/.config/jig/proxy.toml
  ├── if warmup=True:
  │     spawn subprocess → JSON-RPC initialize → tools/list
  │     embed descriptions → ~/.local/share/jig/tools_<model>.db
  │     keep connection open for 10 min (configurable)
  └── return embedded tool count

proxy_tools_search(query) ──→ reads embed cache, never hits subprocess

execute_mcp_tool(mcp, tool, args)
  ├── if mcp is an internal proxy: dispatch in-process
  ├── else: get/spawn subprocess via proxy_pool
  ├── send JSON-RPC tools/call
  └── return result

idle timer fires (default 600s)
  └── SIGTERM subprocess, release file handles
      (reconnects transparently on next execute)

proxy_remove(name)
  ├── stop subprocess
  ├── DELETE rows from embed cache
  └── remove from proxy.toml
```

## Two kinds of proxies

### Subprocess

The typical case: external MCPs installed on the user's system,
spawned as stdio JSON-RPC children.

```bash
proxy_add(
    name="serena",
    command="npx",
    args=["-y", "@modelcontextprotocol/serena"]
)
```

Persisted in `~/.config/jig/proxy.toml`:

```toml
[proxies.serena]
command = "npx"
args = ["-y", "@modelcontextprotocol/serena"]
idle_timeout_seconds = 600.0
env = {}
```

### Internal

Tools bundled inside jig that should not inflate the top-level MCP
surface. Registered at server startup by `_tool_archive.archive_all`:

```python
from jig.engines import internal_proxy

internal_proxy.register("graph", internal_proxy.InternalHandler(
    name="graph_builder_create",
    description="Create a new graph builder session.",
    input_schema={"type": "object", "properties": {...}},
    fn=_real_implementation,  # sync or async Python callable
))
```

`execute_mcp_tool("graph", "graph_builder_create", ...)` routes to the
callable directly — no subprocess, no RPC, no serialisation overhead
beyond the MCP request itself.

Current internal proxies (total 27 tools archived):

| MCP name | Archived tools |
|----------|----------------|
| `graph` | 18 — `graph_builder_*`, `graph_check_*`, debug/advanced. |
| `experience` | 2 — `experience_list`, `experience_derive_checklist`. |
| `pattern` | 1 — `pattern_catalog_generate`. |
| `metadata` | 1 — `project_metadata_refresh`. |
| `trend` | 2 — `trend_record_snapshot`, `trend_get_data`. |
| `workflow` | 2 — `workflow_set_enabled`, `workflow_set_dcc_injection`. |
| `deploy` | 1 — `deploy_project_agents`. |
| `session` | 1 — `set_session`. |

Internal proxies report as connected, tool_count populated:

```json
{"name": "graph", "connected": true, "tool_count": 18, "kind": "internal"}
```

## Idle timeout

Each subprocess proxy carries an `asyncio.TimerHandle`. Every successful
`execute_mcp_tool` call bumps `last_used` and resets the timer. When
it fires, the subprocess gets SIGTERM and the connection is closed.
The next `execute_mcp_tool` will transparently respawn.

Defaults:

```
idle_timeout_seconds = 600.0    # 10 minutes
```

Extend ad-hoc:

```python
proxy_keepalive(name="serena")  # resets timer
```

Override per-proxy in `proxy.toml`:

```toml
[proxies.heavy-mcp]
command = "..."
idle_timeout_seconds = 1800.0    # 30 min for expensive warm-up
```

## Reconnection

The pool keeps one `Connection` per proxy name. If the subprocess dies
(stale stdio, exits early, OOM), the next call triggers a reconnect:

- `get_mcp_connection(name)` notices the dead pipe, kills residual state.
- Respawns the subprocess.
- Re-initialises the MCP handshake.
- Retries the user's call.

Reconnect failures bubble up as `{"error": {"code": ..., "message": ...}}`
from `execute_mcp_tool`. Use `proxy_reconnect(name)` to force a restart
from the outside.

## Writes vs reads

- **`proxy_tools_search`** never spawns subprocesses. Cache-only.
- **`proxy_list`** doesn't spawn; reports whatever state the pool has.
- **`execute_mcp_tool`** spawns if needed.
- **`proxy_refresh`** spawns to refresh the embed cache after an MCP
  upgrade.

This is deliberate: discovery is cheap so agents can search liberally.
Execution is where cost lives.

## Failure modes

| Symptom | Cause | Remediation |
|---------|-------|-------------|
| `warmup failed: Connection closed` | Subprocess exited before `initialize` | Verify command works standalone: `<command> <args>` should print an MCP server banner. |
| `proxy '<n>' not registered` | Missing `proxy_add` | `proxy_add(...)` first, or check `proxy_list`. |
| Search returns empty for a known proxy | Embed cache empty (warmup disabled or failed) | `proxy_refresh(name)`. |
| Stale search results after upgrading an MCP | `text_hash` unchanged or cache not invalidated | `proxy_refresh(name)` re-embeds everything. |
