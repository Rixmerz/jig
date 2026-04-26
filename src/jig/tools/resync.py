"""MCP tool: jig_resync_project."""
from __future__ import annotations


def register_resync_tools(mcp) -> None:

    @mcp.tool()
    def jig_resync_project(
        project_path: str,
        tech_stack: list[str] | None = None,
        dry_run: bool = False,
    ) -> dict:
        # destructiveHint: True (overwrites .claude/ assets)
        """Update hooks, rules, commands and workflows in an existing jig-scaffolded project.

        Copies fresh assets from the installed jig version into <project>/.claude/.
        Does NOT touch .mcp.json, proxy.toml, or settings.json — those contain
        project-local configuration that must be preserved.

        Use after:
        - Updating jig to a new version
        - Pulling new rules or hooks from upstream
        - Noticing that .claude/rules/ or .claude/hooks/ are stale

        Args:
            project_path: Absolute path to the target project (must already have .claude/).
            tech_stack: If provided, also re-deploy agents and skills for these technologies
                        (e.g. ["python", "fastmcp"]). Equivalent to running /setup-agents after resync.
            dry_run: If True, return a plan without writing anything.

        Returns:
            updated: list of asset categories refreshed
            agents_deployed: number of agents re-deployed (0 if tech_stack not provided)
            message: human-readable summary
        """
        from pathlib import Path

        target = Path(project_path).expanduser().resolve()

        if not target.exists() or not target.is_dir():
            return {"error": True, "message": f"Path does not exist or is not a directory: {project_path}"}

        claude_dir = target / ".claude"
        if not claude_dir.exists():
            return {
                "error": True,
                "message": f"No .claude/ found at {target}. Run jig_init_project first.",
            }

        plan = {
            "project": str(target),
            "updates": ["hooks/", "rules/ (base)", "commands/", "workflows/"],
            "skipped": ["settings.json", ".mcp.json", "proxy.toml"],
        }
        if tech_stack:
            plan["updates"].append(f"agents/ + skills/ ({', '.join(tech_stack)})")

        if dry_run:
            return {"dry_run": True, **plan}

        from jig.cli.init_cmd import _copy_assets
        _copy_assets(claude_dir)

        agents_deployed = 0
        if tech_stack:
            agents_deployed = _deploy_agents(target, tech_stack)

        return {
            "updated": plan["updates"],
            "skipped": plan["skipped"],
            "agents_deployed": agents_deployed,
            "message": (
                f"Resync complete for {target.name}. "
                "Reconnect jig in Claude Code via /mcp to pick up the changes."
            ),
        }


def _deploy_agents(target, tech_stack: list[str]) -> int:
    import asyncio
    from fastmcp import FastMCP
    from jig.tools.deployment import register_deployment_tools

    holder = FastMCP("_resync_holder")
    register_deployment_tools(holder)

    async def _call():
        tool = await holder.get_tool("deploy_project_agents")
        return await tool.run({
            "project_path": str(target),
            "tech_stack": tech_stack,
            "include_core": True,
        })

    try:
        result = asyncio.run(_call()) or {}
        return result.get("summary", {}).get("agents", 0)
    except Exception:
        return 0
