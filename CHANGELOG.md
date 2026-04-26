# Changelog

All notable changes to `jig` are documented in this file. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versioning
adheres to [SemVer](https://semver.org/).

## [0.1.0a28] — 2026-04-26

### Added

- **User-level memory store** (`~/.jig/memory/`) with MCP tools
  `memory_get`, `memory_set`, `memory_delete`. Rich schema: TTL,
  priority (`high` / `normal` / `low`), tags, links, type
  (`feedback` / `project` / `user` / `reference`). Separate from
  Claude Code's native `~/.claude/` memory; adds scoring by
  relevance + recency, link expansion, and TTL-based expiry.

- **Two-tier memory injection** (`UserPromptSubmit` hook). Memories
  travel from the user-level brain (`~/.jig/memory/`) exactly once
  per project — on first relevant prompt they are injected AND cached
  into `.claude/memory/`. Subsequent prompts skip re-injection
  entirely (zero token duplication). Cache invalidates automatically
  when the global source is updated (mtime comparison).

- **Semantic embedding for memory matching.** `user_memory_injector`
  now uses fastembed cosine similarity (`BAAI/bge-large-en-v1.5`,
  same model already cached for tool search) when
  `JIG_MEMORY_SEMANTIC=1` is set. Falls back to keyword overlap on
  any error. Enables synonym matching — "headless browser scraping"
  now finds a memory tagged `browser` without the exact word.

- **SessionStart bootstrap hook** (`session_bootstrap.py`). Injects
  pending `next_task` context and warns if DCC is indexed on a
  different project. 5-second SIGALRM timeout; silent when nothing
  to report.

- **Stop hook for session knowledge capture**
  (`session_knowledge_capture.py`). Reads the session transcript
  on close, counts `memory_set` calls and git commits, prints a
  brief summary if there's anything worth noting. Always exits 0;
  never blocks session close.

- **DCC scope check in `jig doctor`**. `_check_dcc_injection` now
  queries `code_points` for rows matching `CLAUDE_PROJECT_DIR`.
  Reports `[!]` when `dcc.db` has data from a *different* project,
  and includes the indexed file count in the pass message.

- **`jig resync` cleans stale `.claude/memory/`**. After copying
  fresh assets, `_clean_stale_project_memory` removes local cache
  copies whose global source in `~/.jig/memory/` was deleted, and
  refreshes entries where the global file is newer.

- **`jig update` command** — single command to upgrade `jig-mcp`
  via `uv tool upgrade` and resync all scaffolded projects.
  Supports `--project`, `--no-resync`, `--dry-run`.

- **`_patch_settings` refactored** into idempotent per-hook helpers
  (`_ensure_user_prompt_submit_hook`, `_ensure_session_bootstrap_hook`,
  `_ensure_stop_hook`). Running `jig resync` on any project now
  installs all three hooks without rewriting unrelated settings.

- **Explicit proxy discovery rule** in `jig-methodology.md`. When
  the user names a proxy by name (e.g. "use obscura"), the first
  action is always `proxy_tools_search(query="<name>")` before any
  `execute_mcp_tool` call.

### Fixed

- **DCC orphan smell noise** — `dcc.db` was indexed on `test-jig`
  instead of the active project. `jig doctor` now detects and reports
  this. Re-index with `cube_index_directory(path='src/')`.

- **`_EXPECTED_HOOKS`** updated to include `session_bootstrap.py`,
  `session_knowledge_capture.py`, and `user_memory_injector.py`
  (previously missing). `jig doctor` now flags missing entries.

## [0.1.0a27] — 2026-04-21

### Added (doctor extensions)
- **DCC injection check.** When a per-project audit runs, `doctor` now
  inspects the project's enforcer config and the XDG DCC db. Reports
  `[!] DCC indexed` if the db is missing / empty (user hasn't run
  `cube_index_project` yet) or `[!] DCC injection config` when
  `dcc_injection_enabled` or `mid_phase_dcc` is false while data IS
  indexed — the case where smells would quietly stop auto-injecting.
- **Hook content drift.** Compares each local `.claude/hooks/*.py` to
  the bundled wheel version (sha256) and flags the mismatches as
  `[!] hook content drift`. Drift repair is deliberately NOT added
  to the auto-repair plan: overwriting a hand-edited hook would be
  destructive, so users have to think before acting.
- **Unified diff in `--dry-run`.** The settings.json rewrite now
  renders its unified diff under the repair plan so users can verify
  exactly which `python3` lines will flip to `sys.executable` before
  committing to `--repair`.

## [0.1.0a26] — 2026-04-20

### Added
- ``jig doctor --project <path> [--repair] [--dry-run]``. Diagnostics
  beyond the global smoke (python, fastembed, XDG, git) now cover
  per-project drift from an upgraded bundle:
  - ``settings.json`` hook commands use absolute python (vs the bare
    ``python3`` shipped by pre-a25 ``jig init``).
  - ``.claude/hooks/*.py`` all present and executable.
  - ``jig-methodology.md`` rule present (sanity on post-a17 init).
  ``--repair`` auto-fixes the two mechanical issues: it rewrites the
  settings.json stanzas to ``sys.executable`` and re-copies any
  missing hook from the wheel + ``chmod +x`` on hooks lacking the bit.
  ``--dry-run`` prints the plan without writing. Both flags are opt-in;
  the default ``jig doctor --project <path>`` is read-only.
- Check status glyphs widened from ``✓ / ✗`` to ``✓ / ✗ / !`` so
  non-fatal drift (e.g. "12 hooks present but not executable") reads
  as warning, not failure.

### Use case
Projects scaffolded before 0.1.0a25 have stale ``python3`` in their
``.claude/settings.json`` and the fix didn't auto-propagate on
``jig-mcp`` upgrade (template code ran at scaffold time, not at
runtime). ``jig doctor --project /path --repair`` brings them to the
current template without having to re-run ``jig init`` (which would
overwrite any hand-edited agents / rules / workflows).

## [0.1.0a25] — 2026-04-20

### Fixed
- **B15:** ``graph_mid_phase_dcc`` reported "DCC not configured" even
  after 0.1.0a24 exposed DCC as an internal proxy. The detector
  (``dcc_integration._is_dcc_available``) still only queried the
  legacy external-MCP config. It now checks the internal_proxy
  registry first (primary path — the vendored DCC),
  falls back to the external config (for users who run their own DCC
  subprocess). ``dcc`` as a registered proxy name is also accepted,
  not just ``deltacodecube``.
- **B16:** ``jig init`` rendered ``settings.json`` with bare
  ``python3`` in every hook command. Claude Code spawns hooks by
  literal command-string; a bare ``python3`` picks up whatever
  interpreter is on ``PATH``, which usually does not have jig's
  dependencies — so every Python hook (``snapshot_trigger``,
  ``dcc_feedback``, ``experience_recorder``, etc.) failed silently
  at ``import jig.engines...``. ``_copy_assets`` now substitutes
  ``"python3 "`` with ``sys.executable`` + space, so hooks run under
  the same Python that jig-mcp itself runs under — the ``uv tool
  install`` env that has every dep available. Side effect: the
  generated ``settings.json`` now contains an absolute python path;
  moving jig to a different env requires a ``jig init`` re-run.

## [0.1.0a24] — 2026-04-20

### Added
- **Vendored DeltaCodeCube exposed as internal proxy ``dcc``.** The
  original plan called for ``engines.dcc.register_internal_proxy()``
  at server startup so the 36-tool DCC surface is reachable via
  ``execute_mcp_tool("dcc", "cube_detect_smells", …)`` and
  ``proxy_tools_search`` without users having to ``proxy_add`` an
  external DCC MCP. That wiring never landed in the port — DCC was
  vendored as Python, but no MCP layer. Closed here by:
  - New ``_tool_archive.archive_external_mcp(holder, proxy_name)``
    helper that harvests tools from a FastMCP holder and registers
    them as an internal proxy (embedding descriptions into the
    cache so ``proxy_tools_search`` finds them).
  - ``server._register_tools`` now creates a throwaway
    ``_dcc_holder`` FastMCP, runs DCC's ``register_all_tools`` on
    it, then calls ``archive_external_mcp(holder, "dcc")``. 36 tools
    moved.
- ``proxy_list`` now reports ``dcc`` alongside the 8 previous
  internal proxies. Smell-delta injection in ``snapshot_trigger``
  works out of the box once DCC's DB is populated (run
  ``execute_mcp_tool("dcc", "index_project", …)`` once).

### Clarified
- ``memory_injector`` and ``smart_context`` hooks are silent by
  design on a greenfield project — they inject context only when
  matching ``.claude/memory/**`` files or pre-computed caches exist.
  Silence is not a bug; documented the intended pre-conditions.

## [0.1.0a23] — 2026-04-20

### Fixed
- **B13:** ``graph_task_complete`` reported every ready task as
  ``newly_ready``, even the ones that were ready *before* the
  completion. It's supposed to be a delta — "what unblocked because
  you just finished this task." Fix: snapshot the ready set before
  ``mark_task_complete``, diff against the post-complete set. The
  response now exposes three disjoint arrays:
  ``newly_ready`` (actually unblocked by this completion),
  ``still_ready`` (ready before and still are, not yet completed),
  and ``ready`` (the full post-complete frontier — the union, kept
  for callers that want the simpler view).
- **B14:** ``experience_record`` docstring listed 7 accepted ``type``
  values while ``engines.experience_memory.VALID_TYPES`` contains 8
  (``skill_referenced`` was the stray). Doc rewritten to enumerate
  the exact frozenset and point at it for truth-keeping.

## [0.1.0a22] — 2026-04-20

### Fixed
- **Critical: MCP reconnect failures due to ~47 s startup latency.**
  `_tool_archive.archive_all` runs on every server boot and calls
  `embed_cache.upsert_tools` with the 33 internal-proxy tool
  descriptions. The old implementation always re-embedded every
  descriptor, forcing the fastembed model load + inference on each
  startup; with BGE-large that's 40–50 s. Claude Code's MCP spawn
  timeout fires well before then, which is what produced the
  "Failed to reconnect to jig" the user kept hitting after every
  restart. `upsert_tools` now pre-reads the existing
  ``(mcp_name, tool_name, text_hash)`` from SQLite and filters the
  input down to rows that actually changed. First run still pays
  the embed cost; subsequent runs skip everything and the server
  handshake completes in well under a second.

## [0.1.0a21] — 2026-04-20

### Fixed
- **B2b (critical):** Path mismatch between writer
  (``engines.graph_state._get_centralized_state_dir`` → XDG
  ``~/.local/share/jig/states/<proj>/``) and reader
  (``hooks.graph_enforcer.get_state_path`` → looked only at
  ``~/.local/share/jig/config.json`` which doesn't exist, then fell
  back to ``.claude/workflow/``). Effect: tools_blocked was
  **decorative** — every enforcer invocation found no state and
  approved. ``get_state_path`` now probes the XDG hub path first
  (matches the writer exactly), then the legacy config.json override,
  then project-local. Enforcement is real again.
- **B3b:** ``graph_list_available`` returned
  ``description: "|"`` for ``demo-feature.yaml`` because its
  top-level ``description: |`` uses the YAML block scalar form; the
  scanner captured the literal pipe. Scanner now joins the indented
  continuation lines for top-level and ``metadata:``-nested keys.

### Changed
- **B8:** ``experience_query`` default raised to ``min_score=0.5``
  and given a ``scope`` parameter (``project`` default / ``global``
  / ``both``). A greenfield project querying a path like
  ``src/greeter.ts`` was pulling in jig's own asset paths from the
  global store at the old 0.3 threshold; ``scope="project"`` +
  higher floor fixes it. The old union-by-default behaviour is still
  reachable via ``scope="both"``.
- **B4:** ``jig init`` / ``jig_init_project`` auto-detect now also
  treats a package installed under ``~/.local/share/uv/tools/`` as
  the tool-install form, not just ``shutil.which("jig-mcp")``. MCP
  subprocesses with stripped PATH still get the lock-free
  ``{"command": "jig-mcp"}`` render instead of falling back to
  ``uvx --from git+https://…``.

## [0.1.0a20] — 2026-04-20

### Fixed
- **B3:** `graph_list_available` ignored `demo-feature.yaml` (and any
  other workflow whose filename didn't match `*-graph.yaml`). Glob
  widened to `*.yaml`, then results filtered by content (must contain
  `nodes:` + `edges:` top-level sections). The metadata scanner also
  supports the two YAML shapes jig actually ships — the builder's
  `metadata:` block and the flat top-level `name:` / `description:`
  style used by `demo-feature.yaml` — so both render with their real
  name instead of falling through to the filename.
- **B9:** `proxy_keepalive` on an internal proxy used to return
  `{"ok": false, "reason": "proxy <name> not currently connected"}`
  because internals have no entry in the subprocess pool. It now
  short-circuits for `internal_proxy.has_mcp(name)` with
  `{"ok": true, "kind": "internal", "note": "…"}` — the right
  semantics, since internals have no idle timer to extend.

### Changed
- **B6:** `proxy_tools_search` accepts `include_schema=True` to return
  each hit's `input_schema` alongside the description. Lets the agent
  pick correct kwargs without a second `proxy_list_tools` round-trip.
  Default remains `False` to keep result payloads small.
- **B8:** `experience_query` default relevance threshold bumped from
  `0.05` to `0.3` and exposed as a `min_score` parameter. At 0.05
  a greenfield project with a large legacy memory pool would return
  noise; 0.3 keeps the signal-to-noise positive. Drop to 0.05 when
  you genuinely want everything loosely related.

## [0.1.0a19] — 2026-04-20

### Fixed
- **B2 (critical):** `tools_blocked` enforcement was silently neutralised
  when LLMs passed the list as a JSON string (e.g.
  `"[\\"Edit\\", \\"Write\\"]"`) instead of a real array. FastMCP's
  pydantic validation runs at the surface-tool boundary, but archived
  tools are dispatched by `handler.fn(**args)` which skips it — so the
  stringified list made it into `_generate_graph_yaml`, got iterated
  character-by-character, and produced a useless block list.
  `internal_proxy.invoke` now coerces args against
  `handler.input_schema`: fields typed `array` receive `json.loads`
  when given a string, falling back to `[value]` if parse fails;
  fields typed `object` get the same treatment. Every archived tool
  across the 7 internal proxies now sees validated, correctly-typed
  kwargs.
- **B7 (cosmetic):** `_parse_agent_frontmatter` now handles YAML block
  scalars (`description: |` followed by indented continuation lines)
  and inline/block lists. `workflow-executor.md` and
  `codebase-analyst.md` no longer end up with `description: "|"` in
  their deployed frontmatter — the full prose comes through.
- **B1 (cosmetic):** `graph_list_available` was scanning the entire
  YAML for `name:` / `description:` lines and picking up values from
  whichever node happened to come last. Scan now restricted to the
  top-level `metadata:` block.
- **B12 (medium):** `proxy_reconnect` and `proxy_refresh_embeddings`
  crashed when the underlying subprocess failed to start or the MCP
  handshake raised. Both wrap the connect/start/handshake in
  try/except now, log the failure to stderr, and return a structured
  result (`False` / `0`) so the caller never receives a bare
  exception.

## [0.1.0a18] — 2026-04-20

### Added
- `graph_builder_update_node(builder_id, node_id, **fields)` —
  idempotent patch of an existing node. Only provided kwargs are
  written; the rest are left alone. Removes the "delete the whole
  builder to flip one flag" friction.
- `graph_builder_update_edge(builder_id, edge_id, **fields)` —
  sibling for edges. Flipping an edge from `type: always` to
  `type: phrase` no longer requires `add_edge` with a new id + `delete`
  the old one. When switching `condition_type`, the newly-irrelevant
  `condition_tool` / `condition_phrases` fields are cleared so the
  rendered YAML matches the new type.

### Changed
- `_generate_graph_yaml` auto-infers `is_end: true` for every node
  with no outgoing edge. Saves the author from having to flag
  terminal nodes explicitly, and the generated YAML always passes
  validation without a round-trip edit.
- `graph_builder_add_edge` validates `condition_type` strictly:
  `phrase` without `condition_phrases` → error; `tool` without
  `condition_tool` → error; unknown type → error. Previously the
  irrelevant fields were silently dropped, producing an `always`
  edge the author didn't intend.
- Both new update tools archived under the `graph` internal proxy,
  so surface count stays at 26.

## [0.1.0a17] — 2026-04-19

### Added
- New `rules/jig-methodology.md` base rule + matching
  `skills/jig-methodology/SKILL.md` operational playbook. The rule
  sets the mental model (discover → execute_mcp_tool, snapshots are
  automatic, DCC signals surface themselves, tool budget). The skill
  gives the concrete recipes: kickoff sequence, per-task flows
  (feature / bug hunt / refactor / MCP add), native replacements for
  `git log`/`git stash`/`grep commits`, enforcer etiquette, and a
  "things NOT to do" list.
- `jig-methodology` added to `_CORE_SKILLS` so every invocation of
  `deploy_project_agents` injects it into the deployed agents'
  frontmatter regardless of tech stack.
- `jig-methodology.md` added to `BASE_RULES` so `jig init` drops it
  into `<project>/.claude/rules/` on scaffold.

### Removed
- `rules/serena-mcp.md`. Serena is one of many MCPs users can add via
  `proxy_add`; bundling a rule that told every agent to prefer Serena
  was opinionated in a way jig shouldn't be. Removed from
  `BASE_RULES` too.

## [0.1.0a16] — 2026-04-19

### Changed
- `jig init` / `jig_init_project` now prefers a tool-installed
  `jig-mcp` on `PATH` over rebuilding with `uvx` on every spawn.
  When the binary is detected, the rendered `.mcp.json` becomes:

  ```json
  {"mcpServers": {"jig": {"command": "jig-mcp"}}}
  ```

  The motivating bug: `uvx --from …` holds an exclusive lock on
  `~/.cache/uv/.lock` for the duration of each build, so concurrent
  Claude Code sessions couldn't both spawn jig — the second one
  hit the lock, Claude Code's MCP spawn timeout fired, and the
  session reported "Failed to reconnect to jig". The tool install
  has no lock at spawn time.

- New `--source tool` value (also `JIG_SOURCE=tool`) explicitly asks
  for the bare form. Default behavior is auto-detect: if
  `shutil.which("jig-mcp")` hits, render tool form; otherwise fall
  back to `git+https://github.com/Rixmerz/jig` (still keeps
  zero-setup working, just slower under concurrency).

- README + docs/init.md walked through the three render modes (`tool`,
  PyPI, git+https) with a table showing when each applies, and the
  recommended first-time install command.

## [0.1.0a15] — 2026-04-19

### Changed
- `jig init` / `jig_init_project` default source is now
  ``git+https://github.com/Rixmerz/jig`` instead of the PyPI spec.
  The rendered ``.mcp.json`` therefore works out-of-the-box while
  jig-mcp isn't on PyPI yet — no ``--source`` flag required. Override
  with ``--source jig-mcp`` (or ``JIG_SOURCE=jig-mcp``) to use the
  PyPI package after publication. Docs and CLI help updated to match.
- Docs (``docs/init.md``, README) also note the new default.

## [0.1.0a14] — 2026-04-19

### Added
- `jig_init_project(project_path, source?, dry_run?, no_warmup?)`
  MCP tool. Phase-0 entry point — same behavior as the `jig init`
  CLI, but callable straight from the agent so the whole
  init → deploy flow stays inside the chat without shelling out.
  Returns a structured result with `phase`, `next_step`, and the
  resolved path so the agent knows what to call next.

### Changed
- `deploy_project_agents` moved from the `deploy` internal proxy
  back to the top-level MCP surface. The two lifecycle entry points
  (`jig_init_project`, `deploy_project_agents`) are now both visible
  in every session without semantic search. The now-empty `deploy`
  bucket is removed from `ARCHIVE_MAP`.
- Top-level surface: 24 → 26. Internal proxies: 8 → 7.

## [0.1.0a13] — 2026-04-19

### Changed
- `jig init` now copies **only** universal rules (10 files listed in
  `init_cmd.BASE_RULES`) instead of all 23. Stack-specific rules
  (`python.md`, `typescript.md`, `rust.md`, `ui.md`, …) stay in the
  wheel and are dropped into the project by
  `deploy_project_agents(tech_stack=…)` based on the declared stack.
- This removes the double-copy that 0.1.0a12 and earlier produced:
  init would dump every rule into `.claude/rules/` and then
  `deploy_project_agents` would rewrite a subset on top.
- Hooks, commands, workflows, and `settings.json` are unchanged —
  still base-tier, always copied.
- `init` completion line now reports the rule count so you can see at
  a glance that the base is 10 files, not 23.

## [0.1.0a12] — 2026-04-19

### Added
- `engines.dcc_integration.smells_for_files(paths, *, max_results)`:
  best-effort API that opens the vendored DCC SQLite db (if present),
  runs `SmellDetector.detect_all()`, filters smells whose file_path
  hits any of the given paths, and returns up to `max_results` ranked
  by severity. Returns `[]` on any missing prerequisite — no DB, no
  index, no smells, raise.
- `hooks.snapshot_trigger`: after the git-diff delta block, appends
  a "DCC smells in changed files" block when the above API finds
  anything. Still a no-op when DCC hasn't been indexed.
- `scripts/fresh-vm-e2e.sh`: one-shot end-to-end validation inside a
  clean `python:3.12-slim` container. Installs jig via `uv tool
  install`, scaffolds a project with `jig init`, asserts `.claude/`
  layout, runs `jig doctor`, verifies the surfaced tool count +
  internal proxies, checks `jig_guide`, checks failing
  `proxy_refresh_embeddings`, and runs the pytest suite in a
  writable copy. **Currently green** (first real fresh-VM validation).

### Changed
- `engines.dcc.config`: DCC's SQLite now lives under jig's XDG
  directory (`~/.local/share/jig/dcc.db`) instead of
  `~/.deltacodecube/`. Closes the last independent data-dir.
  Override via `DCC_DATA_DIR` still works.
- `engines.proxy_pool`: `proxy_statuses` and `_resolve_config` now
  skip MCP names matching jig itself (`jig`, `jig-mcp`) so the
  ghost-self-proxy that previously showed up as
  `{kind: subprocess, connected: false}` in `proxy_list` is gone.
- `tools.deployment._TECH_SKILL_MAP` / `_TECH_RULE_MAP`: re-add
  `tauri`, `react-tauri`, `rust-backend`, `css-theming` entries now
  that the underlying skill packages have been recovered (see next).

### Recovered
- Reinstate 4 agents + 4 skills + 1 command that were deleted in
  0.1.0a11. Copied from the agentcockpit source
  (`~/Projects/agentcockpit/.hub/…`) rather than rewritten from
  scratch, then scrubbed with the same sed pipeline that cleans
  engine code: `.agentcockpit/` → `.jig/`, `.workflow-manager/` →
  `~/.local/share/jig/`, `/var/home/rixmerz/agentcockpit` →
  `<project-root>`, `agentcockpit` → `jig`.
  - `agents/{browser,plugins,terminal,git-snapshots}.md`
  - `skills/{css-theming,react-tauri,rust-backend,xterm-pty}/`
  - `commands/build.md`
- Catalog back to 19 agents, 26 skills, 5 commands, 23 rules.

## [0.1.0a11] — 2026-04-19

### Removed
- Purge every agentcockpit reference — jig replaces agentcockpit, it
  doesn't migrate from it.
- Deleted assets with no meaning in jig:
  - `agents/terminal.md` (xterm.js PTY panel)
  - `agents/browser.md` (embedded webview)
  - `agents/plugins.md` (agent plugin system for a desktop host)
  - `agents/git-snapshots.md` (the bundled `snapshot_*` internal
    proxy + the auto hook fully covers this)
  - `commands/build.md` (distrobox + Tauri release flow)
  - `skills/xterm-pty/`, `skills/css-theming/`,
    `skills/react-tauri/`, `skills/rust-backend/` — all UI-stack
    specific to agentcockpit.
  - `workflows/framework-evolution-graph.yaml` — a workflow about
    evolving workflow-manager itself.
- Scrubbed hardcoded paths in every remaining asset/hook/engine:
  `.agentcockpit/` → `.jig/`, `.workflow-manager/` →
  `~/.local/share/jig/`, `workflow-manager` → `jig`, `agentcockpit`
  → `jig`, `/var/home/rixmerz/agentcockpit` → `<project-root>`.
- `graph_state.py`: dropped `AGENTCOCKPIT_CONFIG_FILE` and hub-config
  load path. Centralized state dir is now unconditionally
  `~/.local/share/jig/states/<project_name>/`.
- `proxy_pool.py`: docstrings that referenced "replaces
  mcp_connection.py from workflow-manager" and
  "(agentcockpit compatibility)" rewritten.

### Changed
- `_TECH_SKILL_MAP` / `_TECH_RULE_MAP` entries trimmed to reference
  only the skill set that still ships. (No `css-theming`,
  `rust-backend`, `xterm-pty`, `react-tauri` remain.)

## [0.1.0a10] — 2026-04-19

### Removed
- All agentcockpit legacy paths. This is a new project and shouldn't
  carry a compatibility surface we didn't need yet.
  - `~/.workflow-manager/` fallback reads in `experience_memory` and
    `tool_index` — XDG-only now.
  - `~/.agentcockpit/config.json` read in `hub_config` — XDG defaults
    only; the only legacy MCP config source kept is `~/.claude.json`
    because that's where Claude Code stores user-scope MCPs.
  - `jig migrate` subcommand and `cli/migrate_cmd.py` — no legacy to
    migrate for a fresh install.
  - `[workflow-manager]` log prefixes across the codebase renamed to
    `[jig]`.
  - Residual docstrings mentioning workflow-manager / its Ollama
    origin cleaned up.

## [0.1.0a9] — 2026-04-19

### Changed
- Snapshots are automatic, not tools. `snapshot_create`, `snapshot_list`,
  `snapshot_diff`, and `snapshot_restore` moved to the `snapshot`
  internal proxy (still callable via
  `execute_mcp_tool("snapshot", "snapshot_<op>", {...})` when you really
  need them). Top-level surface drops 28 → 24.
- `snapshot_trigger` hook now fires on `Edit`/`Write` in addition to
  `Bash`, throttled to one snapshot per 30 s per project. When a new
  snapshot is captured, the hook emits a PostToolUse
  `additionalContext` payload listing files changed since the previous
  snapshot — Claude sees the delta in its next turn without anyone
  having to ask for it.
- `settings.template.json` updated so new `jig init` projects pick up
  both triggers.

### Deferred
- DCC-powered smell/tension deltas on top of the git-diff summary.
  Needs a clean `smells_for_files(paths)` API in
  `engines/dcc_integration.py`; current surface is monolithic. Tracked
  for 0.2.0 in the ROADMAP.

## [0.1.0a8] — 2026-04-19

### Added
- `jig init --source <spec>` (and `JIG_SOURCE` env var) controls what
  install source gets written into the rendered `.mcp.json`. Defaults
  to `uvx jig-mcp` (PyPI, once published). Pre-PyPI users can pass
  `--source git+https://github.com/Rixmerz/jig` to render
  `uvx --from git+https://... jig-mcp` instead of the PyPI-only form.
- Matching pattern recognised: bare package names stay bare; anything
  starting with `git+`, `.`, or containing `/` is treated as a source
  spec and wrapped with `uvx --from`.
- `jig migrate` subcommand: moves legacy `~/.workflow-manager/*` files
  (experience_memory.json, project_memories/, learned_weights.json)
  into `~/.local/share/jig/`. Never overwrites existing XDG data.
  `--dry-run` previews; `--delete-legacy` removes the source tree
  after a clean run (refuses when any XDG path already existed).
  Five full docs landed under `docs/` (architecture, tools, init,
  embeddings, proxy) — the README's previously-dead links now
  resolve.

### Fixed
- Test suite fully green (150/150). Legacy `workflow_manager.*` imports
  in `test_dcc_smart_filtering.py` and `test_experience_checklist.py`
  now point at `jig.engines.*`. Experience-memory tests additionally
  pin the `_LEGACY_*` fallback constants so XDG-first / legacy-fallback
  logic (0.1.0a5) can't read the user's real `~/.workflow-manager/`.

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
