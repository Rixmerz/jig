# Testing Guidelines

## Pre-commit (local)

```bash
uv run pre-commit install
uv run pre-commit run --all-files
```

- **Ruff** + **ruff format** are **manual** (same stage as mypy) so `git commit` is not blocked
  on the repo’s existing Ruff backlog. Run:
  `uv run pre-commit run ruff ruff-format --hook-stage manual --all-files`
  or `ruff check` / `ruff format` like **CI** (`.github/workflows/test.yml`).
- **mypy** (manual): `uv run pre-commit run mypy --hook-stage manual --all-files`  
  types `src/jig/core` only. Full `uv run mypy` matches `pyproject.toml` (includes `engines/`).
- **no-commit-to-branch** blocks commits on `main` / `master` (use a feature branch + PR).
- Also: `check-json`, `check-case-conflict`, `debug-statements`, merge markers, 500kb file cap.

Baseline (as of 0.1.0a21):

- **150/150 pytest** — `uv run --extra dev pytest src/jig/tests/`
- **Fresh-VM E2E** — `scripts/fresh-vm-e2e.sh` (Docker, python:3.12-slim)
- **59-tool functional audit** — done externally, all closed except the
  three known non-blocking residues (B3b / B4 / B8).

What's **not** yet covered by automated tests. Each of these sections
is a procedure that can be run by hand in under ~10 minutes. When a
path here turns green, lift it into `src/jig/tests/` as a regression
test so the next refactor doesn't silently break it.

---

## 1. DCC smell-delta integration

**Goal.** Verify that after `Edit`/`Write`/`Bash` on an indexed
project, `snapshot_trigger` injects a "DCC smells in changed files"
block into Claude Code's next-turn context.

**Prereqs.**

- Fresh project, git-initialized.
- DeltaCodeCube MCP installed (for example by `uv tool install`ing
  an external `deltacodecube` package) so `dcc.db` gets populated
  when you index.

**Setup.**

```python
# In Claude Code, at the project root
jig_init_project(project_path="/abs/path/to/project")
deploy_project_agents(project_path="/abs/path/to/project",
                     tech_stack=["python"])  # or whatever fits
# Register DCC as a subprocess proxy for indexing
proxy_add(name="dcc", command="<dcc-executable>", args=[...])
# Trigger indexing however DCC exposes it
execute_mcp_tool("dcc", "index_project", {...})
```

**Procedure.**

1. Confirm `~/.local/share/jig/dcc.db` exists and is non-empty
   (`ls -la ~/.local/share/jig/dcc.db`).
2. Make an Edit that touches a file the indexer scanned.
3. Wait for the snapshot trigger (30 s throttle; first edit fires
   immediately). Observe `stderr` stream for
   `[jig.snapshot] captured …`.
4. On your **next** turn, inspect the PostToolUse additional context
   you're given. It should contain:
   - `jig captured a snapshot. Files changed since previous snapshot:`
   - Optionally followed by `DCC smells in changed files:` and up to
     5 ranked entries.

**Accept** if the DCC block appears for at least one Edit that
produced a smell. **Fail** if it never appears despite a populated
`dcc.db` — most common cause is that the changed file's path doesn't
match any `file_path` in the `smells` detector output (normalisation
bug in `dcc_integration.smells_for_files`).

---

## 2. DAG nodes with parallel tasks

**Goal.** Verify that a node declared `node_type: "dag"` with a task
list traverses dependencies correctly and `graph_get_ready_tasks`
returns the right subset at each step.

**Setup.** Author a workflow with one DAG node. Easiest path:

```python
execute_mcp_tool("graph", "graph_builder_create",
                 {"name": "dag-smoke", "builder_id": "dag"})
execute_mcp_tool("graph", "graph_builder_add_node", {
    "builder_id": "dag",
    "node_id": "impl",
    "name": "Implement",
    "is_start": True,
    "node_type": "dag",
    "tasks": [
        {"id": "schema",   "name": "Define schema",   "dependencies": []},
        {"id": "migrate",  "name": "Write migration", "dependencies": ["schema"]},
        {"id": "tests",    "name": "Write tests",     "dependencies": ["schema"]},
        {"id": "ship",     "name": "Open PR",         "dependencies": ["migrate", "tests"]},
    ],
})
execute_mcp_tool("graph", "graph_builder_save",
                 {"builder_id": "dag", "filename": "dag-smoke"})
graph_activate(graph_id="dag-smoke")
```

**Procedure.**

1. `graph_status` → confirm current node is `impl` and `tasks_state`
   reports all 4 tasks as `pending`.
2. `execute_mcp_tool("graph", "graph_get_ready_tasks", {})` →
   should return exactly `["schema"]` (only task with no unmet deps).
3. `execute_mcp_tool("graph", "graph_task_complete", {"task_id": "schema"})`.
4. `graph_get_ready_tasks` → should return exactly `["migrate", "tests"]`
   (parallel-ready siblings).
5. Complete one of them. Ready set should drop to the remaining sibling.
6. Complete the last sibling. Ready set should become `["ship"]`.
7. Complete `ship`. Node should auto-advance (or `graph_traverse` must
   succeed without further acks).

**Accept** when the ready set matches the DAG graph's frontier at each
step. **Fail** if a task becomes ready before its dependencies complete
(ordering bug) or never becomes ready even after deps clear (state-read
bug).

---

## 3. Tension gates with acknowledge

**Goal.** Verify that a workflow node with `tension_gate` blocks
`graph_traverse` until the gate is either met OR explicitly
acknowledged via `graph_acknowledge_tensions`, and that
acknowledgements land in the audit log.

**Setup.** Workflow with a gated edge:

```yaml
# fragment
edges:
  - id: implement-to-review
    from: implement
    to: review
    condition:
      type: always
    tension_gate:
      max_critical: 0
      max_high: 2
```

With DCC indexed and at least one critical smell present in the changed
set, the gate should block.

**Procedure.**

1. `graph_activate` the workflow. Reach node `implement`.
2. Edit a file in a way that introduces a critical smell (e.g.
   god-file creation, tight cyclic import).
3. Try `graph_traverse(direction="next")`. Expect a block response
   citing the tension gate; the response should include the raw
   smell count broken down by severity.
4. Call `execute_mcp_tool("graph", "graph_acknowledge_tensions",
   {"reason": "spike — will resolve in next sprint"})`.
5. Retry `graph_traverse`. Should now succeed.
6. Check the audit log:
   `~/.local/share/jig/states/<project>/audit.jsonl` (or
   `.jig/audit.jsonl` if local fallback). Expect an entry with
   `action: "gate_acknowledged"`, timestamp, user-supplied reason,
   and the smell snapshot at acknowledgement.

**Accept** when the block fires, the acknowledgement clears it, and
the audit entry is persisted. **Fail** if:
- The gate never blocks (tension_gate parsing / DCC integration bug).
- Acknowledgement clears without an audit log entry (silent bypass).
- Acknowledgement requires no reason (should be a required param).

---

## 4. Full `sprint-0-test` run to the `record` phase

**Goal.** Take the bundled `sprint-0-test-graph.yaml` workflow
end-to-end from `discover` through `record`, verifying each phase's
entry injection fires and the final `record` phase writes experience
entries that survive a session restart.

**Setup.**

```python
jig_init_project(project_path="/tmp/sprint-0-run")
# No deploy_project_agents needed; workflow injects its own context
graph_activate(graph_id="sprint-0-test",
               project_dir="/tmp/sprint-0-run")
```

**Procedure.**

1. `graph_status` → current node `discover`.
   - Verify `tools_blocked` really blocks Edit/Write. Open a new
     session if the enforcer was swapped mid-session; Claude Code
     caches hooks (see note at bottom).
2. Cycle through each phase using only the allowed tools. At each
   transition observe `prompt_injection` in the response. Phases:
   `discover → design → implement → review → record`.
3. In `record`, call
   `execute_mcp_tool("experience", "experience_record", {...})`
   with the decisions made.
4. Exit the session. Reopen.
5. `experience_query(file_path="...", scope="project")` → the entries
   recorded in step 3 must come back with their original fields
   intact (description, severity, resolution, related_files).

**Accept** when every phase enforces its `tools_blocked` correctly,
every prompt_injection fires exactly once per phase entry, and the
`record` payload survives a restart. **Fail** if any phase allows a
blocked tool (re-triage B2b), any injection fires multiple times
(idempotence bug), or recorded entries are missing / mangled after
restart (persistence bug).

---

## Reporting

For any failure in sections 1–4 above, file a bug entry in
`BUGS.md` (or your equivalent) with:

- **ID**: next free (B13+)
- **Severity**: 🔴 crítica / 🟠 alto / 🟡 medio / 🟢 bajo / 💄 cosmético
- **Repro**: exact tool call(s) + arguments
- **Expected vs observed**
- **Suspected layer**: hook / engine / tool wrapper / asset / Claude Code cache

Known cache gotcha: Claude Code snapshots hook scripts at session
start. Edits to `.claude/hooks/*.py` or changes to the installed
`jig-mcp` binary require `/exit` + reopen — or `uv tool upgrade
jig-mcp` followed by `/mcp` reconnect — before the new behaviour
reaches the live enforcer pipeline.

## Once a section is green

Lift it into `src/jig/tests/` as a deterministic pytest case:

- DCC: stub `smells_for_files` with a seeded SQLite or a monkeypatched
  return value; assert the hook's `additionalContext` output.
- DAG: build the graph in-memory, call `graph_get_ready_tasks` /
  `graph_task_complete` directly on the engine.
- Tension gate: hand-craft a graph_state + DCC fixture; assert the
  block response and the audit entry.
- Sprint-0: replay the transition log on a fixture graph; assert
  phase order and final state.

The manual procedure stays in this doc as the human-readable source
of truth; the pytest case is the regression guard.
