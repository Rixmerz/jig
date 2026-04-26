"""Next-task memory — single-slot per-project persistence of the most
recent task summary.

Goal: let a user finish a task, run ``/clear`` to wipe Claude Code's
conversation context (saving cache cost on the next session), and then
start a new task without losing the high-level continuity of what was
just done. The saved summary is injected as prelude context by the
``/task-with-jig`` command/skill.

Storage: one JSON blob per project at
``~/.local/share/jig/next_task/<project_name>.json``. Single slot —
``next_task_record`` overwrites whatever was there. We deliberately do
not keep history; that's what ``experience_record`` is for. This is a
short-term continuity hand-off, not a journal.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from jig.core import paths as _paths


@dataclass
class NextTaskEntry:
    """Most-recent-task hand-off blob.

    Attributes:
        summary: Free-form summary the agent gave the user at the end of
            the task. The single most important field.
        task_description: One-line description of what the task was.
            Helpful so the next session knows what was being attempted,
            not only what was achieved.
        files_changed: Optional list of file paths the task touched.
        saved_at: ISO 8601 timestamp set by ``record``.
        project_dir: Absolute project path the entry belongs to.
    """
    summary: str
    task_description: Optional[str] = None
    files_changed: list[str] = field(default_factory=list)
    saved_at: str = ""
    project_dir: str = ""


def _next_task_dir() -> Path:
    d = _paths.data_dir() / "next_task"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _entry_path(project_dir: str) -> Path:
    return _next_task_dir() / f"{Path(project_dir).name}.json"


def record(
    project_dir: str,
    summary: str,
    task_description: Optional[str] = None,
    files_changed: Optional[list[str]] = None,
) -> NextTaskEntry:
    """Persist (overwrite) the most-recent-task blob for this project."""
    entry = NextTaskEntry(
        summary=summary,
        task_description=task_description,
        files_changed=files_changed or [],
        saved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        project_dir=str(Path(project_dir).resolve()),
    )
    path = _entry_path(project_dir)
    path.write_text(json.dumps(asdict(entry), indent=2, ensure_ascii=False))
    return entry


def get(project_dir: str) -> Optional[NextTaskEntry]:
    """Load the most-recent-task blob, or None if nothing saved."""
    path = _entry_path(project_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return NextTaskEntry(
            summary=data.get("summary", ""),
            task_description=data.get("task_description"),
            files_changed=data.get("files_changed", []),
            saved_at=data.get("saved_at", ""),
            project_dir=data.get("project_dir", ""),
        )
    except Exception:
        return None


def clear(project_dir: str) -> bool:
    """Wipe the most-recent-task blob for this project. Returns True if
    a file was removed, False if there was nothing to remove."""
    path = _entry_path(project_dir)
    if path.exists():
        path.unlink()
        return True
    return False


def format_for_injection(entry: NextTaskEntry) -> str:
    """Render an entry as a short prelude block to inject into a new
    task's prompt. Kept compact on purpose — the new task is what
    matters; this is just continuity."""
    if not entry.summary:
        return ""
    parts = ["## Previous task summary (continuity context)"]
    if entry.task_description:
        parts.append(f"**Was:** {entry.task_description}")
    parts.append(entry.summary.strip())
    if entry.files_changed:
        parts.append("")
        parts.append("**Files touched last time:** " + ", ".join(
            f"`{p}`" for p in entry.files_changed[:10]
        ))
        if len(entry.files_changed) > 10:
            parts[-1] += f" (+{len(entry.files_changed) - 10} more)"
    if entry.saved_at:
        parts.append(f"\n_(saved {entry.saved_at})_")
    return "\n".join(parts)
