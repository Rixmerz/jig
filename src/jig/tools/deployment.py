"""Deployment tools: deploy_project_agents, list_available_agents_and_skills."""

import shutil
from pathlib import Path

import jig
from jig.engines.hub_config import get_hub_dir


def _bundled_assets_dir() -> Path:
    """Return the filesystem path to jig.assets/ inside the installed wheel.

    Uses jig's package __file__ instead of importlib.resources because some
    loaders return a MultiplexedPath that can't be consumed as a plain Path.
    """
    return Path(jig.__file__).parent / "assets"


def _agents_source() -> Path:
    """Where list_available should read agents from.

    Prefers a populated user hub (hub_dir/.hub/agents) when present —
    that's the override slot for users who maintain a local curated
    catalog. Otherwise falls back to the bundled wheel assets.
    """
    hub_agents = get_hub_dir() / ".hub" / "agents"
    if hub_agents.is_dir():
        return hub_agents
    return _bundled_assets_dir() / "agents"


def _skills_source() -> Path:
    hub_skills = get_hub_dir() / ".hub" / "skills"
    if hub_skills.is_dir():
        return hub_skills
    return _bundled_assets_dir() / "skills"


def _rules_source() -> Path:
    hub_rules = get_hub_dir() / ".hub" / "rules"
    if hub_rules.is_dir():
        return hub_rules
    return _bundled_assets_dir() / "rules"


# Mapping: tech stack keywords -> recommended skills
_TECH_SKILL_MAP: dict[str, list[str]] = {
    # Languages
    "python": ["py-patterns", "qa-patterns"],
    "typescript": ["ts-patterns", "qa-patterns"],
    "javascript": ["ts-patterns", "jsbackend-patterns", "qa-patterns"],
    "go": ["go-patterns", "qa-patterns"],
    "rust": ["rs-patterns", "qa-patterns"],
    "java": ["java-patterns", "qa-patterns"],
    "php": ["php-patterns", "qa-patterns"],
    "swift": ["swift-patterns", "qa-patterns"],
    "lua": ["lua-patterns", "qa-patterns"],
    "csharp": ["csharp-patterns", "qa-patterns"],
    "kotlin": ["kotlin-patterns", "qa-patterns"],
    # Frameworks / domains
    "react": ["ts-patterns", "ui-patterns", "ux-patterns", "react-tauri"],
    "tauri": ["rs-patterns", "rust-backend"],
    "devops": ["devops-patterns", "dev-patterns"],
    "frontend": ["ui-patterns", "ux-patterns", "css-theming"],
}

# Mapping: tech stack keywords -> language/domain rules to copy
_TECH_RULE_MAP: dict[str, list[str]] = {
    "python": ["python.md"],
    "typescript": ["typescript.md", "jsbackend.md"],
    "javascript": ["typescript.md", "jsbackend.md"],
    "go": ["go.md"],
    "rust": ["rust.md"],
    "java": ["java.md"],
    "php": ["php.md"],
    "swift": ["swift.md"],
    "lua": ["lua.md"],
    "react": ["typescript.md", "ui.md", "ux.md"],
    "vue": ["typescript.md", "ui.md", "ux.md"],
    "angular": ["typescript.md", "ui.md"],
    "frontend": ["ui.md", "ux.md"],
    "devops": ["devops.md", "dev.md"],
    "backend": ["dev.md"],
}

# Core agents always included when include_core=True
_CORE_AGENTS = ["orchestrator", "debugger", "reviewer"]

# Core skills always included
_CORE_SKILLS = ["qa-patterns", "testing", "validation", "debug"]


def _parse_agent_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML-like frontmatter from an agent .md file.

    Returns (frontmatter_dict, body_after_frontmatter).
    """
    if not content.startswith("---"):
        return {}, content

    end_idx = content.index("---", 3)
    fm_text = content[3:end_idx].strip()
    body = content[end_idx + 3:].lstrip("\n")

    fm = {}
    for line in fm_text.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()
    return fm, body


def _build_agent_frontmatter(fm: dict) -> str:
    """Serialize frontmatter dict back to YAML-like block."""
    lines = ["---"]
    # Preserve key order: name, description, model, tools, skills
    key_order = ["name", "description", "model", "tools", "skills"]
    written = set()
    for key in key_order:
        if key in fm:
            lines.append(f"{key}: {fm[key]}")
            written.add(key)
    for key, val in fm.items():
        if key not in written:
            lines.append(f"{key}: {val}")
    lines.append("---")
    return "\n".join(lines)


def _resolve_skills_for_stack(tech_stack: list[str], extra_skills: list[str] | None = None) -> list[str]:
    """Given a tech_stack list, resolve the full set of recommended skills."""
    skills = set(_CORE_SKILLS)
    for tech in tech_stack:
        key = tech.lower().strip()
        if key in _TECH_SKILL_MAP:
            skills.update(_TECH_SKILL_MAP[key])
    if extra_skills:
        skills.update(extra_skills)
    return sorted(skills)


def _resolve_rules_for_stack(tech_stack: list[str]) -> list[str]:
    """Given a tech_stack list, resolve the language/domain rules to copy."""
    rules: set[str] = set()
    for tech in tech_stack:
        key = tech.lower().strip()
        if key in _TECH_RULE_MAP:
            rules.update(_TECH_RULE_MAP[key])
    # Always include qa.md for any project
    rules.add("qa.md")
    return sorted(rules)


def _resolve_agents_for_stack(tech_stack: list[str], extra_agents: list[str] | None = None) -> list[str]:
    """Given a tech_stack list, resolve recommended agents."""
    agents = set(_CORE_AGENTS)
    stack_lower = {t.lower().strip() for t in tech_stack}

    # Detect if project has frontend/backend needs
    frontend_techs = {"react", "vue", "angular", "svelte", "deno-fresh", "typescript", "javascript", "frontend"}
    backend_techs = {"python", "go", "rust", "java", "php", "swift", "lua"}

    has_frontend = bool(stack_lower & frontend_techs)
    has_backend = bool(stack_lower & backend_techs)

    if has_frontend:
        agents.add("frontend")
    if has_backend:
        agents.add("backend")

    # Always include tester
    agents.add("tester")

    if extra_agents:
        agents.update(extra_agents)
    return sorted(agents)


def register_deployment_tools(mcp):

    @mcp.tool()
    def jig_init_project(
        project_path: str,
        source: str | None = None,
        dry_run: bool = False,
        no_warmup: bool = False,
    ) -> dict:
        """Phase 0: scaffold a project with jig's base layer.

        Copies hooks (all), commands (all), workflows (all), base rules
        (10 universal ones), and settings.json into
        ``<project_path>/.claude/``. Migrates any local MCPs from the
        project's existing ``.mcp.json`` into jig's proxy pool, then
        rewrites ``.mcp.json`` to point at jig only (plus any remote
        MCPs). Optionally warms up the embedding cache.

        Stack-specific rules, agents, and skills are NOT copied here —
        call ``deploy_project_agents`` next (phase 1) with the declared
        tech_stack to bring in the watcher rules, specialised agents,
        and on-demand skills that match the project.

        Args:
            project_path: Absolute path to the target project directory.
            source: Optional install spec written into the rendered
                .mcp.json. ``git+https://...`` pre-PyPI. Defaults to
                ``uvx jig-mcp`` (PyPI).
            dry_run: If True, print the plan and return without writing.
            no_warmup: Skip embedding warmup (first search will be slow).

        Returns:
            {success, exit_code, project_path, phase, next_step}
        """
        import argparse
        from jig.cli.init_cmd import run as _run_init

        ns = argparse.Namespace(
            path=project_path,
            source=source,
            dry_run=dry_run,
            no_warmup=no_warmup,
        )
        exit_code = _run_init(ns)
        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "project_path": str(Path(project_path).expanduser().resolve()),
            "phase": 0,
            "next_step": (
                "Call deploy_project_agents(project_path, tech_stack=[...]) "
                "to bring in agents, skills, and stack-specific watcher rules."
            ),
        }

    @mcp.tool()
    def deploy_project_agents(
        project_path: str,
        tech_stack: list[str],
        extra_agents: list[str] | None = None,
        extra_skills: list[str] | None = None,
        include_core: bool = True,
        tech_context: dict | None = None,
        session_id: str | None = None,
    ) -> dict:
        # destructiveHint: True (writes files to target project)
        """Deploy specialized agents with injected skills to a user project.

        Copies agent templates from AgentCockpit hub and skill directories,
        customizing each agent's frontmatter with the skills relevant to the
        project's tech stack. Creates .claude/agents/ and .claude/skills/
        in the target project.

        Args:
            project_path: Absolute path to the target project directory
            tech_stack: List of technologies (e.g. ["typescript", "python", "react"])
            extra_agents: Additional agent names to deploy beyond auto-detected ones
            extra_skills: Additional skill names to deploy beyond auto-detected ones
            include_core: Include orchestrator, debugger, reviewer (default True)
            tech_context: Optional dict with project details (e.g. {"frontend": "React 19", "backend": "FastAPI"})
            session_id: Optional session ID

        Returns:
            Manifest of deployed agents and skills with paths

        Example:
            deploy_project_agents(
                project_path="/home/user/my-project",
                tech_stack=["typescript", "python", "react"],
                tech_context={"frontend": "React 19", "backend": "FastAPI"}
            )
        """
        hub_dir = get_hub_dir()
        hub_agents_dir = _agents_source()
        hub_skills_dir = _skills_source()

        target = Path(project_path).resolve()
        if not target.exists():
            return {"error": True, "message": f"Project path does not exist: {project_path}"}


        target_agents_dir = target / ".claude" / "agents"
        target_skills_dir = target / ".claude" / "skills"

        hub_rules_dir = _rules_source()

        # Resolve what to deploy
        agents_to_deploy = _resolve_agents_for_stack(tech_stack, extra_agents) if include_core else list(extra_agents or [])
        skills_to_deploy = _resolve_skills_for_stack(tech_stack, extra_skills)
        rules_to_deploy = _resolve_rules_for_stack(tech_stack)

        # Create target directories
        target_agents_dir.mkdir(parents=True, exist_ok=True)
        target_skills_dir.mkdir(parents=True, exist_ok=True)
        target_rules_dir = target / ".claude" / "rules"
        target_rules_dir.mkdir(parents=True, exist_ok=True)

        deployed_agents = []
        skipped_agents = []
        deployed_skills = []
        skipped_skills = []

        # --- Deploy agents ---
        for agent_name in agents_to_deploy:
            src = hub_agents_dir / f"{agent_name}.md"
            dst = target_agents_dir / f"{agent_name}.md"

            if not src.exists():
                skipped_agents.append({"name": agent_name, "reason": "template not found in hub"})
                continue

            content = src.read_text(encoding="utf-8")
            fm, body = _parse_agent_frontmatter(content)

            # Inject skills into frontmatter
            fm["skills"] = ", ".join(skills_to_deploy)


            # Build customized content
            new_content = _build_agent_frontmatter(fm) + "\n" + body

            # Append tech context section if provided
            if tech_context:
                ctx_lines = ["\n\n## Project Tech Stack\n"]
                for key, val in tech_context.items():
                    ctx_lines.append(f"- **{key}**: {val}")
                ctx_lines.append("")
                new_content += "\n".join(ctx_lines)

            dst.write_text(new_content, encoding="utf-8")
            deployed_agents.append({
                "name": agent_name,
                "path": str(dst),
                "skills_injected": skills_to_deploy,
            })

        # --- Deploy skills ---
        for skill_name in skills_to_deploy:
            src_dir = hub_skills_dir / skill_name
            dst_dir = target_skills_dir / skill_name

            if not src_dir.exists():
                skipped_skills.append({"name": skill_name, "reason": "skill not found in hub"})
                continue

            # Copy entire skill directory (overwrite if exists)
            if dst_dir.exists():
                shutil.rmtree(dst_dir)
            shutil.copytree(src_dir, dst_dir)

            # Count files copied
            files = list(dst_dir.rglob("*"))
            file_count = sum(1 for f in files if f.is_file())
            deployed_skills.append({
                "name": skill_name,
                "path": str(dst_dir),
                "files": file_count,
            })

        # --- Deploy language/domain rules ---
        deployed_rules = []
        for rule_name in rules_to_deploy:
            src = hub_rules_dir / rule_name
            dst = target_rules_dir / rule_name

            if not src.exists():
                continue

            # Only copy if not already present (don't overwrite user customizations)
            if not dst.exists():
                shutil.copy2(src, dst)
                deployed_rules.append({"name": rule_name, "path": str(dst)})

        return {
            "success": True,
            "project_path": project_path,
            "tech_stack": tech_stack,
            "agents_deployed": deployed_agents,
            "agents_skipped": skipped_agents,
            "skills_deployed": deployed_skills,
            "skills_skipped": skipped_skills,
            "rules_deployed": deployed_rules,
            "summary": {
                "agents": len(deployed_agents),
                "skills": len(deployed_skills),
                "rules": len(deployed_rules),
                "skipped": len(skipped_agents) + len(skipped_skills),
            },
            "tech_context": tech_context,
        }

    @mcp.tool()
    def list_available_agents_and_skills(
        session_id: str | None = None,
    ) -> dict:
        # readOnlyHint: True
        """List all agents and skills available in the AgentCockpit hub.

        Use this to discover what can be deployed before calling deploy_project_agents.

        Args:
            session_id: Optional session ID

        Returns:
            Lists of available agent names and skill names with descriptions
        """
        hub_dir = get_hub_dir()
        hub_agents_dir = _agents_source()
        hub_skills_dir = _skills_source()

        agents = []
        for f in sorted(hub_agents_dir.glob("*.md")):
            content = f.read_text(encoding="utf-8")
            fm, _ = _parse_agent_frontmatter(content)
            agents.append({
                "name": fm.get("name", f.stem),
                "description": fm.get("description", ""),
                "model": fm.get("model", "sonnet"),
            })

        skills = []
        for d in sorted(hub_skills_dir.iterdir()):
            if d.is_dir():
                skill_file = d / "SKILL.md"
                desc = ""
                if skill_file.exists():
                    content = skill_file.read_text(encoding="utf-8")
                    # Extract description from frontmatter
                    if content.startswith("---"):
                        try:
                            end = content.index("---", 3)
                            for line in content[3:end].splitlines():
                                if line.startswith("description:"):
                                    desc = line.partition(":")[2].strip()
                                    break
                        except ValueError:
                            pass
                skills.append({"name": d.name, "description": desc})

        return {
            "agents": agents,
            "skills": skills,
            "tech_skill_map": _TECH_SKILL_MAP,
            "core_agents": _CORE_AGENTS,
            "core_skills": _CORE_SKILLS,
            "hub_dir": str(hub_dir),
        }
