# jig

**Just-in-time tool discovery and phase-enforced workflows for AI coding agents.**

`jig` is a Python MCP server designed to be the *only* MCP in your `.mcp.json`. It proxies every other MCP you use (Serena, Sequential Thinking, Context7, Playwright, DCC, and so on), surfaces their tools on-demand through semantic search, and enforces disciplined workflows that gate which tools an agent can use in each phase of a task.

## Why

With N MCPs registered in `.mcp.json`, every session starts with ~N×T tool schemas in context. Most go unused. Claude Code loads hundreds of tool definitions before the agent does anything.

`jig` collapses that surface to ~29 tools at session start. The remaining tools from proxied MCPs become discoverable via `proxy_tools_search("find symbol in large codebase")` and callable via `execute_mcp_tool(mcp, tool, args)`. Combined with workflow phase enforcement, agents work with the *right-sized toolbox per task*, not a pantry of everything.

```text
Before: 7 MCPs × ~30 tools = 227 tool schemas at session start (~18K tokens)
After:  1 MCP  × ~29 tools =  29 tool schemas at session start  (~2K tokens)
Reduction: ~89% of per-session tool budget recovered.
```

## Install

```bash
uv tool install jig-mcp        # or: pipx install jig-mcp
jig init /path/to/project      # scaffolds .claude/ + rewrites .mcp.json
```

Zero system dependencies. No Docker, no Ollama, no Node, no Rust. Just Python 3.10+.

## Quickstart

```bash
# 1. Install
uv tool install jig-mcp

# 2. Scaffold a project (scans existing .mcp.json, migrates local MCPs to jig proxy)
jig init ~/my-project

# 3. Open Claude Code at ~/my-project. You'll see ~29 tools instead of hundreds.
#    Try: jig_guide(topic="getting-started")
```

## What jig ships

- **Workflow graphs** — YAML-defined phases with `tools_blocked`, `mcps_enabled`, `tension_gate`, DAG tasks. Agents can't skip the phase you said they must think in.
- **Semantic tool search** — embeds every proxied tool description + input schema once (fastembed + bge-large, 1024D), queryable via `proxy_tools_search`.
- **Shadow-branch snapshots** — `refs/jig/snapshots/<id>`, never pollutes `git tag -l` or `git branch -a`.
- **Experience memory** — cross-project learning from commits, semantic retrieval by file.
- **Code quality gates** — DeltaCodeCube vendored in, smells & tensions block phase transitions.
- **Hooks** — PreToolUse injects memory + experience + smart context. PostToolUse reports DCC deltas, captures lessons, snapshots state.

## What jig is not

- It is not a daemon. It runs as a stdio MCP server on demand.
- It is not a replacement for your code editor, terminal, or git client. It sits behind Claude Code.
- It is not a package manager for MCPs. It proxies them; they must already exist on your system.

## Architecture

```
Claude Code
  └─▶ .mcp.json: { "jig": "uvx jig-mcp" }
        └─▶ jig (FastMCP server)
              ├── graph_*, proxy_*, experience_*, snapshot_*, jig_guide
              └── proxied MCPs (lazy subprocess, idle-timeout)
                    ├── serena
                    ├── sequentialthinking
                    ├── context7
                    └── ... etc
```

See [`docs/architecture.md`](docs/architecture.md) for subsystem details.

## Status

**Alpha (v0.0.1).** Under active development. API surface is subject to change before 0.1.0.

## License

MIT — see [`LICENSE`](LICENSE).
