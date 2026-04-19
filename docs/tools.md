# Tool reference

jig ships **28 tools on the MCP surface** plus **27 archived** behind
internal proxies (invoked through `execute_mcp_tool`). Total: 55
callable operations, exposed in 28 schemas at session start.

## Surface (28)

### Meta (2)

| Tool | Purpose |
|------|---------|
| `jig_version` | Installed version string. |
| `jig_guide(topic)` | Serves bundled docs. `topic=""` lists the set; topics: `getting-started`, `create-workflow`, `proxy-design`, `snapshots`, `tensions`. |

### Execute (1)

| Tool | Purpose |
|------|---------|
| `execute_mcp_tool(mcp_name, tool_name, arguments)` | Dispatches to internal proxies (in-process) or subprocess proxies (stdio). Use `proxy_tools_search` first to find the right tool. |

### Proxy management (8)

`proxy_add`, `proxy_remove`, `proxy_reconnect`, `proxy_list`,
`proxy_list_tools`, `proxy_tools_search`, `proxy_refresh`,
`proxy_keepalive`. See [`proxy.md`](proxy.md) for the lifecycle model.

### Snapshot (4)

`snapshot_create`, `snapshot_list`, `snapshot_diff`, `snapshot_restore`.
See [`snapshots`](../src/jig/assets/guides/snapshots.md) guide.

### Graph hot path (6)

| Tool | Purpose |
|------|---------|
| `graph_activate` | Load a workflow YAML into state. |
| `graph_status` | Current node, available edges, visit counts. |
| `graph_traverse` | Move to the next node. |
| `graph_reset` | Clear the active graph. |
| `graph_list_available` | Enumerate workflow YAMLs under the hub. |
| `graph_timeline` | Unified timeline of transitions + DCC tensions + git commits. |

Everything else (`graph_builder_*`, `graph_validate`, `graph_visualize`,
etc.) is archived under the `graph` internal proxy — 18 more tools
callable via `execute_mcp_tool("graph", "<name>", {...})`.

### Experience (3 surfaced of 5)

| Tool | Purpose |
|------|---------|
| `experience_record` | Append an experience entry (auto-called by hooks). |
| `experience_query` | Relevance-ranked retrieval, can filter by file/path. |
| `experience_stats` | Counts and confidence distribution. |

Archived: `experience_list`, `experience_derive_checklist`.

### Pattern / Metadata / Trend (4 surfaced of 8)

| Tool | Purpose |
|------|---------|
| `pattern_catalog_get(path)` | Retrieve catalog entries for a path. |
| `project_metadata_get(section?)` | Auto-discovered project facts (migrations, tech stack, bounded contexts). |
| `trend_get_summary(days)` | `"Smells: 50→42, Debt: 45→38"` compact string. |
| `list_available_agents_and_skills` | Catalog of 19 agents + 26 skills bundled in the wheel. |

Archived: `pattern_catalog_generate`, `project_metadata_refresh`,
`trend_record_snapshot`, `trend_get_data`, `deploy_project_agents`,
`workflow_set_enabled`, `workflow_set_dcc_injection`, `set_session`.

## Invoking archived tools

```python
# Discover
proxy_tools_search(query="create a graph builder")
# → ranks graph_builder_create, graph_builder_preview, graph_builder_list

# Invoke
execute_mcp_tool(
    mcp_name="graph",
    tool_name="graph_builder_create",
    arguments={"name": "my-workflow", "builder_id": "wf-001"}
)
```

The internal-proxy path is in-process (no subprocess) so latency is
negligible. `proxy_list` reports each internal MCP with
`"kind": "internal"` and `"connected": true`.

## Adding a tool to the surface / archive

- **Add to surface:** register with `@mcp.tool()` in one of the
  `tools/*.py` modules. Make sure the module's registrar is called
  from `server._register_tools()`.
- **Archive it:** add its name to the right bucket in
  `ARCHIVE_MAP` inside `src/jig/tools/_tool_archive.py`. The post-
  registration pass will move it to the internal proxy automatically.
- **Remove entirely:** delete the registration. Internal callers (hooks)
  that import the function directly are unaffected.

## Versioning

Breaking changes to tool signatures bump the minor version. Renames
are accompanied by a deprecation period when the old name is worth
keeping.
