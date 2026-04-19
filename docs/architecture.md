# Architecture

## One picture

```
Claude Code
 └── .mcp.json → uvx jig-mcp
       └── jig (FastMCP stdio server)
             ├── 28 surfaced tools        ← loaded into every session
             │     proxy_* / snapshot_* / experience_{record,query,stats}
             │     pattern_catalog_get / project_metadata_get / trend_get_summary
             │     6 hot-path graph_* / deploy helpers / jig_{version,guide}
             │     execute_mcp_tool
             │
             ├── internal proxies         ← on-demand, 0 cost at session start
             │     graph (18)      experience (2)    pattern (1)
             │     metadata (1)    trend (2)         workflow (2)
             │     deploy (1)      session (1)
             │
             └── subprocess proxies       ← stdio child processes, idle-timeout
                   serena · context7 · playwright · sequentialthinking · …
```

Top-level surface stays at 28 tools no matter how many subsystems get added.

## Packages

```
src/jig/
  server.py       FastMCP entry. Registers tools, runs archive pass, starts stdio.
  cli/            `jig serve | init | doctor | --version`
  core/           paths (XDG), embeddings (fastembed), embed_cache (SQLite),
                  snapshots (refs/jig/snapshots), session, storage
  engines/        Pure logic. No MCP coupling. Tested as plain Python.
                  graph_{engine,parser,state}, experience_memory, pattern_catalog,
                  project_metadata, tool_index, trend_tracker, dcc_integration,
                  proxy_pool, hub_config, internal_proxy, dcc/ (vendored).
  tools/          Thin FastMCP registration layer. One module per domain.
  hooks/          Bundled PreToolUse / PostToolUse hooks copied into project
                  .claude/ by `jig init`.
  assets/         Package-data: 19 agents, 26 skills, 23 rules, 5 commands,
                  5 guides, 2 workflow templates, settings template.
  tests/          pytest, 150 tests, no MCP deps (hits engines directly).
```

## Runtime boundaries

- **`engines/` is pure Python.** Enforcers and hooks import from here
  directly — no proxy round-trip for internal callers. Example:
  `workflow_post_traverse.py` calls `dcc_integration.compute_deltas()`
  by plain import, not `execute_mcp_tool("dcc", ...)`.
- **`tools/` is the MCP boundary.** Each `@mcp.tool()` decorator is a
  wrapper that unpacks args, calls into engines, and repackages the
  result. Tools must accept JSON-serialisable arguments and return
  JSON-serialisable output.
- **`internal_proxy`** registers (name, schema, Python callable)
  triples. `execute_mcp_tool` checks it first; miss falls through to
  `proxy_pool` (subprocess).
- **`proxy_pool`** spawns subprocess MCPs lazily on first call. Idle
  subprocesses get killed after 10 minutes (per-proxy override in
  `~/.config/jig/proxy.toml`). Tool descriptions are embedded at
  connect time and cached in `~/.local/share/jig/tools_<model>.db`.

## Data layout

| Path | Purpose | Format |
|------|---------|--------|
| `~/.config/jig/proxy.toml` | User proxy registrations | TOML |
| `~/.local/share/jig/tools_<model>.db` | Semantic search cache | SQLite + blob embeddings |
| `~/.local/share/jig/experience_memory.json` | Cross-project learning | JSON |
| `~/.local/share/jig/project_memories/<name>/` | Per-project memory | JSON |
| `~/.local/share/jig/learned_weights.json` | Tool-ranking adjustments | JSON |
| `$PROJECT/.claude/` | Per-project hooks/rules/commands/workflows | files |
| `$PROJECT/.jig/` | Per-project lockfiles and ephemeral state | files |
| `refs/jig/snapshots/<id>` | Shadow-branch snapshots (git) | orphan commits |

`~/.workflow-manager/` (legacy agentcockpit location) is still read as
a fallback when XDG paths are empty. First write to XDG paths
effectively pins them.

## Startup sequence

1. `jig serve` → `server.serve()`
2. logging to stderr (stdio MCP requires clean stdout)
3. `_register_tools()`:
   - 9 tool modules register their public surfaces
   - `_tool_archive.archive_all()` moves 27 tools to internal proxies
4. Embed warmup scheduled as background task (non-blocking)
5. `mcp.run()` blocks on stdio JSON-RPC loop until client disconnects

## Non-goals

- No daemon, no long-running state server.
- No replacement for Claude Code's LSP, git, or terminal integrations.
- No packaging of other MCPs. They're referenced, not bundled.
