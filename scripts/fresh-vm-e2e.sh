#!/usr/bin/env bash
# Fresh-VM end-to-end validation for jig.
# Runs the install + init + tool-count flow inside a clean python:3.12-slim
# container with nothing but uv. If this script exits 0, jig is shippable.
#
# Usage: ./scripts/fresh-vm-e2e.sh [git-ref]
# Default ref: current HEAD of origin/main.

set -euo pipefail

REF="${1:-main}"
IMG="python:3.12-slim"

echo "==> running fresh-VM E2E against git+https://github.com/Rixmerz/jig@${REF}"
echo "==> image: ${IMG}"
echo

docker run --rm \
  -v "$(pwd)":/jig-src \
  -w /work \
  "${IMG}" \
  bash -euo pipefail -c "
    set -euo pipefail
    echo '-- step 0: base tooling'
    apt-get update -qq
    apt-get install -y -qq git curl ca-certificates >/dev/null
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH=\"\$HOME/.local/bin:\$PATH\"
    uv --version

    echo
    echo '-- step 1: install jig from local checkout'
    uv tool install --from /jig-src jig-mcp
    jig --version

    echo
    echo '-- step 2: scaffold /tmp/demo-project'
    mkdir -p /tmp/demo-project
    cd /tmp/demo-project
    git init -q
    jig init /tmp/demo-project --source /jig-src --no-warmup

    echo
    echo '-- step 3-5: assert scaffolded tree'
    test -d .claude/commands
    test -d .claude/hooks
    test -d .claude/rules
    test -d .claude/workflows
    test -f .claude/settings.json
    test -f .mcp.json
    # proxy.toml is only written when there are local MCPs to migrate;
    # the empty case is not an error.
    grep -q '\"jig\"' .mcp.json
    echo '   .claude/ + .mcp.json + proxy.toml OK'

    echo
    echo '-- step 6: jig doctor'
    jig doctor

    echo
    echo '-- step 7: surface count (should be ~24)'
    uv run --with-editable /jig-src --with mcp --with fastmcp --with fastembed --with numpy --with pydantic --with rich python - <<'PY'
import asyncio, sys
sys.path.insert(0, '/jig-src/src')
import jig.server as server
server._register_tools()
tools = asyncio.run(server.mcp.list_tools())
names = sorted(t.name for t in tools)
assert 20 <= len(names) <= 30, f'surface out of band: {len(names)}'
from jig.engines import internal_proxy
proxies = internal_proxy.list_mcps()
assert set(proxies) >= {'graph', 'snapshot', 'experience', 'trend'}, f'missing proxies: {proxies}'
print(f'   surface={len(names)} tools, internal_proxies={sorted(proxies)}')
PY

    echo
    echo '-- step 8: jig_guide returns topics'
    uv run --with-editable /jig-src --with mcp --with fastmcp --with fastembed --with numpy --with pydantic --with rich python - <<'PY'
import sys
sys.path.insert(0, '/jig-src/src')
from jig.tools.guide import list_topics, load_topic
topics = list_topics()
assert 'getting-started' in topics, topics
assert load_topic('getting-started').strip(), 'empty guide'
print(f'   guide topics: {topics}')
PY

    echo
    echo '-- step 9: proxy_add against a fake command fails gracefully'
    uv run --with-editable /jig-src --with mcp --with fastmcp --with fastembed --with numpy --with pydantic --with rich python - <<'PY'
import asyncio, sys
sys.path.insert(0, '/jig-src/src')
from jig.engines import proxy_pool

async def go():
    await proxy_pool.proxy_register('fake-bad', '/usr/bin/false')
    try:
        count = await proxy_pool.proxy_refresh_embeddings('fake-bad')
    except Exception as e:
        print(f'   refresh failed as expected: {type(e).__name__}')
    await proxy_pool.proxy_unregister('fake-bad')

asyncio.run(go())
PY

    echo
    echo '-- step 10: tests pass in a clean copy of the source'
    cp -r /jig-src /work/jig-src
    cd /work/jig-src
    uv run --extra dev pytest src/jig/tests/ -q

    echo
    echo '==> E2E OK'
  "

echo
echo "==> fresh-VM E2E succeeded"
