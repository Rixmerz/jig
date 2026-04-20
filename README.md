# jig

**Just-in-time tool discovery and phase-enforced workflows for AI coding agents.**

`jig` is a Python MCP server designed to be the *only* MCP in your
`.mcp.json`. It proxies every other MCP you use (Serena, Sequential
Thinking, Context7, Playwright, and so on), exposes a small surface
of hot-path tools to every session, and pushes everything else
(30+ operations across eight internal domains: graph, snapshot,
experience, trend, pattern, metadata, workflow, session) into
on-demand internal proxies reachable via semantic search. Combined
with workflow phase enforcement and automatic shadow-branch
snapshots, agents work with the *right-sized toolbox per task*, not
a pantry of everything.

## Why

With N MCPs registered in `.mcp.json`, every Claude Code session starts
with ~N×T tool schemas in context. Most go unused.

`jig` collapses that surface to **26 tools** at session start. The rest
(of both jig's own domains and any MCP you've added via `proxy_add`)
becomes discoverable through `proxy_tools_search(query="…")` and
callable via `execute_mcp_tool(mcp, tool, args)`.

```text
Before: 7 MCPs × ~30 tools = 210 tool schemas at session start (~17K tokens)
After:  1 MCP  × 26 tools  =  26 tool schemas at session start (~2K tokens)
Reduction: ~88% of per-session tool budget recovered.
```

## Install

```bash
# Recommended — persistent binary, lock-free between concurrent sessions
uv tool install git+https://github.com/Rixmerz/jig

# Scaffold a project
jig init /path/to/project
```

Zero system dependencies. No Docker, no Ollama, no Node, no Rust. Just
Python 3.10+ and git.

Once `jig-mcp` is published on PyPI, drop the `git+https://…` bit:
`uv tool install jig-mcp`.

## Quickstart

`jig` is designed to be driven from inside the chat. The whole
project-kickoff flow is two MCP tool calls:

```python
# Phase 0 — scaffold the base layer. Copies hooks, commands, workflows,
# 10 universal rules (including jig-methodology), and settings.json.
# Migrates any local MCPs from .mcp.json into jig's proxy pool.
jig_init_project(project_path="/path/to/project")

# Phase 1 — tailor the project to its stack. Deploys core agents
# (orchestrator, debugger, reviewer, tester) + specialized ones based on
# the stack, injects skills, and adds stack-specific watcher rules
# (python.md, typescript.md, rust.md, ui.md, …).
deploy_project_agents(
    project_path="/path/to/project",
    tech_stack=["python", "react"],
)
```

Both tools are on the top-level surface; no `execute_mcp_tool`
indirection. `jig_init_project` returns a `next_step` pointer so the
agent knows where to go next.

You can still run the same flow from a shell:

```bash
jig init ~/my-project                # phase 0
# then, inside Claude Code:
deploy_project_agents(...)           # phase 1
```

### Rendered `.mcp.json`

`jig init` auto-detects how jig is installed. When `jig-mcp` is on
`PATH` (from `uv tool install`), it picks the zero-overhead form:

```json
{
  "mcpServers": {
    "jig": {"command": "jig-mcp"}
  }
}
```

No `uvx` rebuild per spawn, no cache-lock contention between concurrent
Claude Code sessions. Upgrade in place with `uv tool upgrade jig-mcp`;
the `.mcp.json` never changes.

## What jig ships

- **Two-phase lifecycle tools** — `jig_init_project` (phase 0,
  scaffold) + `deploy_project_agents` (phase 1, tailor to stack). Both
  top-level, agent-driven, no CLI shell-out required.
- **~26 top-level tools** — the hot path: `proxy_*` (add/list/search/
  execute/…), `graph_{activate,status,traverse,reset,list_available,
  timeline}`, `experience_{record,query,stats}`,
  `pattern_catalog_get`, `project_metadata_get`, `trend_get_summary`,
  `jig_{version,guide,init_project}`, `deploy_project_agents`,
  `list_available_agents_and_skills`, `execute_mcp_tool`.
- **Eight internal proxies** — archive the other 30+ operations
  (`graph_builder_*`, `graph_check_*`, `snapshot_*`,
  `experience_{list,derive_checklist}`, `pattern_catalog_generate`,
  `project_metadata_refresh`, `trend_{record_snapshot,get_data}`,
  `workflow_set_*`, `set_session`). Dispatch is in-process Python;
  zero subprocess, zero RPC overhead.
- **Semantic tool search** — every tool description + schema (internal
  and subprocess proxies alike) is embedded once into a SQLite cache
  at `~/.local/share/jig/tools_<model>.db` using fastembed +
  `BAAI/bge-large-en-v1.5` (1024D). `proxy_tools_search` is a pure
  lookup. Override the model with `JIG_EMBED_MODEL`.
- **Shadow-branch snapshots** — `refs/jig/snapshots/<id>` orphan
  commits, captured automatically by hooks on every `Edit` / `Write` /
  `Bash` (30 s throttle). The hook emits the `git diff --name-status`
  against the previous snapshot as PostToolUse `additionalContext` and,
  when DCC has been indexed, appends the top-5 code smells touching
  the changed files. Refs never pollute `git tag -l` or `git branch -a`.
- **19 agents, 26 skills, 23 rules, 5 commands, 2 workflows** — all
  bundled in the wheel. `deploy_project_agents` picks the relevant
  subset based on tech stack and writes them into `.claude/`.
  `jig-methodology` ships as both a rule (always present in
  `.claude/rules/`) and a skill (injected into every deployed agent)
  so every agent knows how to use jig before it touches the stack.
- **Workflow phase gates** — YAML graphs with `tools_blocked`,
  `mcps_enabled`, and `tension_gate` keep agents from skipping the
  phase you said they must think in.
- **Hooks** — PreToolUse injects memory + experience + smart context.
  PostToolUse reports DCC deltas, captures lessons, snapshots state.

## What jig is not

- Not a daemon. It runs as a stdio MCP server on demand.
- Not a replacement for your code editor, terminal, or git client. It
  sits behind Claude Code.
- Not a package manager for MCPs. It proxies them; they must already
  exist on your system.
- Not opinionated about which MCPs you add. Ship Serena or don't;
  both are the user's call.

## Architecture

```
Claude Code
 └── .mcp.json → jig-mcp (bare command, tool-installed)
       └── jig (FastMCP stdio)
             │
             ├── 26 top-level tools (loaded into every session)
             │
             ├── 8 internal proxies (in-process Python, zero spawn)
             │   graph(18) snapshot(4) experience(2) trend(2)
             │   pattern(1) metadata(1) workflow(2) session(1)
             │
             └── subprocess proxies (stdio child processes, idle-timeout)
                   registered via proxy_add: serena, context7,
                   sequentialthinking, playwright, …
```

See [`docs/architecture.md`](docs/architecture.md) for subsystem
details; [`docs/tools.md`](docs/tools.md) for the full tool reference;
[`docs/init.md`](docs/init.md) for `jig init` mechanics and the
`--source` flag; [`docs/proxy.md`](docs/proxy.md) for proxy lifecycle;
[`docs/embeddings.md`](docs/embeddings.md) for the search model.

## Status

**Alpha (0.1.0a17).** All 150 tests green. Fresh-VM E2E validated
(see [`scripts/fresh-vm-e2e.sh`](scripts/fresh-vm-e2e.sh)). API
surface is subject to change before `0.1.0` stable. Next milestone is
PyPI publish; see [`ROADMAP.md`](ROADMAP.md).

## License

MIT — see [`LICENSE`](LICENSE).
