#!/usr/bin/env python3
"""Run a jig hook script with Cursor-friendly project root and stdout mapping.

Copies live under ``<project>/.cursor/hooks/`` alongside the real hook modules.
Cursor invokes this runner; it sets ``CLAUDE_PROJECT_DIR`` for legacy hooks,
executes the target script with the same stdin, then maps Claude-style JSON
responses to Cursor hook output where applicable.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _project_root(here: Path) -> Path:
    # here = <proj>/.cursor/hooks/jig_cursor_hook_runner.py
    return here.parents[2]


def _enriched_env(root: Path) -> dict[str, str]:
    out = {k: str(v) for k, v in os.environ.items()}
    root_s = str(root)
    if not out.get("CLAUDE_PROJECT_DIR", "").strip():
        out["CLAUDE_PROJECT_DIR"] = (
            out.get("CURSOR_WORKSPACE_ROOT", "").strip()
            or out.get("VSCODE_WORKSPACE_FOLDER", "").strip()
            or root_s
        )
    return out


def _translate_hook_stdout(raw: str) -> str:
    text = raw.strip()
    if not text:
        return "{}"
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return json.dumps({"additional_context": raw.rstrip("\n")})

    if not isinstance(data, dict):
        return text

    if "decision" in data:
        dec = str(data.get("decision", "approve"))
        perm = {"approve": "allow", "block": "deny"}.get(dec, "allow")
        out: dict[str, str] = {"permission": perm}
        if dec == "block" and data.get("message"):
            msg = str(data["message"])
            out["user_message"] = msg
            out["agent_message"] = msg
        return json.dumps(out)

    if "hookSpecificOutput" in data and isinstance(data["hookSpecificOutput"], dict):
        hso = data["hookSpecificOutput"]
        ctx = hso.get("additionalContext")
        if ctx is not None:
            return json.dumps({"additional_context": ctx})

    return json.dumps(data)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: jig_cursor_hook_runner.py <hook_script.py>", file=sys.stderr)
        return 2
    here = Path(__file__).resolve()
    root = _project_root(here)
    script = here.parent / sys.argv[1]
    if not script.is_file():
        print(f"jig_cursor_hook_runner: missing {script}", file=sys.stderr)
        return 2

    stdin_bytes = sys.stdin.buffer.read()
    proc = subprocess.run(
        [sys.executable, str(script)],
        input=stdin_bytes,
        capture_output=True,
        env=_enriched_env(root),
        cwd=str(root),
    )
    sys.stderr.buffer.write(proc.stderr)
    sys.stderr.flush()
    if proc.stdout:
        sys.stdout.write(_translate_hook_stdout(proc.stdout.decode("utf-8", errors="replace")))
    sys.stdout.flush()
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
