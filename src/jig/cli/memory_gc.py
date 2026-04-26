"""memory-gc — garbage collect stale Claude Code memory files.

Operates on ~/.claude/projects/*/memory/ across all projects.
Memory files are user-level (not repo-level); this tool just maintains them.

Usage via jig CLI:
    jig memory-gc           dry-run (show what would happen)
    jig memory-gc --apply   move expired files to memory/archive/
    jig memory-gc --stats   only print token/file stats
"""
from __future__ import annotations

import argparse
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path

PROJECTS_ROOT = Path.home() / ".claude" / "projects"
CHARS_PER_TOKEN = 4


def _parse_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end == -1:
        return {}
    fm: dict = {}
    for line in text[3:end].splitlines():
        if ":" in line and not line.startswith(" "):
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()
        elif line.startswith("  - "):
            last_key = list(fm.keys())[-1] if fm else None
            if last_key:
                if not isinstance(fm[last_key], list):
                    fm[last_key] = []
                fm[last_key].append(line.strip().lstrip("- "))
    return fm


def _parse_ttl(ttl_str: str) -> timedelta | None:
    m = re.match(r"^(\d+)([dhw])$", ttl_str.strip())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    return timedelta(days=n if unit == "d" else n * 7 if unit == "w" else n / 24)


def _find_memory_files():
    if not PROJECTS_ROOT.exists():
        return
    for project_dir in PROJECTS_ROOT.iterdir():
        memory_dir = project_dir / "memory"
        if not memory_dir.is_dir():
            continue
        for f in memory_dir.glob("*.md"):
            if f.name == "MEMORY.md":
                continue
            yield f


def _rebuild_index(memory_dir: Path, active_files: list[Path]) -> None:
    lines = []
    for f in sorted(active_files):
        fm = _parse_frontmatter(f.read_text())
        name = fm.get("name", f.stem)
        desc = fm.get("description", "")
        priority = fm.get("priority", "normal")
        links_raw = fm.get("links", [])
        marker = " ⚡" if priority == "high" else ""
        links_str = f" → {', '.join(links_raw)}" if links_raw else ""
        lines.append(f"- [{name}]({f.name}){marker} — {desc}{links_str}\n")
    (memory_dir / "MEMORY.md").write_text("".join(lines))


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "memory-gc",
        help="Garbage collect stale user-level memory files (~/.claude/projects/*/memory/)",
    )
    group = p.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="Move expired files to archive/")
    group.add_argument("--stats", action="store_true", help="Print stats only")
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    now = datetime.now()
    total_files = 0
    expired: list[Path] = []
    active_by_dir: dict[Path, list[Path]] = {}

    for f in _find_memory_files():
        total_files += 1
        memory_dir = f.parent
        active_by_dir.setdefault(memory_dir, [])

        fm = _parse_frontmatter(f.read_text())
        ttl_str = fm.get("ttl", "")
        if ttl_str:
            ttl = _parse_ttl(ttl_str)
            if ttl and (now - datetime.fromtimestamp(f.stat().st_mtime)) > ttl:
                expired.append(f)
                continue

        active_by_dir[memory_dir].append(f)

    total_index_chars = sum(
        len((d / "MEMORY.md").read_text()) if (d / "MEMORY.md").exists() else 0
        for d in active_by_dir
    )
    active_count = total_files - len(expired)
    print(f"Files: {total_files} total, {active_count} active, {len(expired)} expired")
    print(f"Index tokens (est): {total_index_chars // CHARS_PER_TOKEN}")

    if args.stats:
        return 0

    if not expired:
        print("Nothing to archive.")
        return 0

    for f in expired:
        archive_dir = f.parent / "archive"
        action = "would archive" if not args.apply else "archiving"
        print(f"  {action}: {f.relative_to(PROJECTS_ROOT)}")
        if args.apply:
            archive_dir.mkdir(exist_ok=True)
            shutil.move(str(f), archive_dir / f.name)

    if args.apply:
        for memory_dir, active_files in active_by_dir.items():
            _rebuild_index(memory_dir, active_files)
        print("MEMORY.md indexes rebuilt.")
    else:
        print("(dry-run) Pass --apply to execute.")

    return 0
