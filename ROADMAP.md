# Roadmap

Status: `0.1.0a1` shipped 2026-04-19 (first alpha, no PyPI release yet).
This document tracks what lands next. Dates are targets, not commitments.

## 0.1.0 — stable alpha (next)

- **Sweep bundled assets for agentcockpit refs.** `src/jig/assets/agents/*.md`,
  `assets/commands/*.md`, `assets/skills/*`, `assets/rules/*.md` still
  contain hardcoded `/var/home/rixmerz/agentcockpit` paths, `agentcockpit-build`
  distrobox references, `.workflow-manager/state/...` paths, and
  descriptions that mention agentcockpit as the host product. These get
  copied into user projects by `jig init` / `deploy_project_agents`
  and will confuse first-time users.


Close the gaps between "all sprints landed" and "users can actually install it".

- **PyPI publication.** `jig-mcp` name reserved, CI `release.yml` wired for
  trusted publishing (GitHub OIDC, no API tokens). Ship first Test PyPI
  dry-run, then promote to PyPI proper once the smoke from a fresh VM passes.
- **Author `docs/`.** The plan called for `architecture.md`, `tools.md`,
  `init.md`, `embeddings.md`, `proxy.md`; directory currently empty. README
  links them, so 404 risk until written.
- **Fresh-VM E2E.** The acceptance criteria at the tail of
  `~/.claude/plans/si-jig-realiza-la-cozy-church.md` (steps 1–18) has not been
  run end-to-end on a clean VM. Blocks release.
- **Model download UX.** First-run fastembed pull is ~1.3 GB and blocks
  server startup. `jig doctor --prefetch` should be documented in the README
  quickstart, not buried.

## 0.2.0 — proxy hardening

- **Reconnect backoff telemetry.** `proxy_pool.py` reconnects silently on
  stale stdio; surface failures in `jig doctor` and `proxy_list`.
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
