# Output contracts — jig delivery handoffs

Minimal handoff rows for serious PRs. This file was introduced for alignment
with the `/proyecto` orchestration style; phases map per `PHASE_ROUTING.md`.

## Branch: `fix/alpha-hardening-roadmap` (0.1.0a29)

### phase-1 (plan) — N/A formal doc

- **Scope:** Close alpha gaps from prior review + ROADMAP 0.1.0 / 0.2.0 items
  that fit one PR (warmup bug, version sync, prefetch UX, asset sweep sample,
  proxy error surfacing, smoke test robustness).
- **Out:** This branch.

### phase-2 (architecture) — N/A new ADR

- **Change:** Embedding warmup must not claim an asyncio loop; subprocess proxy
  errors belong on `McpConnection` and in `jig doctor`.

### phase-3 / 2b / 3b / 4–5 integration

- **SKIP** — see `PHASE_ROUTING.md`.

### phase-4 (implementation)

- **Files:** `src/jig/server.py`, `src/jig/engines/proxy_pool.py`,
  `src/jig/cli/doctor.py`, `src/jig/cli/main.py`, `src/jig/tests/test_smoke.py`,
  bundled assets, `README.md`, `ROADMAP.md`, `CHANGELOG.md`, `pyproject.toml`,
  `src/jig/__init__.py`.

### phase-6 (review)

- **Tools:** `ruff check`, `ruff format --check`, `mypy`, `pytest`.

### phase-7 (qa)

- **Matrix:** Linux CI (existing workflow); local macOS optional.
- **Note:** `jig doctor --prefetch` triggers a large download on first run —
  not executed in default CI unit job unless separately opted in.

### phase-8 (release)

- **Version:** `0.1.0a29` in `pyproject.toml` and `jig.__version__`.
- **Changelog:** `[0.1.0a29] — unreleased` until tag.

### Tooling / quota (rule 1 fallback)

- **Task / subagent delegation:** not used for this PR; single-agent
  implementation. No premium quota block.
