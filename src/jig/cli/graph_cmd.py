"""`jig graph` — out-of-band graph state management.

Subcommands that operate directly on the on-disk graph state file
(``~/.local/share/jig/states/<project>/graph_state.json``) without
requiring a running MCP server. Intended as a recovery escape hatch for
the deadlock pattern:

    1. User activates a graph workflow whose current phase blocks Bash
       / Edit / Write.
    2. MCP server disconnects (transient bug, OOM, harness restart).
    3. The PreToolUse ``graph_enforcer`` hook keeps reading the persisted
       state and keeps blocking — correctly, from its point of view.
    4. Without MCP access the user cannot call ``graph_reset`` to clear
       the state, so every mutating tool is blocked.

``jig graph reset`` writes a cleared state blob to disk so the hook
starts approving again. Run from any terminal; no MCP needed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from jig.engines.graph_state import get_graph_state_file


def _resolve_project_dir(arg: str | None) -> Path:
    if arg:
        return Path(arg).expanduser().resolve()
    return Path.cwd().resolve()


def _cmd_reset(args: argparse.Namespace) -> int:
    project_dir = _resolve_project_dir(args.project)
    state_file = get_graph_state_file(str(project_dir))

    if not state_file.exists():
        print(f"[jig graph reset] No active graph state at {state_file}")
        print("[jig graph reset] Nothing to reset.")
        return 0

    try:
        previous = json.loads(state_file.read_text())
        prev_graph = previous.get("active_graph")
        prev_nodes = previous.get("current_nodes", [])
    except Exception:
        prev_graph = None
        prev_nodes = []

    cleared = {
        "current_nodes": [],
        "node_visits": {},
        "execution_path": [],
        "active_graph": None,
        "max_visits_default": 10,
        "total_transitions": 0,
        "last_activity": None,
        "tension_gate_state": {},
        "last_dcc_result": None,
        "last_dcc_timestamp": None,
        "completed_tasks": {},
    }

    if args.dry_run:
        print(f"[jig graph reset] (dry-run) would clear: {state_file}")
        if prev_graph:
            print(f"[jig graph reset]   active_graph: {prev_graph}")
            print(f"[jig graph reset]   current_nodes: {prev_nodes}")
        return 0

    state_file.write_text(json.dumps(cleared, indent=2))

    print(f"[jig graph reset] Cleared {state_file}")
    if prev_graph:
        print(
            f"[jig graph reset] Was: active_graph={prev_graph!r}, "
            f"current_nodes={prev_nodes}"
        )
    print(
        "[jig graph reset] PreToolUse hooks will now approve. "
        "Re-activate a workflow with graph_activate when ready."
    )
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    project_dir = _resolve_project_dir(args.project)
    state_file = get_graph_state_file(str(project_dir))

    if not state_file.exists():
        print(f"[jig graph status] No state file at {state_file}")
        return 0

    try:
        state = json.loads(state_file.read_text())
    except Exception as e:
        print(f"[jig graph status] State file unreadable: {e}")
        return 1

    print(f"[jig graph status] {state_file}")
    print(f"  active_graph:  {state.get('active_graph') or '(none)'}")
    print(f"  current_nodes: {state.get('current_nodes') or []}")
    print(f"  last_activity: {state.get('last_activity') or '(never)'}")
    print(f"  transitions:   {state.get('total_transitions', 0)}")
    return 0


def add_parser(sub: argparse._SubParsersAction) -> None:
    """Register the `jig graph` subcommand tree."""
    graph = sub.add_parser(
        "graph",
        help="Out-of-band graph state management (recovery escape hatch)",
    )
    graph_sub = graph.add_subparsers(dest="graph_command", metavar="SUBCOMMAND")

    reset = graph_sub.add_parser(
        "reset",
        help=(
            "Clear active graph state without needing the MCP server. "
            "Use to recover from a deadlock when the PreToolUse hook is "
            "blocking and graph_reset via MCP is unreachable."
        ),
    )
    reset.add_argument(
        "--project",
        default=None,
        help="Project directory (default: current working directory)",
    )
    reset.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be cleared without writing",
    )
    reset.set_defaults(func=_cmd_reset)

    status = graph_sub.add_parser(
        "status",
        help="Read the on-disk graph state without needing the MCP server",
    )
    status.add_argument(
        "--project",
        default=None,
        help="Project directory (default: current working directory)",
    )
    status.set_defaults(func=_cmd_status)

    def _no_subcommand(_a: argparse.Namespace) -> int:
        graph.print_help()
        return 1

    graph.set_defaults(func=_no_subcommand)
