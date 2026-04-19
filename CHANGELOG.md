# Changelog

All notable changes to `jig` are documented in this file. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versioning
adheres to [SemVer](https://semver.org/).

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
