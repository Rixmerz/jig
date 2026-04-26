---
name: sprint
description: Create a wave-based workflow graph for a multi-domain task and orchestrate parallel subagents. Use for any task with 3+ distinct phases or that crosses backend + frontend + tests. Reads `next_task_get` for continuity context. For single-scope tasks use /task-with-jig.
disable-model-invocation: true
argument-hint: "[sprint description]"
---

Create a sprint workflow for: **$ARGUMENTS**

You are the orchestrator. You do NOT implement code yourself. You build a graph, delegate each wave to subagents, and verify before advancing.

## Step 0 — Continuity hand-off

Call `next_task_get`. If `found: true`, read the `injection` block — it's the summary of the user's previous task, preserved across `/clear`. Use it to inform scope decisions (don't redo work that's already done; align with prior choices).

## Step 1 — Plan the waves

Analyze the task and identify all deliverables. Group them into dependency-based waves:

- **Wave 1 (Foundation)**: Domain models, database migrations, core types — no external dependencies
- **Wave 2 (Backend)**: Handlers, endpoints, wiring — depends on Wave 1
- **Wave 3 (Frontend)**: UI components, pages, hooks — depends on Wave 2 API
- **Wave 4 (Tests)**: Unit and integration tests — depends on implementation
- **Validate**: Build checks, test suites, architecture review — depends on all waves
- **Docs**: Status updates, changelogs, README — depends on validation

Skip waves that don't apply. Documentation-only sprints, for example, may be Research → Drafting → Verify with no Backend/Frontend split.

## Step 2 — Build the graph (via jig's internal proxy)

The graph builder tools are **archived behind the `graph` internal proxy** — they are not on jig's top-level tool surface. To use them:

1. Discover the schemas:
   ```
   proxy_tools_search(query="graph_builder")
   ```
   Returns descriptions for `graph_builder_create`, `graph_builder_add_node`, `graph_builder_add_edge`, `graph_builder_update_node`, `graph_builder_save`, `graph_builder_preview`, `graph_builder_validate`.

2. Build:
   ```
   execute_mcp_tool("graph", "graph_builder_create", {
     "graph_id": "sprint-<short-slug>",
     "name": "<descriptive name>",
     "description": "<one line>"
   })
   ```

3. One node per wave with:
   - `id` (e.g. `wave1_foundation`)
   - `name` (display)
   - `prompt_injection` — the exact instructions the orchestrator will paste into each subagent of that wave (paths, acceptance criteria, constraints)
   - `tools_blocked` if you want to enforce read-only phases
   - Add via `execute_mcp_tool("graph", "graph_builder_add_node", {...})`

4. Edges between waves with phrase conditions:
   ```
   execute_mcp_tool("graph", "graph_builder_add_edge", {
     "graph_id": "...",
     "from_node": "wave1_foundation",
     "to_node": "wave2_backend",
     "id": "w1_to_w2",
     "phrase": "wave 1 complete"
   })
   ```

5. Validate + save:
   ```
   execute_mcp_tool("graph", "graph_builder_validate", {"graph_id": "..."})
   execute_mcp_tool("graph", "graph_builder_save", {"graph_id": "..."})
   ```
   That writes the YAML to `<project>/.claude/workflows/<graph_id>.yaml`.

6. Activate:
   ```
   graph_activate(graph_id="<your id>")
   ```

> **Why this lives in a proxy:** the graph builder API is large (10+ tools) and most sessions never touch it. Hiding it keeps jig's top-level surface around 26 tools while remaining one `proxy_tools_search` away when you need it.

## Step 3 — Present the plan

Before kicking anything off, show the user a table:

```
| Wave | Deliverables | Agents | Parallel |
|------|-------------|--------|----------|
```

Ask for approval. The user might want to adjust scope, split or merge waves, or pick different agents. Wait for their go-ahead.

## Step 4 — Execute waves

For each wave:
1. `graph_traverse` into the wave's node (after Wave 1 is the active node from activation; subsequent waves require traverse).
2. Read the wave's `prompt_injection`.
3. Launch all agents within the wave **concurrently** with `run_in_background: true`. Each agent receives:
   - The wave's `prompt_injection`.
   - The user's original task verbatim.
   - The Step 0 continuity injection if any.
   - Concrete file paths to read.
   - Acceptance criteria for *this wave only*.
   - Self-contained context (assume no shared memory with other agents).
4. Never launch agents in the same wave that write to the same files — they will conflict.
5. After all agents in a wave complete, **verify their output** before advancing. Read the files they claim to have changed.
6. If DCC reports new high/critical smells, resolve before traversing.

## Step 5 — Validate

Run the project's check pipeline (`deno task check`, `npm test`, `pytest`, `cargo check`, etc.). If it fails, address it before declaring done.

## Step 6 — Close out

1. `graph_reset` to clear the workflow.
2. **Save the hand-off:** call `next_task_record(summary=<your final summary to the user>, task_description=<the original sprint description>, files_changed=[<paths>])`.
3. Final summary for the user: deliverables shipped, files changed, check pipeline result. 3-5 sentences.

## Recovery — if jig MCP disconnects mid-sprint

If `graph_status`/`graph_reset` become unreachable, the user can clear the persisted graph state from a terminal:

```bash
jig graph reset --project <PROJECT_PATH>
```

After they restart Claude Code you can resume.

## Hard rules

- Main context is the orchestrator — delegate **all** implementation to specialized subagents.
- Launch agents within a wave concurrently with `run_in_background: true`.
- Never launch agents that write to the same files in the same wave.
- After all agents in a wave complete, verify their output before advancing to the next wave.
- Do not commit until the Validate wave passes. Do not commit unless the user explicitly asks.
- If DCC reports new high/critical smells in the Validate wave, fix before declaring done.
- Architecture review criteria should come from project CLAUDE.md, not invented ad-hoc.
- Always end with `next_task_record` so `/clear` is safe between sprints.
