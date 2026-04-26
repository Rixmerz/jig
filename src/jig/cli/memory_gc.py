"""memory-gc — garbage collect stale jig user-level memory files.

Operates on ~/.jig/memory/ (the jig store, NOT ~/.claude/).

Usage via jig CLI:
    jig memory-gc           dry-run (show what would happen)
    jig memory-gc --apply   move expired files to ~/.jig/memory/archive/
    jig memory-gc --stats   only print token/file stats
"""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "memory-gc",
        help="Garbage collect stale jig memory files (~/.jig/memory/)",
    )
    group = p.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="Move expired files to archive/")
    group.add_argument("--stats", action="store_true", help="Print stats only")
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    from jig.engines.memory_store import MEMORY_DIR, load_all, CHARS_PER_TOKEN

    all_nodes = load_all()
    active = {k: v for k, v in all_nodes.items() if not v.is_expired()}
    expired = {k: v for k, v in all_nodes.items() if v.is_expired()}

    total_chars = sum(len(n.to_context()) for n in active.values())
    print(f"Files: {len(all_nodes)} total, {len(active)} active, {len(expired)} expired")
    print(f"Store: {MEMORY_DIR}")
    print(f"Context tokens (est): {total_chars // CHARS_PER_TOKEN}")

    if args.stats:
        return 0

    if not expired:
        print("Nothing to archive.")
        return 0

    archive_dir = MEMORY_DIR / "archive"
    for node_id in expired:
        f = MEMORY_DIR / f"{node_id}.md"
        action = "would archive" if not args.apply else "archiving"
        print(f"  {action}: {node_id}.md (expired)")
        if args.apply and f.exists():
            archive_dir.mkdir(exist_ok=True)
            shutil.move(str(f), archive_dir / f.name)

    if args.apply:
        print("Done.")
    else:
        print("(dry-run) Pass --apply to execute.")

    return 0
