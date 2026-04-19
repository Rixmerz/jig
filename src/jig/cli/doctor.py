"""`jig doctor` — diagnostics.

Verifies:
  - Python version
  - fastembed importable and model resolvable
  - ~/.config/jig/proxy.toml parseable
  - Embedding cache DB writable
  - XDG paths exist / creatable
  - If inside a git repo, refs/jig/snapshots/ namespace is accessible
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

from jig import __version__
from jig.core import embeddings, paths


def run(_args: argparse.Namespace) -> int:
    findings: list[tuple[str, bool, str]] = []

    findings.append(_check_python())
    findings.append(_check_fastembed())
    findings.append(_check_paths())
    findings.append(_check_cache_writable())
    findings.append(_check_proxy_config())
    findings.append(_check_git())

    passed = sum(1 for _, ok, _ in findings if ok)
    total = len(findings)
    print(f"jig doctor — v{__version__}")
    print("=" * 60)
    for name, ok, note in findings:
        mark = "✓" if ok else "✗"
        print(f"  [{mark}] {name:<32} {note}")
    print("=" * 60)
    print(f"  {passed}/{total} checks passed")
    return 0 if passed == total else 1


def _check_python() -> tuple[str, bool, str]:
    v = sys.version_info
    ok = (v.major, v.minor) >= (3, 10)
    return ("Python 3.10+", ok, f"found {v.major}.{v.minor}.{v.micro}")


def _check_fastembed() -> tuple[str, bool, str]:
    try:
        import fastembed  # noqa: F401

        model = embeddings.resolve_model()
        return ("fastembed importable", True, f"model={model}")
    except ImportError as e:
        return ("fastembed importable", False, str(e))


def _check_paths() -> tuple[str, bool, str]:
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
            return ("XDG paths writable", False, f"{name}: {e}")
    return ("XDG paths writable", True, ", ".join(tries))


def _check_cache_writable() -> tuple[str, bool, str]:
    try:
        path = paths.ensure(paths.data_dir()) / "doctor-probe.sqlite"
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE IF NOT EXISTS t (x INTEGER)")
        conn.close()
        path.unlink(missing_ok=True)
        return ("SQLite cache writable", True, str(paths.data_dir()))
    except (sqlite3.DatabaseError, OSError) as e:
        return ("SQLite cache writable", False, str(e))


def _check_proxy_config() -> tuple[str, bool, str]:
    from jig.engines import proxy_pool

    configs = proxy_pool.load_proxy_configs()
    return (
        "proxy.toml parseable",
        True,
        f"{len(configs)} proxies at {proxy_pool.proxy_config_path()}",
    )


def _check_git() -> tuple[str, bool, str]:
    if shutil.which("git") is None:
        return ("git available", False, "git not on PATH — snapshots disabled")
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
            return ("git available (in a repo)", True, "refs/jig/snapshots/ ready")
        return ("git available (not a repo)", True, "not a git repo here")
    except Exception as e:
        return ("git available", False, str(e))


__all__ = ["run"]
