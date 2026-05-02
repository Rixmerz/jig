# Handoff — línea 0.1.0a29 (alpha)

Este documento resume lo incorporado en la rama de trabajo hacia **estable 0.1.0**,
para **onboarding** y **revisión de PR** sin depender del hilo de chat.

## Alcance de la entrega (commits agrupados)

1. **Servidor MCP**
   - Warmup de embeddings en **hilo daemon** + carga síncrona (antes: event loop sin ejecutar).
2. **CLI y diagnóstico**
   - `jig doctor --prefetch` (descarga/carga del modelo de embeddings).
   - `jig doctor`: visibilidad de `last_error` de proxies subprocess.
3. **Proxy**
   - `McpConnection.last_error` rellenado en más fallos; limpieza en `tools/call` exitoso.
   - `proxy_config_path()`: anotación con `pathlib.Path`.
4. **Tests**
   - Smoke: `python -m jig` con `PYTHONPATH` hacia `src` en checkouts sin editable install.
   - Tests para `_check_proxy_last_errors` (mock de `proxy_statuses`).
5. **Assets**
   - Rutas neutrales en `mcp-developer.md` y `skills/debug/SKILL.md` (sin máquina concreta).
6. **Documentación de producto**
   - README: prefetch, versión **0.1.0a29**; `ROADMAP` / `CHANGELOG` alineados en evolución.
7. **Pipeline `/proyecto`**
   - `docs/pipeline/OUTPUT_CONTRACTS.md` (fases, waivers, matriz ROADMAP).
   - `INTEGRATION_SMOKE.md` (gate MCP/CLI, no CORS).
   - `ALIGNMENT_PROJECT_FLOW.md`, `SETUP_AND_TOOLKIT.md`, `PHASE_ROUTING.md` actualizado.
8. **Pre-commit**
   - `pre-commit-hooks` v6; comprobaciones extra; **Ruff / ruff-format / mypy** en etapa `manual`
     para no bloquear commits por deuda global de lint/tipos.
   - `hooks/lsp_status_check.py`: f-string compatible con **Python 3.10** (hook `debug-statements`).
9. **Tipos (core)**
   - `session.py`, `embeddings.py`, `snapshots.py` — mypy en `src/jig/core` limpio.
   - Ajustes menores en `guide.py`, `experience.py`.

## Estado de calidad conocido (post-check)

| Comando | Estado típico del repo completo |
|---------|----------------------------------|
| `pytest src/jig/tests` | **Verde** |
| `ruff check .` | **Rojo** (~cientos de hallazgos; deuda acumulada) |
| `mypy` (ámbito pyproject) | **Rojo** (mucho en `engines/`, DCC) |

**CI (`.github/workflows/test.yml`)** sigue ejecutando ruff + mypy: conviene
plan explícito de **bajar deuda** o ajustar alcance de CI (issue separado).

## Rama Git sugerida para PR

- `release/0.1.0a29-handoff` — documentación + historial de commits de alpha-hardening.

## Próximos pasos (ROADMAP)

- PyPI + E2E en VM limpia.
- Límites de proxy / telemetría (0.2.0).
- Reducir hallazgos `ruff` / `mypy` a nivel de repo o acotar gates de CI.
