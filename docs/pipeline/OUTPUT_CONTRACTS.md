# Output contracts — full `/proyecto` handoff (jig)

This document **covers** the phase model from the `/proyecto` Cursor command for
the **jig** repository: product focus, implementation, quality, release, and
**full `ROADMAP.md` traceability**. Phases that target Cocha BFF+SPA or
Bitbucket generators are **SKIP** with an explicit waiver (see
`PHASE_ROUTING.md`).

**Subagent rule:** where the command expects `planner`, `architect`, `review`,
`qa`, `release`, etc., this project may execute work in a **single session**; if
so, the same *role intent* (plan, design, review) is still applied and noted
here under *Delegation*.

---

## Executive summary

| Item | Value |
|------|--------|
| Product | `jig-mcp` — MCP server + CLI for tool proxying, workflows, memory, DCC, snapshots. |
| Current version line | Aligned in `pyproject.toml` and `jig.__version__` (see `CHANGELOG.md`). |
| ROADMAP source of truth | `ROADMAP.md` at repository root. |
| Integration gate (this repo) | `docs/pipeline/INTEGRATION_SMOKE.md` (not CORS). |

---

## phase-1 — plan (`planner`)

**Problem / opportunity**

- Reduce MCP tool-schema **token** load; unify external MCPs behind one **proxy**; offer **phase-gated workflows** and project memory.

**Scope (in / out)**

- **In:** Python package `src/jig/`, docs under `docs/`, bundled `assets/`, GitHub CI, future PyPI.
- **Out:** Shipping third-party MCP binaries; replacing Claude Code or Cursor as an IDE; GUI (per ROADMAP non-goals).

**User stories (representative)**

1. As a developer, I register one MCP (`jig`) and still reach **all** my tools via search + `execute_mcp_tool`.
2. As a user, I run `jig init` / `jig_init_project` to scaffold project automation.
3. As an operator, I run `jig doctor` to verify **embeddings**, **proxy** config, and (optional) project hooks.

**Acceptance criteria (product)**

- [ ] README matches **install** story (`uv tool install` / git URL) and points to **prefetch** / first-run embedding cost.
- [ ] ROADMAP **milestones** have a clear owner (Issues) or are explicitly **deferred** with version tags.

**Risks**

- **Scope creep** across DCC + graph + proxy + memory — mitigate with versioned ROADMAP and small releases.
- **OS parity** (Windows) tracked in ROADMAP 0.2.0+.

*Delegation: single maintainer or squad discussion; no separate `planner` subagent required if documented here.*

---

## phase-2 — architecture (`architect`)

**Design anchors**

- `docs/architecture.md` — FastMCP stdio, `tools/` vs `engines/`, internal vs subprocess proxies, data paths.
- **NFRs:** no daemon; local-first; secrets not in repo (per project rules).

**ADR (short)**

- **MCP as single entry:** proxy pool + embed cache is intentional for token economy; alternatives (many MCPs registered) are explicitly rejected for the default experience.

*Delegation: `architect` subagent optional; same content can be a PR description referencing `docs/architecture.md`.*

**SKIP for jig:** new microservice split — **N/A** unless a major fork (document then).

---

## phase-2b — API contract (`architect`) — **SKIP (waiver)**

- **Reason:** no public HTTP/OpenAPI for end users; integration is **MCP + JSON** over stdio. Contract is **tool schemas** exposed by FastMCP and **documented in `docs/tools.md`**.

---

## phase-3 — spec / readiness (`spec` or `architect`)

**Readiness**

- **Behavioral spec = tests** under `src/jig/tests/` + smoke in CI.
- Contract for tools: name + args + return shape; drift caught by **integration** and doc reviews.

*SKIP formal OpenAPI:* not applicable.

---

## phase-3b — Cocha standard generators — **SKIP (waiver)**

- **Reason:** `jig` is not `api-standard-java`, `api-standard-node`, or `wapp-standard-angular` from Bitbucket. No `generate-*` from `cocha-dev-*` in this repository.

---

## phase-4 — implementation — backend / core (`backend`)

**Maps to:** Python work in `src/jig/` (the command’s “backend” is the **library and server**).

**Ongoing / ROADMAP-derived backlog (abrigo completo del ROADMAP)**

| ROADMAP bucket | Item | Suggested type |
|----------------|------|----------------|
| **0.1.0** | PyPI publication, Test PyPI, trusted publishing | `chore` / `ci` + release process |
| **0.1.0** | Fresh-VM E2E (18-step acceptance) | `test` + manual run |
| **0.1.0** | Ongoing asset sweep (no machine-specific paths) | `fix` / `chore` |
| **0.1.0** | Docs + README **tool count** in sync | `docs` + optional guard test |
| **0.2.0** | Reconnect / backoff **metrics** in `proxy_list` (beyond `last_error`) | `feat` + tests |
| **0.2.0** | Per-proxy **resource limits** (`execute_mcp_tool` timeout / memory) | `feat` + `security` review |
| **0.2.0** | Search **quality** (bge-large vs small / hybrid) | `perf` / `feat` + benchmark |
| **0.2.0** | **Windows** subprocess + paths | `fix` + CI matrix (optional) |
| **0.3.0** | `graph_build` **tree preview** on stderr | `ux` + CLI |
| **0.3.0** | **Stack detection** for `deploy_project_agents` | `feat` |
| **0.3.0** | **Hot-reload** skills/rules from hub | `feat` (complex) |
| **0.4.0** | **Cross-project** experience memory | `feat` + privacy review |
| **0.4.0** | **Snapshot search** all projects | `feat` |

---

## phase-5 — frontend — **SKIP (waiver)**

- **Reason:** no React/Angular SPA in this repository. A future **TUI or web** would be a new product decision (excluded from current non-goals).

---

## phase-04-05 — integration (BFF + SPA) — **replaced for jig**

- **Waiver:** Cocha CORS / dual-origin **matrix does not apply**.
- **Jig integration smoke:** `docs/pipeline/INTEGRATION_SMOKE.md` (wheel, pytest, stdio, doctor).

**Pass before declaring a version “shippable” for alpha/beta:** integration section of `INTEGRATION_SMOKE.md` + **green** CI on `main` / release branch.

---

## phase-6 — review (`review` [+ `review-be` / `review-fe` if ever applicable])

| Check | Notes |
|-------|--------|
| `review` | **Python**: SOLID, boundaries `engines/` vs `tools/`, no secret literals. |
| `review-be` | Same as `review` here (single stack). **SKIP** separate FE. |
| Diff size | Large DCC or vendor dirs — require explicit reviewer attention in PR description. |

---

## phase-7 — QA (`qa`)

| Matrix | Details |
|--------|--------|
| **Python** | 3.10, 3.11, 3.12 (see CI matrix), optional 3.13+ as policy evolves. |
| **OS** | `ubuntu-latest`, `macos-latest` (as in `test.yml`). **Windows** when ROADMAP 0.2.0 is addressed. |
| **Origins (browser)** | **N/A** — not a web app. If a future `jig` **local web UI** exists, revisit CORS and add a new subsection to `INTEGRATION_SMOKE.md`. |
| **Traceability** | Each release entry in `CHANGELOG.md` maps to an Issue/PR when possible. |

**Heavy checks:** `jig doctor --prefetch` and first-time model download are **out of default CI** (cost/time); run on **release candidate** or dedicated job.

---

## phase-8 — release (`release`)

- **Version:** SemVer + alpha tags `0.1.0aN` until stable `0.1.0` per ROADMAP.
- **Conventional Commits** per team rules (`feat`/`fix`/`chore`/`docs`/…).
- **Artifacts:** sdist + wheel; PyPI when 0.1.0 **PyPI** milestone is met.
- **Changelog:** `CHANGELOG.md` — `[Unreleased]` or dated sections.

---

## `fix/alpha-hardening-roadmap` (historical handoff, 0.1.0a29)

*Delivered in a previous branch: server embed warmup (daemon thread), `jig doctor --prefetch`, proxy `last_error` surfacing, smoke test `PYTHONPATH`, doc/ROADMAP/CHANGELOG, pipeline stubs.*

---

## Quota / tooling (rule 1)

If `Task` or subagent delegation is unavailable, the orchestrator may complete
**phase-4/6/7** in one thread; note **model used** and any **rate limit** under
the PR and in this file’s *Delegation* line for the relevant phase.

**Latest update:** this file expanded to *abarcar* full ROADMAP + full `/proyecto`
map for the jig library (documentation-only; does not by itself change product
version).
