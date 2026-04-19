"""Entry point for deltacodecube when run with uvx."""

import sys


def main() -> int:
    """Run the DeltaCodeCube MCP server."""
    from jig.engines.dcc.server import mcp

    mcp.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
