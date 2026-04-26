"""next_task_* tools — single-slot continuity hand-off between sessions.

See ``jig.engines.next_task`` for the storage contract. These tools sit
on jig's surface (not archived) because they're called once at the end
of a task (record) and once at the start of the next (get) — hot path,
not niche.
"""
from __future__ import annotations

from dataclasses import asdict

from jig.core.session import resolve_project_dir
from jig.engines import next_task as engine


def register_next_task_tools(mcp) -> None:

    @mcp.tool()
    def next_task_record(
        summary: str,
        task_description: str | None = None,
        files_changed: list[str] | None = None,
        project_dir: str | None = None,
        session_id: str | None = None,
    ) -> dict:
        """Save the just-finished task's user-facing summary as a
        continuity hand-off for the *next* task.

        Call this at the end of a task, with the same summary you
        present to the user. The next time ``/task-with-jig`` (or any
        wrapper that respects this convention) runs, it will inject
        this blob as prelude context — so the user can ``/clear`` to
        wipe conversation history without losing the thread of what
        was just done.

        Single-slot: a new record overwrites the previous one. For
        long-term lessons-learned, use ``experience_record`` instead.

        Args:
            summary: The summary text given to the user at task end.
                Required. Markdown is fine.
            task_description: One-line description of what the task
                was attempting. Optional but recommended.
            files_changed: Optional list of paths the task modified.
                Helps the next session know where to look.
            project_dir: Project directory (optional after set_session).
            session_id: Optional session id.
        """
        resolved_dir, _ = resolve_project_dir(project_dir, session_id)
        entry = engine.record(
            project_dir=resolved_dir,
            summary=summary,
            task_description=task_description,
            files_changed=files_changed,
        )
        return {
            "success": True,
            "saved_at": entry.saved_at,
            "project_dir": entry.project_dir,
            "bytes": len(entry.summary),
        }

    @mcp.tool()
    def next_task_get(
        project_dir: str | None = None,
        session_id: str | None = None,
    ) -> dict:
        """Read the most-recent-task hand-off for this project.

        Returns the saved summary plus a pre-formatted ``injection``
        string ready to paste into a new task's prompt. Returns
        ``{"found": False}`` if nothing was saved (fresh project or
        after ``next_task_clear``).

        Args:
            project_dir: Project directory (optional after set_session).
            session_id: Optional session id.
        """
        resolved_dir, _ = resolve_project_dir(project_dir, session_id)
        entry = engine.get(resolved_dir)
        if entry is None:
            return {"found": False, "project_dir": resolved_dir}
        return {
            "found": True,
            "entry": asdict(entry),
            "injection": engine.format_for_injection(entry),
        }

    @mcp.tool()
    def next_task_clear(
        project_dir: str | None = None,
        session_id: str | None = None,
    ) -> dict:
        """Wipe the most-recent-task hand-off for this project.

        Use when you want to start a fresh series of tasks without
        carrying continuity from the prior one. Idempotent.
        """
        resolved_dir, _ = resolve_project_dir(project_dir, session_id)
        removed = engine.clear(resolved_dir)
        return {
            "success": True,
            "removed": removed,
            "project_dir": resolved_dir,
        }
