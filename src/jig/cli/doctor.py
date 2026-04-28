"""`jig doctor` — diagnostics + repair.

Global checks (always run):
  - Optional ``--prefetch`` (blocking model load before the rest)
  - Python version
  - fastembed importable and model resolvable
  - ~/.config/jig/proxy.toml parseable
  - Subprocess proxy ``last_error`` snapshot (from the pool, if any)
  - Embedding cache DB writable
  - XDG paths exist / creatable
  - git available (and whether cwd is a repo)

Per-project checks (``--project <path>``):
  - .claude/settings.json exists and its hook commands point at an
    absolute python that can import jig (not the bare ``python3`` that
    0.1.0a24 and earlier shipped).
  - .claude/hooks/*.py are present and executable.
  - .claude/rules/jig-methodology.md is present (sanity: jig_init was
    run with a modern version).

Repair (``--repair``):
  - Rewrites stale ``python3`` to ``sys.executable`` in settings.json.
  - ``chmod +x`` on hook scripts that exist but aren't executable.
  - Recopies missing hook files from the wheel.

``--dry-run`` shows the plan without touching anything.

``--prefetch`` loads the fastembed model (blocking) so later
``proxy_tools_search`` calls are fast; intended for post-install or CI images.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import difflib
import hashlib
import os
import re
import shutil
import sqlite3
import sys
from importlib import resources
from pathlib import Path

from jig import __version__
from jig.core import embeddings, paths

# Hook files that every jig-scaffolded project is expected to have.
# Keep in sync with ``cli.init_cmd._copy_assets``.
_EXPECTED_HOOKS: frozenset[str] = frozenset({
    "_common.py",
    "dcc_feedback.py",
    "experience_injector.py",
    "experience_recorder.py",
    "graph_enforcer.py",
    "lsp_status_check.py",
    "memory_injector.py",
    "session_bootstrap.py",
    "session_knowledge_capture.py",
    "smart_context.py",
    "snapshot_trigger.py",
    "style_guard.py",
    "user_memory_injector.py",
    "workflow_enforcer.py",
    "workflow_post_traverse.py",
})


def run(args: argparse.Namespace) -> int:
    if getattr(args, "prefetch", False):
        prefetch_rc = _run_embedding_prefetch()
        if prefetch_rc != 0:
            return prefetch_rc

    findings: list[tuple[str, str, str]] = []  # (status, name, note); status ∈ {✓, ✗, !}

    findings.append(_check_python())
    findings.append(_check_fastembed())
    findings.append(_check_paths())
    findings.append(_check_cache_writable())
    findings.append(_check_proxy_config())
    findings.append(_check_proxy_last_errors())
    findings.append(_check_git())

    project = getattr(args, "project", None)
    repair_plan: list[tuple[str, object]] = []  # (action, payload)
    if project:
        proj = Path(project).expanduser().resolve()
        if not proj.is_dir():
            print(f"jig doctor: --project path not a directory: {proj}", file=sys.stderr)
            return 2
        claude_dir = proj / ".claude"
        settings_path = claude_dir / "settings.json"
        hooks_dir = claude_dir / "hooks"

        findings.append(_check_settings_exists(settings_path))
        stale = _stale_hook_commands(settings_path)
        if stale:
            findings.append((
                "✗",
                "settings.json hooks",
                f"{len(stale)} hook(s) use bare `python3` — pre-a25 scaffold",
            ))
            repair_plan.append(("rewrite-settings", settings_path))
        elif settings_path.is_file():
            findings.append(("✓", "settings.json hooks", "hooks use absolute python path"))

        hook_status = _check_hooks_dir(hooks_dir)
        findings.append(hook_status[0])
        if hook_status[1]:
            repair_plan.append(("restore-hooks", (hooks_dir, hook_status[1])))
        if hook_status[2]:
            repair_plan.append(("chmod-hooks", (hooks_dir, hook_status[2])))

        drifted = _drifted_hooks(hooks_dir)
        if drifted:
            findings.append((
                "!",
                "hook content drift",
                f"{len(drifted)} hook(s) differ from bundled wheel (may be customised)",
            ))
            # Drift repair is opt-in destructive — don't add to plan
            # automatically; advertise it in the report so users have
            # to think before overwriting their edits.
        elif hook_status[0][0] == "✓":
            findings.append(("✓", "hook content drift", "hooks match bundled version"))

        rules_dir = claude_dir / "rules"
        has_methodology = (rules_dir / "jig-methodology.md").is_file()
        findings.append((
            "✓" if has_methodology else "!",
            "jig-methodology rule",
            "present" if has_methodology else "missing — re-run jig_init_project",
        ))

        dcc_state = _check_dcc_injection(proj)
        if dcc_state is not None:
            findings.append(dcc_state)

    passed = sum(1 for s, *_ in findings if s == "✓")
    total = len(findings)
    print(f"jig doctor — v{__version__}")
    if project:
        print(f"  project: {project}")
    print("=" * 62)
    for status, name, note in findings:
        print(f"  [{status}] {name:<32} {note}")
    print("=" * 62)
    print(f"  {passed}/{total} checks passed")

    if getattr(args, "repair", False):
        if not repair_plan:
            print("\nNothing to repair.")
            return 0 if passed == total else 1
        print("\nRepair plan:")
        for action, payload in repair_plan:
            print(f"  - {_describe_repair(action, payload)}")
        if getattr(args, "dry_run", False):
            diffs = _render_dry_run_diffs(repair_plan)
            if diffs:
                print()
                print(diffs)
            print("\n(dry run — no changes made)")
            return 0
        print()
        for action, payload in repair_plan:
            _apply_repair(action, payload)
            print(f"  ✓ {_describe_repair(action, payload)}")
        print("\nRepair complete. Re-run `jig doctor --project <path>` to verify.")
        return 0

    return 0 if passed == total else 1


# ---------------------------------------------------------------------------
# Global checks
# ---------------------------------------------------------------------------


def _check_python() -> tuple[str, str, str]:
    v = sys.version_info
    ok = (v.major, v.minor) >= (3, 10)
    return ("✓" if ok else "✗", "Python 3.10+", f"found {v.major}.{v.minor}.{v.micro}")


def _check_fastembed() -> tuple[str, str, str]:
    try:
        import fastembed  # noqa: F401

        model = embeddings.resolve_model()
        return ("✓", "fastembed importable", f"model={model}")
    except ImportError as e:
        return ("✗", "fastembed importable", str(e))


def _check_paths() -> tuple[str, str, str]:
    tries = []
    for name, fn in [
        ("config", paths.config_dir),
        ("data", paths.data_dir),
        ("cache", paths.cache_dir),
    ]:
        try:
            paths.ensure(fn())
            tries.append(f"{name}=ok")
        except OSError as e:
            return ("✗", "XDG paths writable", f"{name}: {e}")
    return ("✓", "XDG paths writable", ", ".join(tries))


def _check_cache_writable() -> tuple[str, str, str]:
    try:
        path = paths.ensure(paths.data_dir()) / "doctor-probe.sqlite"
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE IF NOT EXISTS t (x INTEGER)")
        conn.close()
        path.unlink(missing_ok=True)
        return ("✓", "SQLite cache writable", str(paths.data_dir()))
    except (sqlite3.DatabaseError, OSError) as e:
        return ("✗", "SQLite cache writable", str(e))


def _check_proxy_config() -> tuple[str, str, str]:
    from jig.engines import proxy_pool

    configs = proxy_pool.load_proxy_configs()
    return (
        "✓",
        "proxy.toml parseable",
        f"{len(configs)} proxies at {proxy_pool.proxy_config_path()}",
    )


def _run_embedding_prefetch() -> int:
    """Blocking load of the default embedding model (may download on first run)."""
    print(
        "Prefetching embedding model (first run may download up to ~1.3 GB)…",
        file=sys.stderr,
    )
    emb = embeddings.get_embedder()
    if not emb.available:
        print("fastembed is not available — install jig with its dependencies.", file=sys.stderr)
        return 1
    vec = emb.embed_one("jig doctor --prefetch warmup")
    if vec is None:
        print("Embedding model failed to load — see logs above.", file=sys.stderr)
        return 1
    print(
        f"Embedding model ready (dim={len(vec)}, model={embeddings.resolve_model()}).",
        file=sys.stderr,
    )
    return 0


def _check_proxy_last_errors() -> tuple[str, str, str]:
    """Surface recent proxy subprocess errors (see ROADMAP 0.2 telemetry)."""
    from jig.engines import proxy_pool

    try:
        statuses = asyncio.run(proxy_pool.proxy_statuses())
    except Exception as e:
        return ("!", "proxy subprocess errors", f"status query failed: {e}")
    errs = [f"{s.name}: {s.last_error}" for s in statuses if s.last_error]
    if not statuses:
        return ("✓", "proxy subprocess errors", "no subprocess proxies configured")
    if not errs:
        return ("✓", "proxy subprocess errors", "no recorded errors on pooled connections")
    note = "; ".join(errs[:4])
    if len(errs) > 4:
        note += f" … (+{len(errs) - 4} more)"
    return ("!", "proxy subprocess errors", note)


def _check_git() -> tuple[str, str, str]:
    if shutil.which("git") is None:
        return ("✗", "git available", "git not on PATH — snapshots disabled")
    try:
        cwd = Path.cwd()
        import subprocess

        r = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode == 0:
            return ("✓", "git available (in a repo)", "refs/jig/snapshots/ ready")
        return ("✓", "git available (not a repo)", "not a git repo here")
    except Exception as e:
        return ("✗", "git available", str(e))


# ---------------------------------------------------------------------------
# Project checks + repair hooks
# ---------------------------------------------------------------------------


def _check_settings_exists(settings_path: Path) -> tuple[str, str, str]:
    if settings_path.is_file():
        return ("✓", "settings.json present", str(settings_path))
    return ("✗", "settings.json present", "missing — run jig_init_project first")


_STALE_CMD_RE = re.compile(r'"command"\s*:\s*"python3\s')


def _stale_hook_commands(settings_path: Path) -> list[str]:
    if not settings_path.is_file():
        return []
    try:
        raw = settings_path.read_text(encoding="utf-8")
    except OSError:
        return []
    matches = _STALE_CMD_RE.findall(raw)
    return matches


def _check_hooks_dir(hooks_dir: Path) -> tuple[tuple[str, str, str], list[str], list[str]]:
    """Return ((status, name, note), missing_hooks, non_executable_hooks)."""
    if not hooks_dir.is_dir():
        return (
            ("✗", "hooks/ directory", f"missing: {hooks_dir}"),
            list(_EXPECTED_HOOKS),
            [],
        )
    present = {p.name for p in hooks_dir.iterdir() if p.is_file()}
    missing = sorted(_EXPECTED_HOOKS - present)
    non_exec = sorted(
        p.name for p in hooks_dir.iterdir()
        if p.is_file() and p.suffix == ".py" and not os.access(p, os.X_OK)
    )
    parts = []
    if missing:
        parts.append(f"{len(missing)} missing")
    if non_exec:
        parts.append(f"{len(non_exec)} not executable")
    note = ", ".join(parts) if parts else f"all {len(_EXPECTED_HOOKS)} present"
    status = "✓" if not (missing or non_exec) else "!"
    return (
        (status, "hooks/ scripts", note),
        missing,
        non_exec,
    )


def _drifted_hooks(hooks_dir: Path) -> list[str]:
    """Return hook filenames whose content hash differs from the wheel bundle."""
    if not hooks_dir.is_dir():
        return []
    try:
        import jig.hooks as hooks_pkg
        bundled = resources.files(hooks_pkg)
    except Exception:
        return []
    drift: list[str] = []
    for p in hooks_dir.iterdir():
        if not p.is_file() or p.name not in _EXPECTED_HOOKS:
            continue
        try:
            local = p.read_bytes()
            src_entry = bundled / p.name
            if not src_entry.is_file():
                continue
            src = src_entry.read_bytes()
        except OSError:
            continue
        if hashlib.sha256(local).digest() != hashlib.sha256(src).digest():
            drift.append(p.name)
    return sorted(drift)


def _count_dcc_project_files(db_path: Path, project_dir: str) -> int:
    """Return count of code_points rows whose file_path starts with project_dir.

    Returns -1 if the query fails (caller should not emit a false alarm).
    """
    import sqlite3 as _sqlite3
    try:
        conn = _sqlite3.connect(str(db_path), timeout=2)
        cur = conn.execute(
            "SELECT COUNT(*) FROM code_points WHERE file_path LIKE ? ESCAPE '\\'",
            (project_dir.rstrip("/") + "/%",),
        )
        count: int = cur.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return -1


def _check_dcc_injection(project_dir: Path) -> tuple[str, str, str] | None:
    """Warn when DCC has indexed data but dcc_injection is disabled.

    Returns None when nothing actionable to report (no config, no DB).
    """
    db_path = paths.data_dir() / "dcc.db"
    dcc_indexed = db_path.exists() and db_path.stat().st_size > 0
    try:
        from jig.engines.hub_config import load_enforcer_config
        cfg = load_enforcer_config(str(project_dir))
    except Exception:
        cfg = {}
    injection_enabled = cfg.get("dcc_injection_enabled", True)
    mid_phase_enabled = cfg.get("mid_phase_dcc", True)
    if not dcc_indexed:
        return ("!", "DCC indexed", "no dcc.db yet — run cube_index_project once")
    if not injection_enabled or not mid_phase_enabled:
        details = []
        if not injection_enabled:
            details.append("dcc_injection_enabled=false")
        if not mid_phase_enabled:
            details.append("mid_phase_dcc=false")
        return ("!", "DCC injection config", ", ".join(details) + " — smells won't auto-inject")
    count = _count_dcc_project_files(db_path, str(project_dir))
    if count == 0:
        return ("!", "DCC injection config", "dcc.db has data but 0 files from this project — run cube_index_directory(path='src/')")
    if count > 0:
        return ("✓", "DCC injection config", f"indexed + injection enabled ({count} files)")
    return ("✓", "DCC injection config", "indexed + injection enabled")


def _render_dry_run_diffs(plan: list[tuple[str, object]]) -> str:
    """For each ``rewrite-settings`` entry, produce a unified diff so the
    user can see exactly what changes before approving."""
    chunks: list[str] = []
    for action, payload in plan:
        if action != "rewrite-settings":
            continue
        settings_path = payload
        if not settings_path.is_file():
            continue
        before = settings_path.read_text(encoding="utf-8")
        after = before.replace(
            '"command": "python3 ',
            f'"command": "{sys.executable} ',
        )
        if before == after:
            continue
        diff = difflib.unified_diff(
            before.splitlines(keepends=False),
            after.splitlines(keepends=False),
            fromfile=str(settings_path),
            tofile=f"{settings_path} (after repair)",
            lineterm="",
        )
        chunks.append("\n".join(diff))
    if not chunks:
        return ""
    return "Diff preview:\n" + "\n\n".join(chunks)


def _describe_repair(action: str, payload) -> str:
    if action == "rewrite-settings":
        return f"rewrite bare `python3` in {payload} → {sys.executable}"
    if action == "restore-hooks":
        hooks_dir, missing = payload
        return f"copy {len(missing)} missing hook(s) into {hooks_dir}/"
    if action == "chmod-hooks":
        hooks_dir, non_exec = payload
        return f"chmod +x {len(non_exec)} hook(s) in {hooks_dir}/"
    return f"{action}: {payload}"


def _apply_repair(action: str, payload) -> None:
    if action == "rewrite-settings":
        settings_path = payload
        raw = settings_path.read_text(encoding="utf-8")
        rewired = raw.replace(
            '"command": "python3 ',
            f'"command": "{sys.executable} ',
        )
        settings_path.write_text(rewired, encoding="utf-8")
        return
    if action == "restore-hooks":
        hooks_dir, missing = payload
        hooks_dir.mkdir(parents=True, exist_ok=True)
        import jig.hooks as hooks_pkg
        hooks_path = resources.files(hooks_pkg)
        for entry in hooks_path.iterdir():
            if entry.name in missing and entry.is_file():
                (hooks_dir / entry.name).write_bytes(entry.read_bytes())
        return
    if action == "chmod-hooks":
        hooks_dir, non_exec = payload
        for name in non_exec:
            p = hooks_dir / name
            with contextlib.suppress(OSError):
                p.chmod(p.stat().st_mode | 0o111)
        return


__all__ = ["run"]
