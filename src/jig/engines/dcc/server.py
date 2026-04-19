"""FastMCP server for DeltaCodeCube.

Multi-dimensional code indexing - represent code as points in 63D feature space
for similarity search, impact analysis, and change detection.

This module provides the entry point for the MCP server.
All tools are organized in the tools/ subpackage:
- tools/core.py: Core indexing tools (index_file, index_directory, etc.)
- tools/contracts.py: Contract/dependency tools
- tools/deltas.py: Delta and tension tools
- tools/search.py: Advanced search tools
- tools/analysis.py: Analysis tools (smells, clustering, debt, etc.)
- tools/visualizations.py: HTML visualization generators
"""

from fastmcp import FastMCP

from jig.engines.dcc.tools import register_all_tools

# Create FastMCP server
mcp = FastMCP("deltacodecube")

# Register all tools from submodules
register_all_tools(mcp)
