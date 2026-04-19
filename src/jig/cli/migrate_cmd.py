"""`jig migrate` — move legacy ~/.workflow-manager/ data into XDG.

Until a user runs this, jig reads from ~/.workflow-manager/ as a
fallback (XDG-first, legacy-fallback resolution in ``experience_memory``
and ``tool_index``). Running ``jig migrate`` makes the XDG location
authoritative and optionally removes the legacy tree.

Files handled:
    ~/.workflow-manager/experience_memory.json
    ~/.workflow-manager/project_memories/<name>/experience_memory.json
    ~/.workflow-manager/learned_weights.json

Behavior:
    - Copy each legacy path to its XDG counterpart if the XDG file is
      missing. Never overwrite existing XDG data.
    - ``--dry-run`` prints the plan without touching anything.
    - ``--delete-legacy`` removes the legacy source after a successful
      copy of every entry.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from jig.core import paths


LEGACY_ROOT = Path.home() / ".workflow-manager"


def run(args: argparse.Namespace) -> int:
    xdg = paths.data_dir()

    legacy_global = LEGACY_ROOT / "experience_memory.json"
    xdg_global = xdg / "experience_memory.json"

    legacy_projects = LEGACY_ROOT / "project_memories"
    xdg_projects = xdg / "project_memories"

    legacy_weights = LEGACY_ROOT / "learned_weights.json"
    xdg_weights = xdg / "learned_weights.json"

    plan: list[tuple[Path, Path, str]] = []

    if legacy_global.exists():
        if xdg_global.exists():
            plan.append((legacy_global, xdg_global, "skip: XDG path exists"))
        else:
            plan.append((legacy_global, xdg_global, "copy"))

    if legacy_weights.exists():
        if xdg_weights.exists():
            plan.append((legacy_weights, xdg_weights, "skip: XDG path exists"))
        else:
            plan.append((legacy_weights, xdg_weights, "copy"))

    if legacy_projects.is_dir():
        for child in sorted(legacy_projects.iterdir()):
            if not child.is_dir():
                continue
            src = child / "experience_memory.json"
            dst = xdg_projects / child.name / "experience_memory.json"
            if not src.exists():
                continue
            if dst.exists():
                plan.append((src, dst, "skip: XDG path exists"))
            else:
                plan.append((src, dst, "copy"))

    if not plan:
        print("[jig.migrate] nothing to migrate — no legacy data found")
        return 0

    for src, dst, action in plan:
        print(f"  [{action}]  {src}  →  {dst}")

    if args.dry_run:
        return 0

    copied = 0
    for src, dst, action in plan:
        if action != "copy":
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
    print(f"[jig.migrate] copied {copied} file(s) to {xdg}")

    if args.delete_legacy:
        # Only remove what we actually migrated or that was already stale.
        skipped_because_exists = any(
            action.startswith("skip") for _, _, action in plan
        )
        if skipped_because_exists:
            print(
                "[jig.migrate] --delete-legacy refused: XDG already had some "
                "files, leaving ~/.workflow-manager/ in place so nothing is "
                "lost. Diff and resolve manually, then rerun.",
                file=sys.stderr,
            )
            return 2
        shutil.rmtree(LEGACY_ROOT)
        print(f"[jig.migrate] removed {LEGACY_ROOT}")

    return 0
