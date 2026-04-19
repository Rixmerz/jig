#!/usr/bin/env python3
"""PostToolUse(Bash) hook: snapshot workspace with a throttle window.

Captures a shadow-branch snapshot after Bash commands that touched the
workspace. Uses a 30s lockfile-based throttle so rapid-fire commands don't
create a flood of snapshots.

Exits with code 0 always (never blocks Claude Code). Output is advisory.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

THROTTLE_SECONDS = 30.0


def _project_dir() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return Path.cwd()


def _read_input() -> dict:
    try:
        data = sys.stdin.read()
        if not data:
            return {}
        return json.loads(data)
    except Exception:
        return {}


def _should_skip(payload: dict) -> bool:
    tool = payload.get("tool_name", "")
    if tool != "Bash":
        return True
    cmd = (payload.get("tool_input", {}) or {}).get("command", "")
    if not isinstance(cmd, str) or not cmd.strip():
        return True
    # Skip read-only commands
    first = cmd.strip().split()[0] if cmd.strip() else ""
    read_only = {"ls", "cat", "grep", "rg", "find", "pwd", "echo", "head", "tail", "wc", "git"}
    if first in read_only:
        return True
    return False


def main() -> int:
    payload = _read_input()
    if _should_skip(payload):
        return 0

    project = _project_dir()
    lock = project / ".jig" / "snapshots.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)

    now = time.time()
    if lock.exists():
        try:
            last = float(lock.read_text().strip())
            if now - last < THROTTLE_SECONDS:
                return 0
        except (ValueError, OSError):
            pass

    try:
        from jig.core import snapshots

        snap = snapshots.create(project, label="bash-postrun", phase="")
        if snap:
            lock.write_text(f"{now}", encoding="utf-8")
            print(
                f"[jig.snapshot] captured {snap.id}",
                file=sys.stderr,
            )
    except Exception as e:
        print(f"[jig.snapshot] skip: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
