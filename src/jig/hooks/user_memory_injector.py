#!/usr/bin/env python3
"""User Memory Injector — UserPromptSubmit hook.

Injects relevant memories from ~/.jig/memory/ at the start of each prompt.
Memories are user-level (cross-project) — same knowledge across all sessions.

Protocol:
  stdin:  {"session_id": "...", "transcript_path": "...", "hook_event_name": "UserPromptSubmit"}
  stdout: injected context block (shown to Claude as additional context)
  stderr: ignored
  exit 0: always

Selection strategy:
  1. Always include priority:high nodes (safety net)
  2. For remaining budget: score by type, recency, and expiry
  3. Never exceed TOKEN_BUDGET characters total
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

TOKEN_BUDGET = 4000  # chars (~1000 tokens), keep injection lean
MEMORY_DIR = Path.home() / ".jig" / "memory"


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("---", 3)
    if end == -1:
        return {}, text
    fm: dict = {}
    current_list_key: str | None = None
    for line in text[3:end].splitlines():
        if line.startswith("  - ") or line.startswith("- "):
            val = line.strip().lstrip("- ")
            if current_list_key:
                if not isinstance(fm.get(current_list_key), list):
                    fm[current_list_key] = []
                fm[current_list_key].append(val)
        elif ":" in line and not line.startswith(" "):
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            fm[key] = val if val else None
            current_list_key = key if not val else None
        else:
            current_list_key = None
    body = text[end + 3:].lstrip("\n")
    return fm, body


def _parse_ttl(ttl_str: str) -> float | None:
    """Return TTL in seconds, or None if unparseable."""
    import re
    m = re.match(r"^(\d+)([dhw])$", ttl_str.strip())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    mult = {"d": 86400, "h": 3600, "w": 604800}
    return n * mult.get(unit, 86400)


def _load_memories() -> list[dict]:
    if not MEMORY_DIR.exists():
        return []
    nodes = []
    for f in MEMORY_DIR.glob("*.md"):
        try:
            fm, body = _parse_frontmatter(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        ttl_str = fm.get("ttl", "")
        if ttl_str:
            ttl_secs = _parse_ttl(ttl_str)
            if ttl_secs is not None:
                age = time.time() - f.stat().st_mtime
                if age > ttl_secs:
                    continue  # expired
        nodes.append({
            "id": fm.get("id") or f.stem,
            "name": fm.get("name", f.stem),
            "description": fm.get("description", ""),
            "type": fm.get("type", "reference"),
            "tags": fm.get("tags") or [],
            "priority": fm.get("priority", "normal"),
            "mtime": f.stat().st_mtime,
            "body": body,
        })
    return nodes


def _score(node: dict) -> float:
    priority_boost = {"high": 1.0, "normal": 0.0, "low": -0.5}.get(node["priority"], 0.0)
    # type weight: feedback and user knowledge are most actionable
    type_boost = {"feedback": 0.3, "user": 0.2, "project": 0.1, "reference": 0.0}.get(node["type"], 0.0)
    recency = 1.0 / (1.0 + (time.time() - node["mtime"]) / 86400)
    return priority_boost + type_boost + recency * 0.1


def _format(node: dict) -> str:
    parts = [f"[{node['type']}] {node['name']}"]
    if node["description"]:
        parts.append(node["description"])
    if node["body"].strip():
        parts.append(node["body"].strip())
    return "\n".join(parts)


def main() -> None:
    try:
        json.load(sys.stdin)  # consume stdin (required by hook protocol)
    except Exception:
        pass

    nodes = _load_memories()
    if not nodes:
        sys.exit(0)

    # Always include high-priority; fill remaining budget by score
    high = [n for n in nodes if n["priority"] == "high"]
    rest = sorted(
        [n for n in nodes if n["priority"] != "high"],
        key=_score,
        reverse=True,
    )
    ordered = high + rest

    selected: list[str] = []
    used = 0
    for node in ordered:
        block = _format(node)
        if used + len(block) > TOKEN_BUDGET:
            break
        selected.append(block)
        used += len(block) + 1

    if not selected:
        sys.exit(0)

    header = "## Jig Memory (cross-project knowledge)\n"
    print(header + "\n\n---\n\n".join(selected))
    sys.exit(0)


if __name__ == "__main__":
    main()
