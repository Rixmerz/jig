"""Visualization tools for DeltaCodeCube."""

from typing import Any

from jig.engines.dcc.db.database import get_connection


def register_visualization_tools(mcp):
    """Register visualization tools with MCP server."""

    @mcp.tool()
    def cube_generate_timeline(
        project_path: str,
        output_path: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """
        Generate an interactive timeline visualization of code changes.

        Shows:
        - Code changes (deltas) over time
        - Tension creation/resolution events
        - Git commits
        - Activity patterns

        Outputs an HTML file that can be opened in any browser.

        Args:
            project_path: Path to the project root (for git history).
            output_path: Where to save HTML file. Default: project_path/deltacodecube_timeline.html
            limit: Maximum events to include (default: 100).

        Returns:
            Result with event counts and output file path.

        Example output:
            {
                "events_count": 45,
                "by_type": {"deltas": 20, "tensions": 10, "commits": 15},
                "output_path": "/project/deltacodecube_timeline.html"
            }
        """
        from jig.engines.dcc.cube.visualizations.timeline import generate_timeline

        with get_connection() as conn:
            return generate_timeline(conn, project_path, output_path, limit)

    @mcp.tool()
    def cube_generate_matrix(
        project_path: str = ".",
        output_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Generate an interactive dependency matrix visualization.

        Shows:
        - File dependencies as a color-coded grid
        - Rows depend on columns
        - Direct vs bidirectional dependencies
        - Distance-based coloring (close vs far)

        Click cells for relationship details.

        Args:
            project_path: Path to the project root.
            output_path: Where to save HTML file. Default: project_path/deltacodecube_matrix.html

        Returns:
            Result with file/dependency counts and output path.

        Example output:
            {
                "files_count": 25,
                "dependencies_count": 42,
                "bidirectional_count": 8,
                "output_path": "/project/deltacodecube_matrix.html"
            }
        """
        from jig.engines.dcc.cube.visualizations.matrix import generate_dependency_matrix

        with get_connection() as conn:
            return generate_dependency_matrix(conn, output_path, project_path)

    @mcp.tool()
    def cube_generate_heatmap(
        project_path: str = ".",
        output_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Generate a code heatmap visualization.

        Shows files as colored cells based on:
        - Activity (changes + tensions)
        - Complexity
        - Technical debt
        - Tension count

        Toggle between metrics. Grouped by domain.

        Args:
            project_path: Path to the project root.
            output_path: Where to save HTML file. Default: project_path/deltacodecube_heatmap.html

        Returns:
            Result with file counts, hotspots, and output path.

        Example output:
            {
                "files_count": 25,
                "hotspots": 3,
                "high_debt_files": 5,
                "output_path": "/project/deltacodecube_heatmap.html"
            }
        """
        from jig.engines.dcc.cube.visualizations.heatmap import generate_heatmap

        with get_connection() as conn:
            return generate_heatmap(conn, output_path, project_path)

    @mcp.tool()
    def cube_generate_architecture(
        project_path: str = ".",
        output_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Generate an interactive architecture diagram.

        Shows:
        - Force-directed graph of modules
        - Color-coded by domain (auth, db, api, ui, util)
        - Node size based on file size and importance
        - Dependency arrows between modules
        - Hub/Authority highlighting

        Pan, zoom, and hover for details.

        Args:
            project_path: Path to the project root.
            output_path: Where to save HTML file. Default: project_path/deltacodecube_architecture.html

        Returns:
            Result with node/link counts and output path.

        Example output:
            {
                "nodes_count": 25,
                "links_count": 42,
                "domains": {"api": 8, "ui": 10, "util": 7},
                "hubs": 3,
                "authorities": 5,
                "output_path": "/project/deltacodecube_architecture.html"
            }
        """
        from jig.engines.dcc.cube.visualizations.architecture import generate_architecture

        with get_connection() as conn:
            return generate_architecture(conn, output_path, project_path)
