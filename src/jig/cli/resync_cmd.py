"""`jig resync <path>` — update an existing jig-scaffolded project's assets.

Copies fresh hooks, rules, commands, and workflows from the installed jig
version into <project>/.claude/. Does NOT touch .mcp.json, proxy.toml, or
settings.json — those contain project-local config that must be preserved.

Use after:
  - Updating jig to a new version
  - Pulling new rules/hooks from upstream
  - Noticing that .claude/rules/ or .claude/hooks/ are out of date

To also refresh agents and skills, pass --agents with the tech stack.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "resync",
        help="Update hooks, rules, commands and workflows in an existing jig project",
    )
    p.add_argument("path", help="Target project path (must already have .claude/)")
    p.add_argument(
        "--agents",
        nargs="+",
        metavar="TECH",
        default=None,
        help="Also re-deploy agents and skills for these technologies (e.g. python fastmcp)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without writing anything",
    )
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> int:
    target = Path(args.path).expanduser().resolve()

    if not target.exists() or not target.is_dir():
        print(f"[jig.resync] path does not exist or is not a directory: {target}", file=sys.stderr)
        return 2

    claude_dir = target / ".claude"
    if not claude_dir.exists():
        print(
            f"[jig.resync] {target} has no .claude/ — run `jig init {target}` first",
            file=sys.stderr,
        )
        return 2

    print(f"jig resync {target}")
    print()
    print("  Updates:")
    print("    • hooks/        ← jig.hooks (all hook scripts)")
    print("    • rules/        ← jig assets (base rules only; stack rules if --agents)")
    print("    • commands/     ← jig assets")
    print("    • workflows/    ← jig assets")
    print("    • settings.json ← NOT touched (project-local)")
    print("    • .mcp.json     ← NOT touched (project-local)")
    if args.agents:
        print(f"    • agents/skills ← deploy_project_agents({args.agents})")
    print()

    if args.dry_run:
        return 0

    from jig.cli.init_cmd import _copy_assets
    _copy_assets(claude_dir)

    if args.agents:
        _resync_agents(target, args.agents)

    print()
    print(" ─── jig resync complete ─── ")
    print(f"   Project: {target}")
    print("   Next: reconnect jig in Claude Code via /mcp")
    if args.agents:
        print(f"   Agents deployed for: {', '.join(args.agents)}")
    return 0


def _resync_agents(target: Path, tech_stack: list[str]) -> None:
    from jig.engines.hub_config import get_hub_dir  # noqa: F401 — triggers hub detection
    from jig.tools.deployment import register_deployment_tools
    from fastmcp import FastMCP

    # Spin up a throwaway MCP instance to get the deploy function registered,
    # then call it by pulling it from the registry.
    _holder = FastMCP("_resync_holder")
    register_deployment_tools(_holder)

    import asyncio

    async def _call():
        tool = await _holder.get_tool("deploy_project_agents")
        return await tool.run({"project_path": str(target), "tech_stack": tech_stack, "include_core": True})

    try:
        result = asyncio.run(_call())
        n = (result or {}).get("summary", {}).get("agents", 0)
        print(f"[jig.resync] deployed {n} agent(s) for {tech_stack}")
    except Exception as e:
        print(f"[jig.resync] agent deploy failed: {e}", file=sys.stderr)
