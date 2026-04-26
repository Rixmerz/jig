"""Jig user-level memory store — ~/.jig/memory/.

Separate from Claude Code's native ~/.claude/projects/*/memory/ system.
Richer schema: TTL, priority, links, tags, source tracking.

Memory file format:
---
id: unique-slug
name: Human title
description: one-line summary
type: feedback | project | user | reference
tags:
  - tag1
  - tag2
links:
  - other-slug
priority: high | normal | low
ttl: 90d           # optional: Nd, Nw, Nh
---
Body content here.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

MEMORY_DIR = Path.home() / ".jig" / "memory"
CHARS_PER_TOKEN = 4


def _ensure_dir() -> Path:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    return MEMORY_DIR


# ── Frontmatter parser ──────────────────────────────────────────────────────

def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (fields_dict, body_text)."""
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


def _serialize_frontmatter(fm: dict, body: str) -> str:
    lines = ["---\n"]
    for key, val in fm.items():
        if isinstance(val, list):
            lines.append(f"{key}:\n")
            for item in val:
                lines.append(f"  - {item}\n")
        elif val is not None:
            lines.append(f"{key}: {val}\n")
    lines.append("---\n")
    if body:
        lines.append("\n" + body.lstrip("\n"))
    return "".join(lines)


def _parse_ttl(ttl_str: str) -> timedelta | None:
    m = re.match(r"^(\d+)([dhw])$", ttl_str.strip())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    return timedelta(days=n if unit == "d" else n * 7 if unit == "w" else n / 24)


# ── Memory node ─────────────────────────────────────────────────────────────

@dataclass
class MemoryNode:
    id: str
    name: str
    description: str
    type: str
    tags: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    priority: str = "normal"
    ttl: str = ""
    body: str = ""
    mtime: float = field(default_factory=time.time)

    def score(self, query_tags: list[str]) -> float:
        if not query_tags:
            return 0.0
        overlap = len(set(self.tags) & set(query_tags))
        similarity = overlap / (len(self.tags) + 1) if self.tags else 0.0
        recency = 1.0 / (1.0 + (time.time() - self.mtime) / 86400)
        priority_boost = {"high": 0.3, "normal": 0.0, "low": -0.2}.get(self.priority, 0.0)
        return similarity * 0.6 + recency * 0.1 + priority_boost

    def is_expired(self) -> bool:
        if not self.ttl:
            return False
        delta = _parse_ttl(self.ttl)
        if delta is None:
            return False
        age = datetime.now() - datetime.fromtimestamp(self.mtime)
        return age > delta

    def to_context(self) -> str:
        parts = [f"[{self.id}] {self.name}"]
        if self.description:
            parts.append(self.description)
        if self.body:
            parts.append(self.body.strip())
        return "\n".join(parts)


# ── Store ────────────────────────────────────────────────────────────────────

def load_all() -> dict[str, MemoryNode]:
    d = _ensure_dir()
    nodes: dict[str, MemoryNode] = {}
    for f in d.glob("*.md"):
        fm, body = _parse_frontmatter(f.read_text())
        node_id = fm.get("id") or f.stem
        nodes[node_id] = MemoryNode(
            id=node_id,
            name=fm.get("name", node_id),
            description=fm.get("description", ""),
            type=fm.get("type", "reference"),
            tags=fm.get("tags") or [],
            links=fm.get("links") or [],
            priority=fm.get("priority", "normal"),
            ttl=fm.get("ttl", ""),
            body=body,
            mtime=f.stat().st_mtime,
        )
    return nodes


def save(node: MemoryNode) -> None:
    d = _ensure_dir()
    fm = {
        "id": node.id,
        "name": node.name,
        "description": node.description,
        "type": node.type,
        "tags": node.tags or None,
        "links": node.links or None,
        "priority": node.priority,
    }
    if node.ttl:
        fm["ttl"] = node.ttl
    text = _serialize_frontmatter({k: v for k, v in fm.items() if v is not None}, node.body)
    (d / f"{node.id}.md").write_text(text)


def query(tags: list[str], top_n: int = 5, expand_links: bool = True) -> list[MemoryNode]:
    """Return top_n relevant nodes, expanding links one level deep."""
    all_nodes = load_all()
    active = {k: v for k, v in all_nodes.items() if not v.is_expired()}

    # always include priority:high nodes
    high = [n for n in active.values() if n.priority == "high"]
    scored = sorted(
        [n for n in active.values() if n.priority != "high"],
        key=lambda n: n.score(tags),
        reverse=True,
    )

    seed_ids = {n.id for n in high}
    result = list(high)

    for n in scored:
        if len(result) >= top_n:
            break
        if n.score(tags) > 0 and n.id not in seed_ids:
            result.append(n)
            seed_ids.add(n.id)

    if expand_links:
        for n in list(result):
            for link_id in n.links:
                if link_id in active and link_id not in seed_ids:
                    result.append(active[link_id])
                    seed_ids.add(link_id)

    return result


def stats() -> dict:
    all_nodes = load_all()
    active = [n for n in all_nodes.values() if not n.is_expired()]
    expired = [n for n in all_nodes.values() if n.is_expired()]
    total_chars = sum(len(n.to_context()) for n in active)
    return {
        "total": len(all_nodes),
        "active": len(active),
        "expired": len(expired),
        "estimated_tokens": total_chars // CHARS_PER_TOKEN,
        "store": str(MEMORY_DIR),
    }
