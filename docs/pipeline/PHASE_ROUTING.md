# Phase routing — jig repository

This repo is a **Python MCP library/CLI**, not a Cocha BFF + SPA deliverable. The
orchestrator map in the `/proyecto` Cursor command is adapted as follows.

| Standard phase | Applies to jig? | Notes |
|----------------|-----------------|-------|
| phase-1 plan | Yes (light) | Problem/scope captured in ROADMAP + Issues. |
| phase-2 architecture | Yes (light) | `docs/architecture.md`, subsystem boundaries. |
| phase-2b API contract | **SKIP** | No public HTTP API contract for this package. |
| phase-3 spec | **SKIP** | No OpenAPI/spec-first surface; behavior via tests + docs. |
| phase-3b Cocha generators | **SKIP** | Not Java/Node/Angular from Bitbucket templates. |
| phase-4 backend | Partial | Python implementation work in `src/jig/`. |
| phase-5 frontend | **SKIP** | No SPA in this repo. |
| phase-04-05 integration | **SKIP** | No CORS/BFF matrix; integration = pytest + wheel smoke in CI. |
| phase-6 review | Yes | PR / self-review + ruff/mypy. |
| phase-7 qa | Yes | `pytest`, CI matrix. |
| phase-8 release | Yes | Version bump, CHANGELOG, tag, PyPI when ready. |

## Waivers

- **Cocha 3b / integration:** not applicable; documented here so reviewers do
  not expect `docs/pipeline/INTEGRATION_SMOKE.md` gates in this repository.
