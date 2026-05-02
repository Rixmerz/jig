"""`jig init <path>` — scaffold a project for jig.

Flow:
    1. Read target .mcp.json (if any), split local (stdio command) vs remote (url)
    2. Prompt to migrate local MCPs into the jig proxy config
    3. Write ~/.config/jig/proxy.toml (global, secrets live here)
    4. Write stripped .mcp.json (only jig + remotes) with timestamped backup
    5. Copy bundled hooks/rules/commands/workflows into <project>/.claude/
    6. Render canonical settings.template.json → <project>/.claude/settings.json
    7. Warm up: connect each proxy, tools/list, embed into global cache
    8. Print before/after token-economy report

This module is intentionally synchronous around a narrow async call for warmup.
The rest uses plain I/O so that a bare `jig init` works without an event loop.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import time
from importlib import resources
from pathlib import Path

from jig.core import paths
from jig.engines import proxy_pool


_DEFAULT_SOURCE = "git+https://github.com/Rixmerz/jig"


def _resolve_jig_source(args: argparse.Namespace) -> tuple[str, list[str]]:
    """Pick the command+args for the rendered ``jig`` entry in .mcp.json.

    Precedence: ``--source`` flag > ``JIG_SOURCE`` env > auto-detect
    (tool-installed) > git+https fallback.

    Source-shape rules:
    - ``tool`` (special): render ``{"command": "jig-mcp"}`` — assumes
      ``uv tool install`` was run and ``jig-mcp`` is on ``PATH``.
      This is the recommended mode: spawn is instant, no uv cache
      contention, multiple Claude Code sessions can share the install.
    - Bare package name (``jig-mcp``): rendered as ``uvx <name>``
      (PyPI form, once published).
    - ``git+…`` / ``.`` / contains ``/``: wrapped as
      ``uvx --from <spec> jig-mcp``. Rebuilds on each spawn and locks
      the uv cache — fine for a single session, painful across many.

    Auto-detect: when neither ``--source`` nor ``JIG_SOURCE`` is set
    and ``jig-mcp`` is already on ``PATH``, the tool form is chosen.
    Running ``uv tool install git+https://github.com/Rixmerz/jig``
    once therefore wins the lock-free render for every subsequent
    ``jig init`` without a flag.
    """
    explicit = getattr(args, "source", None) or os.environ.get("JIG_SOURCE")
    if explicit == "tool":
        return "jig-mcp", []
    if explicit is None and _tool_install_detected():
        return "jig-mcp", []
    source = explicit or _DEFAULT_SOURCE
    if source.startswith("git+") or source.startswith(".") or "/" in source:
        return "uvx", ["--from", source, "jig-mcp"]
    return "uvx", [source]


def _tool_install_detected() -> bool:
    """True when jig-mcp is reachable as a bare command.

    Two signals:
    - ``jig-mcp`` is on the current PATH — the obvious case.
    - Or the *running* jig package lives under a ``uv tool install``
      tree (``~/.local/share/uv/tools/jig-mcp/``). MCP subprocesses
      spawned by Claude Code inherit the user's shell PATH, which
      usually contains ``~/.local/bin`` where the entry-point script
      lands; but the subprocess the server itself runs in may have a
      stripped PATH. If the package itself is tool-installed, the
      entry-point is reachable by definition.
    """
    if shutil.which("jig-mcp"):
        return True
    try:
        import jig as _jig_pkg
        pkg_path = str(Path(_jig_pkg.__file__).resolve())
    except Exception:
        return False
    tool_root = str((Path.home() / ".local" / "share" / "uv" / "tools").resolve())
    return pkg_path.startswith(tool_root)


def run(args: argparse.Namespace) -> int:
    target = Path(args.path).expanduser().resolve()
    if not target.exists():
        print(f"[jig.init] target does not exist: {target}", file=sys.stderr)
        return 2
    if not target.is_dir():
        print(f"[jig.init] target is not a directory: {target}", file=sys.stderr)
        return 2

    mcp_json_path = target / ".mcp.json"
    local_mcps, remote_mcps = _split_mcp_json(mcp_json_path)
    before_count = sum(_rough_tool_estimate(m) for m in (*local_mcps.values(), *remote_mcps.values()))

    _print_plan(
        target,
        local_mcps,
        remote_mcps,
        dry_run=args.dry_run,
        emit_cursor=getattr(args, "cursor", False),
    )
    if args.dry_run:
        return 0

    # 1. Backup original .mcp.json
    if mcp_json_path.exists():
        backup = mcp_json_path.with_suffix(f".json.jig-backup-{int(time.time())}")
        shutil.copy2(mcp_json_path, backup)
        print(f"[jig.init] backed up .mcp.json → {backup.name}")

    # 2. Register local MCPs as proxies
    migrated = 0
    for name, spec in local_mcps.items():
        proxy_pool_cfg = {
            "name": name,
            "command": spec["command"],
            "args": list(spec.get("args", [])),
            "env": dict(spec.get("env", {})),
        }
        asyncio.run(proxy_pool.proxy_register(**proxy_pool_cfg))
        migrated += 1
    if migrated:
        print(f"[jig.init] migrated {migrated} local MCP(s) to proxy config")

    # 3. Write stripped .mcp.json
    jig_cmd, jig_args = _resolve_jig_source(args)
    new_mcp_json = {
        "mcpServers": {
            "jig": {"command": jig_cmd, "args": jig_args},
            **remote_mcps,
        }
    }
    mcp_json_path.write_text(
        json.dumps(new_mcp_json, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[jig.init] wrote {mcp_json_path.name} (jig + {len(remote_mcps)} remote MCPs)")

    # 4. Copy assets to <project>/.claude/
    claude_dir = target / ".claude"
    _copy_assets(claude_dir)

    if getattr(args, "cursor", False):
        from jig.cli.cursor_emit import emit_cursor_bundle

        cur = emit_cursor_bundle(
            target,
            py_exe=sys.executable,
            tech_stack=None,
            dry_run=False,
        )
        if not cur.get("success"):
            print(
                f"[jig.init] emit-cursor failed: {cur.get('error', 'unknown')}",
                file=sys.stderr,
            )
            return 2
        print(
            f"[jig.init] also wrote Cursor bundle → {target / '.cursor'} "
            f"(agents/skills/rules/hooks/commands; see .cursor/README.jig-cursor.md)"
        )

    # 5. Warm up embeddings
    embedded = 0
    if not args.no_warmup and migrated:
        print("[jig.init] warming up tool embeddings...")
        embedded = asyncio.run(_warmup_all(list(local_mcps)))
        print(f"[jig.init] embedded {embedded} tool definitions")

    after_count = len(remote_mcps) + 1  # jig itself
    _print_report(before_count, after_count, embedded, migrated)
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _split_mcp_json(path: Path) -> tuple[dict[str, dict], dict[str, dict]]:
    """Return (local_stdio_mcps, remote_mcps)."""
    if not path.exists():
        return {}, {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[jig.init] .mcp.json parse error: {e}", file=sys.stderr)
        return {}, {}
    servers = data.get("mcpServers") or data.get("servers") or {}
    if not isinstance(servers, dict):
        return {}, {}
    local: dict[str, dict] = {}
    remote: dict[str, dict] = {}
    for name, spec in servers.items():
        if not isinstance(spec, dict) or name == "jig":
            continue
        if spec.get("command"):
            local[name] = spec
        elif spec.get("url") or spec.get("type") == "http":
            remote[name] = spec
        else:
            remote[name] = spec  # conservative: don't break unknown shapes
    return local, remote


def _rough_tool_estimate(_spec: dict) -> int:
    """Rough heuristic: assume an avg MCP exposes ~25 tools."""
    return 25


"""Rule files that apply regardless of tech stack. Stack-specific rules
(python.md, typescript.md, rust.md, ui.md, ...) are deferred to
`deploy_project_agents`, which copies only what the declared stack needs."""
BASE_RULES: frozenset[str] = frozenset({
    "autonomous-strategy.md",
    "commit-discipline.md",
    "jig-methodology.md",
    "qa.md",
    "quality-feedback.md",
    "security-awareness.md",
})


def _copy_assets(claude_dir: Path) -> None:
    """Populate <project>/.claude/ with jig's base layer.

    Base means: hooks (all), commands (all), workflows (all), the canonical
    settings.json pipeline, and the universal rules listed in ``BASE_RULES``.

    Explicitly **not** copied here:
    - Stack-specific rules (python.md, rust.md, ui.md, ...)  — deferred to
      ``deploy_project_agents(tech_stack=...)``.
    - Agents — on-demand via ``deploy_project_agents``.
    - Skills — on-demand via ``deploy_project_agents`` + ``jig_guide``.
    """
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "hooks").mkdir(exist_ok=True)
    (claude_dir / "rules").mkdir(exist_ok=True)
    (claude_dir / "commands").mkdir(exist_ok=True)
    (claude_dir / "workflows").mkdir(exist_ok=True)

    # 1. Hooks: copy jig's hooks/ module content as scripts
    import jig.hooks as hooks_pkg

    hooks_path = resources.files(hooks_pkg)
    for entry in hooks_path.iterdir():
        if entry.name.startswith("_") or not entry.name.endswith(".py"):
            if entry.name != "_common.py":
                continue
        if entry.name == "jig_cursor_hook_runner.py":
            continue  # Cursor-only shim; emitted via ``jig emit-cursor``
        if entry.is_file():
            dest_path = claude_dir / "hooks" / entry.name
            dest_path.write_bytes(entry.read_bytes())
            dest_path.chmod(dest_path.stat().st_mode | 0o111)  # chmod +x

    # 2. Commands + workflows: copy wholesale
    import jig.assets as assets_pkg

    assets_path = resources.files(assets_pkg)
    for sub in ("commands", "workflows"):
        src = assets_path / sub
        if src.is_dir():
            target = claude_dir / sub
            for item in src.iterdir():
                if item.is_file():
                    (target / item.name).write_bytes(item.read_bytes())

    # 3. Rules: only the universal ones. Stack rules land later via
    # deploy_project_agents.
    rules_src = assets_path / "rules"
    if rules_src.is_dir():
        for item in rules_src.iterdir():
            if item.is_file() and item.name in BASE_RULES:
                (claude_dir / "rules" / item.name).write_bytes(item.read_bytes())

    # 4. settings.json from template. Substitute the bare ``python3``
    # command with ``sys.executable`` — the Python that the jig-mcp tool
    # install uses. Claude Code spawns hooks by literal command-string;
    # a bare ``python3`` picks up whatever interpreter happens to be on
    # ``PATH``, which usually lacks jig's dependencies and silently
    # fails to run anything that imports ``jig.engines``.
    settings_src = assets_path / "settings.template.json"
    if settings_src.is_file():
        raw = settings_src.read_text(encoding="utf-8")
        # Only replace at word boundaries so "python3" inside a path or
        # identifier is untouched. The template shape is
        # ``"command": "python3 \"$CLAUDE_PROJECT_DIR/..."``.
        rewired = raw.replace(
            '"command": "python3 ',
            f'"command": "{sys.executable} ',
        )
        (claude_dir / "settings.json").write_text(rewired, encoding="utf-8")

    print(
        f"[jig.init] populated {claude_dir}/ "
        f"(hooks, commands, workflows, {len(BASE_RULES)} base rules, settings.json)"
    )


async def _warmup_all(names: list[str]) -> int:
    total = 0
    for name in names:
        try:
            total += await proxy_pool.proxy_refresh_embeddings(name)
        except Exception as e:
            print(f"[jig.init] warmup {name} failed: {e}", file=sys.stderr)
    return total


def _print_plan(
    target: Path,
    local: dict[str, dict],
    remote: dict[str, dict],
    *,
    dry_run: bool,
    emit_cursor: bool = False,
) -> None:
    header = "[DRY RUN] " if dry_run else ""
    print(f"{header}jig init {target}")
    print()
    print(f"  Local MCPs to migrate ({len(local)}):")
    for name, spec in sorted(local.items()):
        cmd = spec.get("command", "?")
        args = " ".join(spec.get("args", []))
        print(f"    - {name}: {cmd} {args}".rstrip())
    print()
    print(f"  Remote MCPs (kept in .mcp.json) ({len(remote)}):")
    for name in sorted(remote):
        print(f"    - {name}")
    print()
    print("  Actions:")
    print("    1. Backup .mcp.json → .mcp.json.jig-backup-<timestamp>")
    print("    2. Write ~/.config/jig/proxy.toml with local MCP definitions")
    print("    3. Rewrite .mcp.json with only jig + remote MCPs")
    print("    4. Copy hooks, rules, commands, workflows → .claude/")
    if emit_cursor:
        print("    4b. Mirror full bundle → .cursor/ (rules as .mdc, hooks.json, …)")
    print("    5. Warm up tool embeddings (unless --no-warmup)")
    print()


def _print_report(before: int, after: int, embedded: int, migrated: int) -> None:
    saved = before - after
    pct = int(100 * saved / before) if before else 0
    print()
    print(" ─── jig init complete ─── ")
    print(f"   Before: ~{before} tool schemas in .mcp.json")
    print(f"   After:  ~{after} tool schemas in .mcp.json")
    print(f"   Reduction: ~{pct}%")
    print(f"   Migrated:  {migrated} MCP(s) to proxy")
    print(f"   Embedded:  {embedded} tool definitions in global cache")
    print(f"   Config:    {proxy_pool.proxy_config_path()}")
    print(f"   Data:      {paths.data_dir()}")
    print()
    print("Open Claude Code in this directory. Try: jig_guide(topic=\"getting-started\")")


__all__ = ["run"]
