# Roadmap

Status: `0.1.0a1` shipped 2026-04-19 (first alpha, no PyPI release yet).
This document tracks what lands next. Dates are targets, not commitments.

## 0.1.0 — stable alpha (next)

- **Sweep bundled assets for agentcockpit refs (ongoing).** Prefer neutral
  placeholders in `src/jig/assets/**` (no machine-specific absolute paths).
  CHANGELOG and `docs/architecture.md` may still mention legacy paths for
  migration context.

Close the gaps between "all sprints landed" and "users can actually install it".

- **PyPI publication.** `jig-mcp` name reserved, CI `release.yml` wired for
  trusted publishing (GitHub OIDC, no API tokens). Ship first Test PyPI
  dry-run, then promote to PyPI proper once the smoke from a fresh VM passes.
- **`docs/` shipped.** `architecture.md`, `tools.md`, `init.md`,
  `embeddings.md`, `proxy.md`, and `testing.md` live under `docs/`; keep them
  in sync with README numbers when the tool surface changes.
- **Fresh-VM E2E.** The acceptance criteria at the tail of
  `~/.claude/plans/si-jig-realiza-la-cozy-church.md` (steps 1–18) has not been
  run end-to-end on a clean VM. Blocks release.
- **Model download UX.** `jig doctor --prefetch` documents and performs a
  blocking model load; README quickstart points to it. Server startup still
  warms embeddings in a background thread (non-blocking).

## 0.2.0 — proxy hardening

- **Reconnect backoff telemetry (partial).** `McpConnection.last_error` is set
  on common failures; `jig doctor` reports pooled proxy `last_error` values.
  Remaining: reconnect attempt counters / backoff metrics in `proxy_list`.
- **Per-proxy resource limits.** Subprocess memory cap + wall-clock timeout
  on `execute_mcp_tool`. Currently unbounded.
- **Search quality.** A/B `bge-large` vs `bge-small` vs hybrid
  (BM25 + dense) on real `.mcp.json` fleets. Ship whichever wins on a
  100-tool corpus.
- **Windows support.** Subprocess stdio + path handling audit. Deferred from
  S6 scope. `fastembed` wheels exist for Windows; the rest is shell quoting.

## 0.3.0 — workflow ergonomics

- **`graph_build` live preview.** `dry_run` currently returns JSON; render
  a tree to stderr so authoring a YAML is less blind.
- **`jig_deploy_agents` stack detection.** Inspect `pyproject.toml`,
  `package.json`, `Cargo.toml`, Go modules → pick from `assets/agents/`
  instead of the user guessing the stack string.
- **Skill/rule hot-reload.** Editing `~/.local/share/jig/hub/...` should not
  require a server restart.

## 0.4.0 — multi-project hub

- **Shared experience memory across projects.** Today each project's
  `.jig/experience.db` is isolated. Add an opt-in cross-project index so
  lessons from repo A surface when working in repo B.
- **Cross-project snapshot search.** `snapshot_list --all-projects` for the
  "where did I last do this?" use case.

## Tracking

- Bugs and feature requests: GitHub Issues.
- Design conversations: GitHub Discussions.
- Internal notes and decisions that don't belong in git:
  `~/.claude/plans/si-jig-realiza-la-cozy-church.md` (frozen at
  implementation start — not maintained against code drift).

## Non-goals

- Replacing Claude Code's terminal, git, or LSP features — jig stays a
  server, not a client.
- Packaging MCPs. Users bring their own; jig proxies them.
- GUI. The desktop app (agentcockpit) is archived; jig does not resurrect it.
