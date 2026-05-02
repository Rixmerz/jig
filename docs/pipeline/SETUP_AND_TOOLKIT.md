# Setup and toolkit — `jig` upstream

## Default install (contributors / CI)

- **Python:** 3.10+.
- **Package manager:** `uv` recommended (see `README.md` and `.github/workflows/test.yml`).
- **Dev extras:** `uv pip install -e ".[dev]"` for pytest, ruff, mypy (as configured in `pyproject.toml`).

## Cocha *cocha-infra-ai-toolkit*

Not bundled with `jig`. Teams that use the internal Infra toolkit in **other**
repositories should follow that catalog’s `setup.sh` and skills **there**; this
file exists only to satisfy the `/proyecto` doc index and avoid a dead link.

**For jig development:** the authoritative setup is `README.md` + `docs/testing.md`.
