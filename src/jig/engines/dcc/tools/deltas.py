"""Delta and tension tools for DeltaCodeCube."""

from typing import Any

from jig.engines.dcc.db.database import get_connection
from jig.engines.dcc.cube import DeltaCodeCube
from jig.engines.dcc.utils import convert_numpy_types


def register_delta_tools(mcp):
    """Register delta and tension tools with MCP server."""

    @mcp.tool()
    def cube_reindex(path: str) -> dict[str, Any]:
        """
        Re-index a file and detect changes (deltas) and tensions.

        When a code file changes, this tool:
        1. Compares the new code with the previously indexed version
        2. Creates a Delta recording the movement in 63D feature space
        3. Detects any Tensions (contracts that may be broken)
        4. Updates the CodePoint in the database

        Use this after modifying a file to see what impact the changes have.

        Args:
            path: Absolute path to the file that changed.

        Returns:
            Reindex result with delta and detected tensions.
        """
        with get_connection() as conn:
            cube = DeltaCodeCube(conn)
            return convert_numpy_types(cube.reindex_file(path))

    @mcp.tool()
    def cube_analyze_impact(path: str) -> dict[str, Any]:
        """
        Analyze potential impact if a file were to change.

        Shows all files that depend on this file (import it) and their
        current distances in the 63D feature space. Useful for:
        - Understanding dependencies before making changes
        - Identifying high-impact files
        - Planning refactoring

        Args:
            path: Absolute path to the file to analyze.

        Returns:
            Impact analysis with list of dependent files and their distances.
        """
        with get_connection() as conn:
            cube = DeltaCodeCube(conn)
            return convert_numpy_types(cube.analyze_impact(path))

    @mcp.tool()
    def cube_get_tensions(
        status: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """
        Get detected tensions (potential contract violations).

        A Tension is created when a code file changes and its distance to
        dependent files deviates significantly from the baseline. This indicates
        the change may have broken implicit dependencies.

        Args:
            status: Filter by status:
                   - 'detected': New tensions not yet reviewed
                   - 'reviewed': Tensions that have been seen
                   - 'resolved': Fixed tensions
                   - 'ignored': Tensions marked as non-issues
                   - None: All tensions (default)
            limit: Maximum tensions to return (default: 50).

        Returns:
            List of tensions with severity and suggested actions.
        """
        with get_connection() as conn:
            cube = DeltaCodeCube(conn)
            tensions = cube.get_tensions(status=status, limit=limit)
            stats = cube.get_tension_stats()
            return {
                "tensions": tensions,
                "count": len(tensions),
                "stats": stats,
            }

    @mcp.tool()
    def cube_resolve_tension(tension_id: str, status: str = "resolved") -> dict[str, Any]:
        """
        Update the status of a tension.

        After reviewing a tension, mark it as resolved, ignored, or reviewed.

        Args:
            tension_id: ID of the tension to update.
            status: New status:
                   - 'reviewed': Marked as seen but not yet fixed
                   - 'resolved': Fixed and no longer an issue
                   - 'ignored': Not a real issue, ignore it

        Returns:
            Update result.
        """
        with get_connection() as conn:
            cube = DeltaCodeCube(conn)
            success = cube.resolve_tension(tension_id, status)
            return {
                "success": success,
                "tension_id": tension_id,
                "new_status": status if success else None,
                "message": "Tension updated." if success else "Tension not found.",
            }

    @mcp.tool()
    def cube_get_deltas(limit: int = 20) -> dict[str, Any]:
        """
        Get recent code changes (deltas).

        Shows history of code movements in the 63D feature space.
        Each delta records what changed (lexical, structural, semantic)
        and by how much.

        Args:
            limit: Maximum deltas to return (default: 20).

        Returns:
            List of recent deltas with movement analysis.
        """
        with get_connection() as conn:
            cube = DeltaCodeCube(conn)
            deltas = cube.get_deltas(limit=limit)
            return {
                "deltas": deltas,
                "count": len(deltas),
            }
