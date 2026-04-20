# `jig init`

Scaffolds a project for jig. One command turns an arbitrary directory
into a token-economy-aware Claude Code project.

```
jig init <path> [--source <spec>] [--dry-run] [--no-warmup]
```

## What it does

Given a target directory:

1. **Read `<path>/.mcp.json`** (if any). Split entries into
   - **local** (stdio command with `"command"` + `"args"`) → candidates
     for jig's proxy pool.
   - **remote** (HTTP with `"url"`) → kept as-is; jig does not broker
     remote MCPs.
2. **Back up** the original `.mcp.json` with a timestamped suffix.
3. **Register** each local MCP in `~/.config/jig/proxy.toml` so jig
   can lazy-spawn it on demand.
4. **Rewrite `.mcp.json`** with exactly two entries: jig itself and
   the remote MCPs.
5. **Copy bundled assets** into `<path>/.claude/`: hooks, rules,
   commands, workflows, plus a rendered `settings.json` with the
   canonical hook pipeline.
6. **Warm up embeddings** (unless `--no-warmup`): connect each proxy,
   list its tools, and embed the descriptions into the global cache
   at `~/.local/share/jig/tools_<model>.db`. First `proxy_tools_search`
   lands instantly.
7. **Print a report**: before/after tool schema count and the resulting
   token reduction estimate.

## Before / after

```
# Before — every session loads N × ~30 schemas
{
  "mcpServers": {
    "serena": {"command": "npx", "args": ["-y", "@modelcontextprotocol/serena"]},
    "context7": {"command": "npx", "args": ["-y", "context7-mcp"]},
    "sequentialthinking": {"command": "docker", "args": ["run", "--rm", "-i", "mcp/sequentialthinking"]},
    "playwright": {"command": "npx", "args": ["-y", "@executeautomation/playwright-mcp-server"]}
  }
}

# After `jig init .`
{
  "mcpServers": {
    "jig": {"command": "uvx", "args": ["jig-mcp"]}
  }
}

# Each proxy kept in ~/.config/jig/proxy.toml, tools embedded in cache.
# Session cost drops from ~120 schemas to 28.
```

## The `--source` flag

Default renders `uvx --from git+https://github.com/Rixmerz/jig jig-mcp`
so a fresh `jig init` works out-of-the-box while jig-mcp is pre-PyPI.
Once jig-mcp is published, pass `--source jig-mcp` (or set
`JIG_SOURCE=jig-mcp`) to render the bare PyPI form:

```json
{"jig": {"command": "uvx", "args": ["jig-mcp"]}}
```

Override with any source spec via `--source` or the `JIG_SOURCE` env var.

Accepted source formats:

| Spec | Effect |
|------|--------|
| `jig-mcp` (default) | `uvx jig-mcp` |
| `git+https://...@tag` | `uvx --from <spec> jig-mcp` |
| `/abs/path/to/jig` | `uvx --from <spec> jig-mcp` |
| `./relative/path` | `uvx --from <spec> jig-mcp` |

## `--dry-run`

Prints the plan (which MCPs migrate, which stay, what .claude/ gets
populated) without touching the filesystem. Use to preview migrations
before committing.

## `--no-warmup`

Skips the embedding warmup step. `proxy_tools_search` will be slow on
the first call (model load + embedding) but init finishes in seconds
instead of minutes. Useful for air-gapped environments or when the
embed model is already cached.

## Idempotence

Running `jig init` twice is safe:

- `.mcp.json` is re-read from the previous output — local MCPs already
  moved to `proxy.toml` are detected and skipped.
- Existing `.claude/` files are overwritten only when their content
  differs (default `shutil.copy2`).
- A new backup is created on each invocation so history is preserved.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `target does not exist` | Wrong path | Use absolute path. |
| `target is not a directory` | Path is a file | Point to parent dir. |
| No MCPs migrated, 0% reduction | `.mcp.json` was empty | Expected; init still populates `.claude/`. |
| First search slow (~30s) | Embed model download | Run `jig doctor` once to pre-fetch the model. |
| Spawn error opening Claude Code | `uvx jig-mcp` fails pre-PyPI | Re-run `jig init` with `--source git+https://github.com/Rixmerz/jig`. |
