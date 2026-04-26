"""`jig update` — upgrade jig itself and resync all scaffolded projects.

Steps:
  1. Run `uv tool upgrade jig-mcp` to pull the latest version
  2. For each --project path given (or CWD if it looks like a jig project),
     run `jig resync` to propagate new hooks/rules/assets

Usage:
    jig update                        # upgrade + resync CWD if it's a jig project
    jig update --project /a --project /b   # upgrade + resync specific projects
    jig update --no-resync            # upgrade only, skip project resync
    jig update --dry-run              # show what would happen
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "update",
        help="Upgrade jig-mcp and resync scaffolded projects",
    )
    p.add_argument(
        "--project",
        action="append",
        dest="projects",
        metavar="PATH",
        default=None,
        help=(
            "Project path(s) to resync after upgrade. "
            "Can be repeated. Defaults to CWD if it contains .claude/."
        ),
    )
    p.add_argument(
        "--no-resync",
        action="store_true",
        help="Upgrade jig only — skip project resync",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without writing anything",
    )
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    dry_run: bool = args.dry_run
    no_resync: bool = args.no_resync

    # Resolve projects to resync
    if no_resync:
        projects: list[Path] = []
    elif args.projects:
        projects = [Path(p).expanduser().resolve() for p in args.projects]
    else:
        cwd = Path.cwd()
        projects = [cwd] if (cwd / ".claude").exists() else []

    # ── Step 1: upgrade jig-mcp ─────────────────────────────────────────────
    print("jig update")
    print()
    print("  Step 1: upgrade jig-mcp via uv tool upgrade")
    if dry_run:
        print("  [dry-run] would run: uv tool upgrade jig-mcp")
    else:
        result = subprocess.run(
            ["uv", "tool", "upgrade", "jig-mcp"],
            capture_output=False,
        )
        if result.returncode != 0:
            print(
                "\n[jig.update] uv tool upgrade failed — "
                "is jig-mcp installed as a uv tool? "
                "Run: uv tool install git+https://github.com/Rixmerz/jig",
                file=sys.stderr,
            )
            return result.returncode
    print()

    # ── Step 2: resync each project ──────────────────────────────────────────
    if not projects:
        if not no_resync:
            print("  No jig projects to resync (pass --project PATH to specify one).")
        print()
        print(" ─── jig update complete ─── ")
        return 0

    print(f"  Step 2: resync {len(projects)} project(s)")
    for p in projects:
        print(f"    • {p}")
    print()

    from jig.cli.resync_cmd import run as resync_run

    errors = 0
    for project in projects:
        resync_args = argparse.Namespace(
            path=str(project),
            agents=None,
            dry_run=dry_run,
        )
        code = resync_run(resync_args)
        if code != 0:
            errors += 1

    print()
    print(" ─── jig update complete ─── ")
    if errors:
        print(f"   {errors} project(s) failed to resync — check output above")
        return 1

    print("   Reconnect jig in Claude Code via /mcp")
    return 0
