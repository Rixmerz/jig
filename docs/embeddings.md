# Embeddings

Semantic search across proxied tools is cache-driven: the embedding
model runs once at proxy connect time, vectors go into SQLite, and
every subsequent `proxy_tools_search` is a pure lookup. No live MCP
connection required.

## Model

| Default | `BAAI/bge-large-en-v1.5` |
|---------|--------------------------|
| Dimension | 1024 |
| Backend | [`fastembed`](https://github.com/qdrant/fastembed) |
| Source | ONNX, downloaded to `~/.cache/huggingface/hub/` on first use |
| Size on disk | ~1.3 GB |
| First-search latency | ~2–10s (model load), then <50ms per query |

Override with the `JIG_EMBED_MODEL` env var:

```bash
# Smaller / faster, less accurate
export JIG_EMBED_MODEL=BAAI/bge-small-en-v1.5   # 384D, ~130 MB

# Alternative multilingual model
export JIG_EMBED_MODEL=intfloat/multilingual-e5-large  # 1024D, ~2.2 GB
```

Any fastembed-supported model works. When the model changes, the
cache path changes too (it's keyed by model slug), so switching never
mixes dimensions mid-DB.

## Cache

```
~/.local/share/jig/tools_bge-large-en-v1.5.db      ← default
~/.local/share/jig/tools_bge-small-en-v1.5.db      ← if JIG_EMBED_MODEL switched
```

Schema:

```sql
CREATE TABLE tools (
    mcp_name     TEXT NOT NULL,
    tool_name    TEXT NOT NULL,
    text_hash    TEXT NOT NULL,        -- SHA of desc + schema
    description  TEXT NOT NULL,
    input_schema TEXT NOT NULL,        -- JSON
    embedding    BLOB NOT NULL,        -- float32 little-endian, length = 1024
    updated_at   REAL NOT NULL,
    PRIMARY KEY (mcp_name, tool_name)
);
CREATE INDEX idx_tools_mcp ON tools(mcp_name);
```

`text_hash` lets `proxy_refresh` skip tools whose description + schema
haven't changed since the last embed.

## When embeddings happen

| Event | Trigger |
|-------|---------|
| Background warmup at server start | `server.serve()` schedules `_warmup_embed_model()` as a non-blocking task so the model loads before the first search. |
| At `proxy_add(warmup=True)` | Spawns the proxy, calls `tools/list`, embeds each description. |
| At `jig init` (unless `--no-warmup`) | Same as `proxy_add` for every migrated local MCP. |
| On demand via `proxy_refresh(name)` | After upgrading the underlying MCP or adding tools. |
| At internal-proxy registration | `_tool_archive.archive_all` embeds the 27 internal tools into MCPs named `graph`, `experience`, `trend`, etc. |

## Search

```python
proxy_tools_search(
    query="find a function definition in the codebase",
    top_k=5,
    proxy=None,   # or filter to a single MCP, e.g. "serena"
)
```

Scoring is cosine similarity over the query embedding. Typical scores:

- `> 0.80`: semantic near-match. The description directly mentions the
  capability you asked about.
- `0.60 – 0.80`: relevant but broader. Worth inspecting.
- `< 0.50`: noise. Usually means the query should be rephrased.

No BM25 fallback yet — if `fastembed.available == False` (e.g. model
never downloaded and no network), search returns an empty list.
`jig doctor` flags this.

## Updating the embeddings

Force a fresh embed of a proxy:

```bash
# Via MCP
proxy_refresh(name="serena")

# Or manually in Python
from jig.core import embed_cache
embed_cache.remove_mcp("serena")   # clear cached rows
# Then let proxy_refresh re-embed on next connect.
```

`jig doctor --prefetch` triggers a model download so the first session
doesn't pay the 1.3 GB price.

## Size and performance

A 100-tool corpus takes ~400 KB on disk. Search over 100 tools is
sub-millisecond (pure Python cosine over float32 arrays). For larger
fleets (1000+ tools), consider swapping to a smaller model or an
approximate-nearest-neighbour index — jig stays linear today because
it's unnecessary at realistic sizes.
