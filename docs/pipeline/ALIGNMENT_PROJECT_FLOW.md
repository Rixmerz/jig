# Alignment with *project-flow* (Infra / Cocha)

## Summary

- **`jig`** is an upstream open-source **MCP + CLI** package. It is **not** the
  Cocha *cocha-infra-ai-toolkit* delivery nor a generated Java/Node/Angular app.
- The `/proyecto` Cursor command’s **subagent map** (planner, architect, backend,
  frontend, …) still applies **by analogy**: the **orchestrator** (human or
  model) plans work, but **specialist subagents** are only required when the
  team’s tooling can spawn them. If a phase is executed in a **single thread**,
  document that in `OUTPUT_CONTRACTS.md` (rule 1 fallback).

## Avoiding conflict

| Concern | Cocha *project-flow* | This repo (`jig`) |
|--------|------------------------|-------------------|
| Scaffold | `setup.sh`, Bitbucket templates, `generate-*` | `uv tool install` / `jig init`; no Cocha generators. |
| Integration smoke | CORS, BFF+SPA | See `INTEGRATION_SMOKE.md` (wheel, stdio MCP, `doctor`). |
| Rules / skills in repo | May copy `.cursor/` for the app | `jig` ships **bundled assets** for **Claude Code** under `src/jig/assets/`; **Cursor mirror:** `jig emit-cursor`, `jig init --cursor`, or `jig resync --cursor` (see [`docs/cursor-assets.md`](../cursor-assets.md)). |

## When both are used

If a team uses **Cocha Infra** for an application **and** `jig` as the MCP hub:

- Run **Cocha** pipelines for the app repository.
- Run **jig**-specific checks (`pytest`, wheel smoke, `jig doctor`) for the
  `jig` fork or version pin — do not merge the two into one linear phase list
  without a clear handoff.
