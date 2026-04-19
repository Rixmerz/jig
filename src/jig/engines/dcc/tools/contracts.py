"""Contract/dependency tools for DeltaCodeCube."""

from typing import Any

from jig.engines.dcc.db.database import get_connection
from jig.engines.dcc.cube import DeltaCodeCube


def register_contract_tools(mcp):
    """Register contract tools with MCP server."""

    @mcp.tool()
    def cube_get_contracts(
        path: str | None = None,
        direction: str = "both",
        limit: int = 100,
    ) -> dict[str, Any]:
        """
        Get contracts (dependencies) between code files.

        A contract represents an import/require relationship between two files.
        Each contract includes a baseline_distance that represents the "healthy"
        distance between caller and callee in the 63D feature space.

        Args:
            path: Optional file path to filter contracts for a specific file.
            direction: Filter direction when path is provided:
                      - 'incoming': Files that import this file (dependents)
                      - 'outgoing': Files this file imports (dependencies)
                      - 'both': All contracts involving this file (default)
            limit: Maximum contracts to return (default: 100).

        Returns:
            Contract list with caller/callee info and baseline distances.
        """
        with get_connection() as conn:
            cube = DeltaCodeCube(conn)
            contracts = cube.get_contracts(file_path=path, direction=direction, limit=limit)
            return {"contracts": contracts, "count": len(contracts)}

    @mcp.tool()
    def cube_get_contract_stats() -> dict[str, Any]:
        """
        Get statistics about detected contracts.

        Returns total contracts, breakdown by type, and distance statistics.

        Returns:
            Contract statistics.
        """
        with get_connection() as conn:
            cube = DeltaCodeCube(conn)
            return cube.get_contract_stats()
