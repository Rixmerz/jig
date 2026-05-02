# Cursor asset mirror (`jig emit-cursor`)

Jig’s **canonical** authoring layout targets **Claude Code** (`.claude/`). The
`emit-cursor` path mirrors the same bundled material into **Cursor**’s project
layout (`.cursor/`) so teams can use one source tree in the package and still
get rules, skills, slash commands, hook scripts, and a `hooks.json` wired for
Cursor.

## Commands

```bash
# After `jig init <project>` (or any time you want a full mirror):
jig emit-cursor <project>

# Same stack filter as `jig resync --agents …`:
jig emit-cursor <project> --tech-stack python react

# Dry-run manifest only:
jig emit-cursor <project> --dry-run
```

Shorthand during init:

```bash
jig init <project> --cursor
```

Refresh alongside `.claude/`:

```bash
jig resync <project> --cursor
jig resync <project> --agents python --cursor   # Cursor mirror matches stack filter
```

## What gets written

| Area | Cursor location | Notes |
|------|-----------------|--------|
| Hook scripts | `.cursor/hooks/*.py` | Same Python as Claude; includes `_common.py` and `jig_cursor_hook_runner.py`. |
| Hook wiring | `.cursor/hooks.json` | Events mapped from `settings.template.json` (e.g. `PreToolUse` → `preToolUse`). Commands run through the runner for JSON mapping. |
| Rules | `.cursor/rules/*.mdc` | Plain `.md` rules get a small YAML header (`alwaysApply: false`). |
| Skills | `.cursor/skills/<name>/` | Full directory copy (default: **entire** catalog when no `--tech-stack`). |
| Agents | `.cursor/agents/*.md` | Same markdown as `.claude/agents/` with skills injected in frontmatter. |
| Commands | `.cursor/commands/*.md` | Bundled slash-command markdown. |
| Workflows (reference) | `.cursor/jig/workflows/` | YAML copies for discovery; graph state still uses `.claude/workflow/`. |

## Runtime expectations

- **MCP + graph** still expect `.claude/` and XDG state. Run `jig init` first; do
  not delete `.claude/` if you use jig’s MCP workflows.
- **Session hooks** (`session_bootstrap`, `user_memory_injector`, `session_knowledge_capture`)
  assume Claude Code transcripts and event payloads. Under Cursor they may be
  partial or no-ops until a dedicated adapter exists.
- **Pre/post tool hooks** are the best-supported path: the runner sets
  `CLAUDE_PROJECT_DIR` from `CURSOR_WORKSPACE_ROOT` / `VSCODE_WORKSPACE_FOLDER`
  / cwd, and maps `{"decision":"approve|block"}` to Cursor’s `permission` field
  where applicable. `hookSpecificOutput.additionalContext` is mapped to
  `additional_context`.

See `.cursor/README.jig-cursor.md` in an emitted project for a short recap.
