"""CLI entry point dispatcher.

Subcommands:
    serve    — start the MCP server on stdio (default when invoked with no args)
    init     — scaffold a project: migrate .mcp.json, copy hooks/rules/skills, warm cache
    doctor   — diagnostics: embedding model, proxy reachability, cache integrity
    version  — print version and exit

Invocation:
    jig            → equivalent to `jig serve`
    jig serve      → explicit serve mode
    jig init PATH  → scaffold
    jig doctor     → diagnostics
    jig --version  → version
"""
from __future__ import annotations

import argparse
import sys
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
            "Install source written into the rendered .mcp.json. Defaults to "
            "'git+https://github.com/Rixmerz/jig' while jig-mcp is pre-PyPI. "
            "Pass 'jig-mcp' (or set JIG_SOURCE=jig-mcp) to use the PyPI "
            "package once it's published."
        ),
    )
    init.set_defaults(func=_cmd_init)

    doctor = sub.add_parser("doctor", help="Run diagnostics on the jig installation")
    doctor.set_defaults(func=_cmd_doctor)

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
