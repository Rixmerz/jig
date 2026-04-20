# jig Methodology

> The canonical way to work inside a jig-scaffolded project. Every
> Claude Code session loaded this rule implicitly via `.claude/rules/`
> after `jig init`.

jig collapses every MCP you have configured into a single server that
exposes ~26 tools at session start. The remaining 30+ operations live
in internal proxies and are discovered on demand via semantic search.
Work the flow the way jig was designed, and you'll see the delta
between "hundreds of schemas" and "the right toolbox per task."

## Core workflow

1. **Discover before you act.** When you need a capability that isn't
   on the surface, call `proxy_tools_search(query="…")` first. It
   reads the embedding cache — no subprocess spawn, no network, no
   cost beyond the query. The top hit's `description` tells you what
   the tool does; don't invent assumptions.

2. **Invoke via `execute_mcp_tool`.** Internal proxies (`graph`,
   `snapshot`, `experience`, `trend`, `pattern`, `metadata`,
   `workflow`, `session`) are in-process Python; subprocess proxies
   spawn on demand and idle out after 10 minutes. Both go through the
   same entry point: `execute_mcp_tool(mcp_name, tool_name, arguments)`.

3. **Let the enforcer talk.** A `graph_activate` workflow can block
   tools (e.g. Edit/Write) until you've called specific others
   (e.g. `graph_traverse` through a "think" phase). If a tool returns
   a block message from the enforcer, read the rationale — don't
   retry the same call. Traverse first.

4. **Snapshots are automatic.** jig drops an orphan commit under
   `refs/jig/snapshots/<id>` after every Edit/Write/Bash cycle
   (30 s throttle). You'll see the changed-file delta injected back
   as context. You do not create snapshots manually; if you ever need
   to roll back, `execute_mcp_tool("snapshot", "snapshot_restore",
   {"snap_id": "…"})`.

5. **DCC smells surface themselves.** When the project has been
   indexed with DeltaCodeCube, the snapshot hook also appends a
   "DCC smells in changed files" block. Treat those as first-class
   signals — if a smell went from none to critical in one edit, pause
   and consider the reason before moving on.

## Surface vs archived

| Layer | What lives there | How to reach it |
|-------|------------------|------------------|
| Surface (26 tools) | hot-path operations: proxy_*, graph_{activate,status,traverse,reset,list_available,timeline}, experience_{record,query,stats}, jig_version, jig_guide, jig_init_project, deploy_project_agents, execute_mcp_tool, … | Call directly by name. |
| Internal proxies | 30+ niche ops: every `graph_builder_*`, `graph_check_*`, `pattern_catalog_generate`, `trend_record_snapshot`, etc. | `proxy_tools_search` → `execute_mcp_tool`. |
| Subprocess proxies | any MCP the user registered with `proxy_add` (Serena, Context7, Playwright, …). | Same path as internal. |

If you're tempted to search PATH for a CLI or shell out to `git` when
jig has a direct tool, stop — use the tool. `graph_timeline` beats
`git log`, `snapshot_restore` beats `git reset`, `experience_query`
beats re-reading old commit messages.

## Good habits

- **Look at `jig_guide(topic=…)` before unfamiliar work.** Topics:
  `getting-started`, `create-workflow`, `proxy-design`, `snapshots`,
  `tensions`. They're short and grounded in the real tool surface.
- **Prefer `experience_query` for "have I seen this before?"** It's
  ranked by semantic relevance to the file path you're touching,
  not by textual match to a commit message.
- **Lean on `project_metadata_get` for scaffolding decisions.** Next
  migration number, bounded contexts, tech stack, test runner — all
  auto-discovered and cached 1 h. Don't re-scan the filesystem.
- **Trust the enforcer.** If it blocks, it's either protecting a
  phase invariant or flagging a tension budget — both are load-
  bearing. Understand why before you work around it.

## Things jig is not

- It is not a daemon. It runs as a stdio MCP spawned by Claude Code.
- It is not a substitute for the terminal, Claude Code's Edit tool,
  or the Grep/Glob built-ins. Those still do what they always did.
- It is not a package manager. `proxy_add` registers an existing
  MCP; it doesn't install one.
