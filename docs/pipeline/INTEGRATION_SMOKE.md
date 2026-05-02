# Integration smoke — `jig` (MCP / CLI)

This repository is a **Python MCP server and CLI**, not a browser + BFF stack. The
Cocha-oriented checks in the original *project-flow* (CORS, `localhost` vs
`127.0.0.1`, `bffBaseUrl`) **do not apply** here. This file defines the
**jig-specific** integration gate before calling a release “usable in the wild”.

## Mandatory matrix (jig)

| Step | What | Pass criteria |
|------|------|----------------|
| 1 | Install from source | `uv pip install -e ".[dev]"` (or project-standard install) completes. |
| 2 | Unit tests | `pytest src/jig/tests` exit 0. |
| 3 | Lint (if used in PR) | `ruff check` + `ruff format --check` on touched areas; align with CI. |
| 4 | Wheel smoke | `python -m build` + `pip install dist/*.whl` + `jig --version` + `python -m jig --version` (as in `.github/workflows/test.yml`). |
| 5 | MCP process | `jig-mcp` / `jig serve` starts on stdio without crashing after tool registration (manual or scripted short session). |
| 6 | Doctor (no heavy prefetch in CI) | `jig doctor` global checks; optional `jig doctor --prefetch` on a **fresh VM** or ad hoc (large download). |

## Drift

- If README tool counts or `__version__` / `pyproject.toml` **diverge**, treat as
  **failed integration** until a single source of truth is restored (see
  `OUTPUT_CONTRACTS.md` release section).

## Waiver

- **BFF + SPA CORS matrix:** not applicable; documented waiver for `/proyecto`
  rule 6 when the deliverable is only `jig-mcp`.
