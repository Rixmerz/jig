"""CLI entry point dispatcher.

Subcommands:
    serve      — start the MCP server on stdio (default when invoked with no args)
    init       — scaffold a project: migrate .mcp.json, copy hooks/rules/skills, warm cache
    resync     — update hooks/rules/commands/workflows in an existing jig project (no .mcp.json touch)
    update     — upgrade jig-mcp via uv tool upgrade + resync scaffolded projects
    doctor     — diagnostics: embedding model, proxy reachability, cache integrity
                 (use ``doctor --prefetch`` to download/load embed model first)
    graph      — out-of-band graph state management (reset/status without MCP)
    memory     — list or search user-level memories (~/.jig/memory/)
    memory-gc  — garbage collect stale user-level memory files (~/.jig/memory/)
    version    — print version and exit

Invocation:
    jig            → equivalent to `jig serve`
    jig serve      → explicit serve mode
    jig init PATH  → scaffold
    jig doctor     → diagnostics
    jig graph reset → clear stuck graph state (escape hatch)
    jig --version  → version
"""
from __future__ import annotations

import argparse
from collections.abc import Sequence

from jig import __version__


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jig",
        description=(
            "Just-in-time tool discovery and phase-enforced workflows for AI coding agents. "
            "By default, starts an MCP server on stdio."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    serve = sub.add_parser("serve", help="Start the MCP server on stdio (default)")
    serve.set_defaults(func=_cmd_serve)

    init = sub.add_parser("init", help="Scaffold jig configuration into a project")
    init.add_argument("path", help="Target project path")
    init.add_argument(
        "--no-warmup",
        action="store_true",
        help="Skip embedding warmup after init (first search will be slower)",
    )
    init.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what init would do without writing anything",
    )
    init.add_argument(
        "--source",
        default=None,
        help=(
            "Install source written into the rendered .mcp.json. "
            "'tool' = bare `jig-mcp` command, assumes `uv tool install` "
            "was run. 'jig-mcp' = `uvx jig-mcp` (PyPI). "
            "'git+...' = `uvx --from <spec> jig-mcp`. "
            "Auto-detected as 'tool' when jig-mcp is on PATH; otherwise "
            "falls back to git+https://github.com/Rixmerz/jig. Can also be "
            "set via JIG_SOURCE env var."
        ),
    )
    init.set_defaults(func=_cmd_init)

    doctor = sub.add_parser(
        "doctor",
        help="Run diagnostics (global + optional per-project)",
    )
    doctor.add_argument(
        "--project",
        default=None,
        help="Path to a jig-scaffolded project to audit in addition to global checks",
    )
    doctor.add_argument(
        "--repair",
        action="store_true",
        help="Auto-fix auto-fixable issues (requires --project). Rewrites stale python3 in settings.json, restores missing hooks, chmod +x on hook scripts.",
    )
    doctor.add_argument(
        "--dry-run",
        action="store_true",
        help="With --repair, print the plan without touching anything",
    )
    doctor.add_argument(
        "--prefetch",
        action="store_true",
        help=(
            "Download/load the embedding model before other checks (blocks; "
            "first run may fetch ~1.3 GB). Use after install to avoid slow "
            "first MCP search."
        ),
    )
    doctor.set_defaults(func=_cmd_doctor)

    from jig.cli import graph_cmd
    graph_cmd.add_parser(sub)

    from jig.cli import memory_cmd
    memory_cmd.add_parser(sub)

    from jig.cli import memory_gc
    memory_gc.add_parser(sub)

    from jig.cli import resync_cmd
    resync_cmd.add_parser(sub)

    from jig.cli import update_cmd
    update_cmd.add_parser(sub)

    return parser


def _cmd_serve(_args: argparse.Namespace) -> int:
    """Start the MCP server. Actual implementation lives in jig.server."""
    from jig.server import serve

    serve()
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    """Scaffold project — see jig.cli.init_cmd for details."""
    from jig.cli.init_cmd import run

    return run(args)


def _cmd_doctor(args: argparse.Namespace) -> int:
    """Diagnostics — see jig.cli.doctor for details."""
    from jig.cli.doctor import run

    return run(args)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        # default: serve
        return _cmd_serve(args)
    return args.func(args)  # type: ignore[no-any-return]


if __name__ == "__main__":
    raise SystemExit(main())
