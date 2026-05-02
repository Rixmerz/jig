# Phase routing — jig repository

This repo is a **Python MCP library/CLI**, not a Cocha BFF + SPA deliverable. The
orchestrator map in the `/proyecto` Cursor command is adapted as follows.

| Standard phase | Applies to jig? | Notes |
|----------------|-----------------|-------|
| phase-1 plan | Yes (light) | Problem/scope captured in ROADMAP + Issues. |
| phase-2 architecture | Yes (light) | `docs/architecture.md`, subsystem boundaries. |
| phase-2b API contract | **SKIP** | No public HTTP API contract for this package. |
| phase-3 spec | **Partial** | Readiness: tests + `docs/tools.md` as tool contract. |
| phase-3b Cocha generators | **SKIP** | Not Java/Node/Angular from Bitbucket templates. |
| phase-4 backend | Yes | Python implementation work in `src/jig/`. |
| phase-5 frontend | **SKIP** | No SPA in this repo. |
| phase-04-05 integration | **Replaced** | `docs/pipeline/INTEGRATION_SMOKE.md` (wheel, pytest, stdio, doctor) — not CORS. |
| phase-6 review | Yes | PR / self-review + ruff/mypy. |
| phase-7 qa | Yes | `pytest`, CI matrix. |
| phase-8 release | Yes | Version bump, CHANGELOG, tag, PyPI when ready. |

## Supporting docs (this repo)

| Document | Role |
|----------|------|
| `OUTPUT_CONTRACTS.md` | Full handoff: phases, ROADMAP matrix, waivers. |
| `INTEGRATION_SMOKE.md` | Non-web integration gate for jig. |
| `ALIGNMENT_PROJECT_FLOW.md` | How this repo coexists with Cocha Infra elsewhere. |
| `SETUP_AND_TOOLKIT.md` | `uv`/`README` for jig; Cocha toolkit is out-of-tree. |

## Waivers

- **Cocha 3b / BFF+SPA CORS integration:** not applicable. Use `INTEGRATION_SMOKE.md`
  for the **MCP/CLI** gate. Full detail in `OUTPUT_CONTRACTS.md` (*/proyecto* **abarcalo**).
