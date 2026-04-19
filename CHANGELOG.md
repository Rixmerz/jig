# Changelog

All notable changes to `jig` are documented in this file. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versioning
adheres to [SemVer](https://semver.org/).

## [0.1.0a7] — 2026-04-19

### Changed
- Generalize the internal-proxy archive pattern beyond graph. A single
  pass in `server._register_tools` (via `tools/_tool_archive.py`) moves
  tools listed in `ARCHIVE_MAP` to their domain's internal proxy:
  - `experience`: `experience_list`, `experience_derive_checklist`
  - `pattern`: `pattern_catalog_generate`
  - `metadata`: `project_metadata_refresh`
  - `trend`: `trend_record_snapshot`, `trend_get_data`
  - `workflow`: `workflow_set_enabled`, `workflow_set_dcc_injection`
  - `deploy`: `deploy_project_agents`
  - `session`: `set_session`
- The per-graph splitter (`_graph_split.py`) is gone; its 18 tools are
  now part of `ARCHIVE_MAP["graph"]`. Replaced by `_tool_archive.py`.
- Tool count on jig's top-level surface drops from 38 to **29**, hitting
  the original plan's target. All archived tools remain callable via
  `execute_mcp_tool("<domain>", "<tool>", {...})` and discoverable via
  `proxy_tools_search`.

## [0.1.0a6] — 2026-04-19

### Added
- `engines/internal_proxy.py`: in-process handler registry for tools
  archived off jig's top-level MCP surface. Dispatch happens directly
  in Python — no subprocess, no JSON-RPC. Descriptions go into the
  embed cache at registration so `proxy_tools_search` finds them.
- `execute_mcp_tool` now routes to internal handlers when the proxy
  is registered internal; subprocess path unchanged for external MCPs.
- `proxy_list` reports internal proxies as always-connected with a
  `kind: "internal"` field alongside subprocess ones.

### Changed
- 18 of 24 `graph_*` tools archived to the internal proxy named `graph`.
  Top-level surface keeps the hot path: `graph_activate`,
  `graph_status`, `graph_traverse`, `graph_reset`,
  `graph_list_available`, `graph_timeline`. The rest
  (`graph_builder_*`, `graph_check_*`, `graph_mid_phase_dcc`,
  `graph_override_max_visits`, `graph_record_output`, `graph_set_node`,
  `graph_visualize`, `graph_validate`, `graph_acknowledge_tensions`,
  `graph_get_ready_tasks`, `graph_task_complete`) are reachable via
  `execute_mcp_tool("graph", "<name>", {...})` and discoverable via
  `proxy_tools_search`. Tool count drops from 56 to 38.

## [0.1.0a5] — 2026-04-19

### Fixed
- `experience_memory`: primary storage moved to XDG
  (`~/.local/share/jig/experience_memory.json`,
  `~/.local/share/jig/project_memories/`). Legacy
  `~/.workflow-manager/` is still read as a fallback when the XDG
  files don't exist, so existing entries from the agentcockpit era
  remain visible until a manual migration.
- `tool_index.LEARNED_WEIGHTS_FILE`: same XDG + legacy-fallback pattern.
- `list_available_agents_and_skills` and `deploy_project_agents`
  now read bundled agents/skills/rules from `jig.assets` via
  `importlib.resources` when the hub dir is empty. No more
  `[Errno 2] No such file or directory` on fresh installs.

## [0.1.0a4] — 2026-04-19

### Added
- Register six previously orphaned tool modules at server startup:
  `experience_*`, `pattern_*`, `project_metadata`, `trend_report`,
  `jig_deploy_agents`, `jig_config`. Total tool count climbs from 39
  to ~48.

### Fixed
- `hub_config.load_hub_config` no longer raises when
  `~/.agentcockpit/config.json` is absent. jig now falls back to XDG
  defaults (`hub_dir=~/.local/share/jig`, `workflows_dir=workflows`,
  `states_dir=states`), and `graph_list_available` returns an empty
  list instead of crashing. The legacy agentcockpit file is still
  honored if present so users migrating from agentcockpit keep their
  hub layout.

## [0.1.0a3] — 2026-04-19

### Fixed
- `tools.graph.register_all` iterated submodules looking for a
  `register_tools` attribute that never existed — the real functions
  are `register_graph_core_tools`, `register_graph_management_tools`,
  `register_graph_builder_tools`. `getattr(..., None)` returned None
  for all three, silently skipping every graph tool. Now calls each
  submodule's registrar by its actual name. Pairs with the 0.1.0a2
  import fix; both were needed to surface the 14 missing tools.

## [0.1.0a2] — 2026-04-19

### Fixed
- `tools/*` modules imported engine modules at `jig.X` (pre-port
  location) instead of `jig.engines.X`, silently dropping 14 tools
  (`graph_*`, `experience_*`, `pattern_*`, `trend_*`, `project_metadata`,
  `jig_deploy_agents`, `jig_config`) at server startup. Sessions saw 15
  tools instead of the expected 29. All top-level and inline imports
  across `_graph_builder`, `_graph_core`, `_graph_management`, `config`,
  `deployment`, `experience`, `metadata`, `patterns`, `trends` corrected.

## [0.1.0a1] — 2026-04-19

First alpha. End-to-end compressed sprint pass from the agentcockpit rewrite.

### Added
- Repository bootstrap: `pyproject.toml` (hatchling, name=jig-mcp), CI workflows (test matrix + trusted PyPI release), pre-commit (ruff + mypy), smoke tests.
- CLI skeleton with `serve`, `init <path>`, `doctor`, `--version`.
- FastMCP server wired to all tool modules.
- Vendored DeltaCodeCube (45 modules, 516KB) at `src/jig/engines/dcc/` with imports rewritten to `jig.engines.dcc.*`.
- Ported 11 workflow-manager engines: `graph_engine`, `graph_parser`, `graph_state`, `hub_config`, `experience_memory`, `pattern_catalog`, `project_metadata`, `tool_index`, `trend_tracker`, `dcc_integration`, plus `session` under `core/`.
- Ported 10 hooks from `.hub/` (canonical) + `.claude/` (legacy workflow-specific); `rules_checker.py` renamed to `style_guard.py`.
- Bundled 26 skills, 23 rules, 5 commands, 19 agents, 2 workflows as package data.
- `core/embeddings.py`: fastembed singleton client (`BAAI/bge-large-en-v1.5`, 1024D, `JIG_EMBED_MODEL` override). Ollama dropped.
- `core/embed_cache.py`: SQLite cache versioned by model slug (`tools_<slug>.db`).
- `engines/proxy_pool.py`: lazy subprocess pool with idle timeout, reconnect, per-proxy config.
- 8 proxy management tools + `execute_mcp_tool` (in `tools/proxy.py`).
- `core/snapshots.py` + `tools/snapshot.py`: shadow-branch snapshots under `refs/jig/snapshots/<id>`; no pollution of user git namespace.
- `hooks/snapshot_trigger.py`: PostToolUse Bash hook with 30s lockfile throttle.
- `cli/init_cmd.py`: scan `.mcp.json`, classify local vs remote, migrate locals to proxy, copy hooks/rules/commands/workflows to `.claude/`, render canonical hook pipeline template, warm up embeddings, print before/after token economy report.
- `tools/guide.py`: `jig_guide(topic)` serves bundled markdown via `importlib.resources`.
- 5 authored guides: getting-started, create-workflow (method), proxy-design, snapshots, tensions.
- `assets/workflows/demo-feature.yaml`: tutorial-executable 4-phase workflow with inline comments.
- `cli/doctor.py`: diagnostics for Python, fastembed, paths, cache, proxy config, git.

### Changed
- Embedding dimension convention: 1024D via bge-large (was 768D via nomic-embed on Ollama).
- Snapshot storage: shadow refs (was git tags — polluted user namespace).
- `rules_checker.py` → `style_guard.py`.
- `mcp_connection.py` → `engines/proxy_pool.py` (drop-in compatible, plus idle timeout + reconnect + tool embedding).

### Removed
- Ollama runtime dependency.
- `hub_sync.py` hook (obsolete once jig is the distribution unit).
- Desktop app entirely (Rust/Tauri/React codebase stays in agentcockpit, archived).

## [0.0.1] — 2026-04-19

Initial repository skeleton.
