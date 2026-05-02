"""Emit jig's bundled Claude assets into a Cursor-compatible ``.cursor/`` tree.

Canonical authoring stays under ``src/jig/assets`` (and ``jig.hooks``); this module
mirrors commands, rules (as ``.mdc``), skills, agents, workflows, hook scripts,
and a ``hooks.json`` that routes through :mod:`jig.hooks.jig_cursor_hook_runner`.
"""
from __future__ import annotations

import json
import re
import shlex
import shutil
import stat
import sys
from pathlib import Path
from typing import Any

import jig

from jig.tools.deployment import (
    _agents_source,
    _build_agent_frontmatter,
    _bundled_assets_dir,
    _parse_agent_frontmatter,
    _rules_source,
    _skills_source,
    bundled_full_catalog,
    deploy_sets_for_stack,
)

_CLAUDE_TO_CURSOR_EVENTS: dict[str, str] = {
    "UserPromptSubmit": "beforeSubmitPrompt",
    "SessionStart": "sessionStart",
    "Stop": "stop",
    "PreToolUse": "preToolUse",
    "PostToolUse": "postToolUse",
}


def _hook_script_from_claude_command(command: str) -> str | None:
    m = re.search(r"/hooks/([^/\"]+\.py)", command)
    if not m:
        return None
    return m.group(1)


def _cursor_command_for_hook(py_exe: str, claude_command: str) -> str | None:
    script = _hook_script_from_claude_command(claude_command)
    if not script or script == "jig_cursor_hook_runner.py":
        return None
    runner = ".cursor/hooks/jig_cursor_hook_runner.py"
    return f"{shlex.quote(py_exe)} {shlex.quote(runner)} {shlex.quote(script)}"


def _build_cursor_hooks_json(py_exe: str) -> dict[str, Any]:
    template = _bundled_assets_dir() / "settings.template.json"
    raw = json.loads(template.read_text(encoding="utf-8"))
    claude_hooks = raw.get("hooks") or {}
    out: dict[str, list[dict[str, Any]]] = {}
    for claude_event, blocks in claude_hooks.items():
        cursor_event = _CLAUDE_TO_CURSOR_EVENTS.get(claude_event)
        if not cursor_event:
            continue
        if not isinstance(blocks, list):
            continue
        bucket = out.setdefault(cursor_event, [])
        for block in blocks:
            if not isinstance(block, dict):
                continue
            matcher = block.get("matcher", "*")
            inner = block.get("hooks") or []
            if not isinstance(inner, list):
                continue
            for h in inner:
                if not isinstance(h, dict) or h.get("type") != "command":
                    continue
                cmd = h.get("command", "")
                if not isinstance(cmd, str):
                    continue
                mapped = _cursor_command_for_hook(py_exe, cmd)
                if not mapped:
                    continue
                entry: dict[str, Any] = {"command": mapped}
                if matcher and matcher != "*":
                    entry["matcher"] = matcher
                timeout = h.get("timeout")
                if isinstance(timeout, (int, float)):
                    entry["timeout"] = int(timeout)
                bucket.append(entry)
    return {"version": 1, "hooks": out}


def _rule_body_to_mdc(content: str, stem: str) -> str:
    if content.lstrip().startswith("---"):
        return content
    desc = f"jig bundled rule ({stem})"
    return (
        f"---\n"
        f"description: {json.dumps(desc)[1:-1]}\n"
        f"alwaysApply: false\n"
        f"---\n\n"
        f"{content.lstrip()}"
    )


def _write_rules_as_mdc(
    rules_src: Path,
    target_rules: Path,
    rule_names: list[str],
) -> list[str]:
    target_rules.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for name in rule_names:
        src = rules_src / name
        if not src.is_file():
            continue
        stem = src.stem
        mdc_name = f"{stem}.mdc"
        body = _rule_body_to_mdc(src.read_text(encoding="utf-8"), stem)
        (target_rules / mdc_name).write_text(body, encoding="utf-8")
        written.append(mdc_name)
    return written


def _copy_skill_trees(skills_src: Path, target_skills: Path, names: list[str]) -> list[str]:
    target_skills.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for name in names:
        src = skills_src / name
        if not src.is_dir():
            continue
        dst = target_skills / name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        copied.append(name)
    return copied


def _deploy_agents_markdown(
    agents_src: Path,
    target_agents: Path,
    agent_names: list[str],
    skills_for_injection: list[str],
) -> list[str]:
    target_agents.mkdir(parents=True, exist_ok=True)
    deployed: list[str] = []
    for name in agent_names:
        src = agents_src / f"{name}.md"
        if not src.is_file():
            continue
        content = src.read_text(encoding="utf-8")
        fm, body = _parse_agent_frontmatter(content)
        fm["skills"] = ", ".join(skills_for_injection)
        new_content = _build_agent_frontmatter(fm) + "\n" + body
        dst = target_agents / f"{name}.md"
        dst.write_text(new_content, encoding="utf-8")
        deployed.append(name)
    return deployed


def _copy_hook_scripts(target_hooks: Path) -> None:
    target_hooks.mkdir(parents=True, exist_ok=True)
    hooks_root = Path(jig.__file__).parent / "hooks"
    for entry in hooks_root.iterdir():
        if not entry.is_file() or not entry.name.endswith(".py"):
            continue
        if entry.name.startswith("_") and entry.name != "_common.py":
            continue
        dest = target_hooks / entry.name
        dest.write_bytes(entry.read_bytes())
        mode = dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        dest.chmod(mode)


def emit_cursor_bundle(
    project: Path,
    *,
    py_exe: str,
    tech_stack: list[str] | None,
    include_core: bool = True,
    extra_agents: list[str] | None = None,
    extra_skills: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Write ``.cursor/`` mirror. Does not modify ``.mcp.json``.

    When ``tech_stack`` is ``None``, deploy the **full** bundled catalog (all
    agents, skills, rules). Otherwise resolve sets like ``deploy_project_agents``.
    """
    project = project.expanduser().resolve()
    if not project.is_dir():
        return {"success": False, "error": f"not a directory: {project}"}

    cursor = project / ".cursor"
    hooks_dir = cursor / "hooks"
    commands_dir = cursor / "commands"
    skills_dir = cursor / "skills"
    agents_dir = cursor / "agents"
    rules_dir = cursor / "rules"
    jig_mirror = cursor / "jig"
    wf_mirror = jig_mirror / "workflows"

    assets = _bundled_assets_dir()
    hub_agents = _agents_source()
    hub_skills = _skills_source()
    hub_rules = _rules_source()

    if tech_stack is None:
        catalog = bundled_full_catalog()
        agents_list = catalog["agents"]
        skills_list = catalog["skills"]
        rules_list = catalog["rules"]
    else:
        agents_list, skills_list, rules_list = deploy_sets_for_stack(
            tech_stack,
            extra_agents=extra_agents,
            extra_skills=extra_skills,
            include_core=include_core,
        )

    plan = {
        "project": str(project),
        "cursor_dir": str(cursor),
        "agents": agents_list,
        "skills": skills_list,
        "rules_mdc": [f"{Path(n).stem}.mdc" for n in rules_list],
    }
    if dry_run:
        return {"success": True, "dry_run": True, **plan}

    commands_dir.mkdir(parents=True, exist_ok=True)
    wf_mirror.mkdir(parents=True, exist_ok=True)
    cmd_src = assets / "commands"
    if cmd_src.is_dir():
        for item in cmd_src.iterdir():
            if item.is_file():
                shutil.copy2(item, commands_dir / item.name)
    wf_src = assets / "workflows"
    if wf_src.is_dir():
        for item in wf_src.iterdir():
            if item.is_file():
                shutil.copy2(item, wf_mirror / item.name)

    _copy_hook_scripts(hooks_dir)
    hooks_json = _build_cursor_hooks_json(py_exe)
    (cursor / "hooks.json").write_text(
        json.dumps(hooks_json, indent=2) + "\n",
        encoding="utf-8",
    )

    rules_written = _write_rules_as_mdc(hub_rules, rules_dir, rules_list)
    skills_copied = _copy_skill_trees(hub_skills, skills_dir, skills_list)
    agents_written = _deploy_agents_markdown(
        hub_agents, agents_dir, agents_list, skills_list
    )

    readme = cursor / "README.jig-cursor.md"
    readme.write_text(
        _CURSOR_README_TEMPLATE.format(project=str(project)),
        encoding="utf-8",
    )

    return {
        "success": True,
        "dry_run": False,
        **plan,
        "rules_written": rules_written,
        "skills_copied": skills_copied,
        "agents_written": agents_written,
        "hooks_json": str(cursor / "hooks.json"),
    }


_CURSOR_README_TEMPLATE = """# Jig → Cursor emit

This ``.cursor/`` tree was generated by **jig** from the same bundled assets used
for Claude Code (``src/jig/assets`` in the jig package). The canonical workflow
state and graph files still live under ``.claude/`` — run ``jig init`` first so
MCP + graph hooks resolve paths there.

## Contents

- ``hooks.json`` + ``hooks/`` — Cursor hook events, routed through
  ``jig_cursor_hook_runner.py`` (maps ``decision``/``hookSpecificOutput`` toward
  Cursor JSON where possible).
- ``commands/``, ``skills/``, ``agents/``, ``rules/*.mdc`` — mirrors of jig assets.
- ``jig/workflows/`` — copy of bundled YAML workflow templates (reference).

## Regenerate

```bash
jig emit-cursor "{project}"
# or, after ``jig init``:
jig init "{project}" --cursor
```

## Limits

Session hooks (bootstrap, user memory, stop summary) assume Claude Code stdin and
transcripts; under Cursor they may be no-ops or partial until a native adapter exists.
Pre/post tool hooks are the best-supported path.
"""


def run(args: argparse.Namespace) -> int:
    project = Path(args.path).expanduser().resolve()
    py_exe = getattr(args, "python", None) or sys.executable
    tech = getattr(args, "tech_stack", None)
    include_core = not getattr(args, "no_core_agents", False)
    xa = getattr(args, "extra_agents", None) or None
    xs = getattr(args, "extra_skills", None) or None
    if xa:
        xa = list(dict.fromkeys(xa))
    if xs:
        xs = list(dict.fromkeys(xs))
    result = emit_cursor_bundle(
        project,
        py_exe=py_exe,
        tech_stack=tech,
        include_core=include_core,
        extra_agents=xa,
        extra_skills=xs,
        dry_run=args.dry_run,
    )
    if not result.get("success"):
        print(f"[jig.emit-cursor] {result.get('error', 'failed')}", file=sys.stderr)
        return 2
    if result.get("dry_run"):
        print(json.dumps(result, indent=2))
        return 0
    print(f"[jig.emit-cursor] wrote {result['cursor_dir']}")
    print(f"  agents:  {len(result.get('agents_written', []))}")
    print(f"  skills:  {len(result.get('skills_copied', []))}")
    print(f"  rules:   {len(result.get('rules_written', []))}")
    print(f"  hooks:   {result.get('hooks_json')}")
    return 0


def add_parser(sub: Any) -> None:
    p = sub.add_parser(
        "emit-cursor",
        help="Mirror bundled jig assets into .cursor/ (rules, skills, agents, hooks, commands)",
    )
    p.add_argument("path", help="Target project path (repo root)")
    p.add_argument(
        "--tech-stack",
        nargs="+",
        metavar="TECH",
        default=None,
        help=(
            "Optional stack keywords (e.g. python react). When omitted, emit the "
            "**full** bundled catalog (all agents, skills, rules)."
        ),
    )
    p.add_argument(
        "--no-core-agents",
        action="store_true",
        help="With --tech-stack, exclude core orchestrator/debugger/reviewer resolution",
    )
    p.add_argument(
        "--extra-agent",
        action="append",
        default=None,
        dest="extra_agents",
        help="Extra agent stem (repeatable); only used with --tech-stack",
    )
    p.add_argument(
        "--extra-skill",
        action="append",
        default=None,
        dest="extra_skills",
        help="Extra skill folder name (repeatable); only used with --tech-stack",
    )
    p.add_argument(
        "--python",
        default=None,
        help="Python executable for hook commands (default: sys.executable)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved manifest without writing files",
    )
    p.set_defaults(func=run)


__all__ = ["emit_cursor_bundle", "add_parser", "run"]
