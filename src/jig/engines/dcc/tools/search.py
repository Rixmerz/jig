"""Advanced search tools for DeltaCodeCube."""

from typing import Any

from jig.engines.dcc.db.database import get_connection
from jig.engines.dcc.cube import DeltaCodeCube
from jig.engines.dcc.utils import convert_numpy_types


def register_search_tools(mcp):
    """Register advanced search tools with MCP server."""

    @mcp.tool()
    def cube_compare(path_a: str, path_b: str) -> dict[str, Any]:
        """
        Compare two code files in the DeltaCodeCube.

        Shows detailed comparison including:
        - Distance in each axis (lexical, structural, semantic)
        - Overall similarity score
        - Insights about what makes them similar/different

        Useful for:
        - Understanding code relationships
        - Finding refactoring opportunities
        - Comparing implementations

        Args:
            path_a: Absolute path to first file.
            path_b: Absolute path to second file.

        Returns:
            Detailed comparison with distances, similarity, and insights.
        """
        with get_connection() as conn:
            cube = DeltaCodeCube(conn)
            return convert_numpy_types(cube.compare_files(path_a, path_b))

    @mcp.tool()
    def cube_export_positions(
        format: str = "3d",
        include_features: bool = False,
    ) -> dict[str, Any]:
        """
        Export code point positions for external visualization.

        Exports all indexed files with their positions in the 63D feature space.
        Supports multiple formats for different visualization tools.

        Args:
            format: Export format:
                   - '3d': Simplified 3D coordinates (x=lexical, y=structural, z=semantic)
                   - 'json': Full JSON with optional feature vectors
                   - 'csv': CSV-ready format with headers
            include_features: Include full 63D feature vectors (only for 'json' format).

        Returns:
            Export data with positions and metadata.
        """
        with get_connection() as conn:
            cube = DeltaCodeCube(conn)
            return convert_numpy_types(cube.export_positions(format=format, include_features=include_features))

    @mcp.tool()
    def cube_find_by_criteria(
        domain: str | None = None,
        min_lines: int | None = None,
        max_lines: int | None = None,
        similar_to: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        Find files matching multiple criteria.

        Combines domain filtering, size filtering, and similarity search
        in a single query. More flexible than individual search tools.

        Args:
            domain: Filter by domain ('auth', 'db', 'api', 'ui', 'util').
            min_lines: Minimum line count filter.
            max_lines: Maximum line count filter.
            similar_to: Path to file to find similar files to.
            limit: Maximum results (default: 20).

        Returns:
            List of matching files with optional similarity scores.

        Examples:
            - Find large DB files: domain="db", min_lines=200
            - Find small API files similar to X: domain="api", max_lines=100, similar_to="/path/to/x.js"
        """
        with get_connection() as conn:
            cube = DeltaCodeCube(conn)
            results = cube.find_by_criteria(
                domain=domain,
                min_lines=min_lines,
                max_lines=max_lines,
                similar_to=similar_to,
                limit=limit,
            )
            return {
                "files": results,
                "count": len(results),
                "filters": {
                    "domain": domain,
                    "min_lines": min_lines,
                    "max_lines": max_lines,
                    "similar_to": similar_to,
                },
            }

    @mcp.tool()
    def cube_suggest_fix(
        tension_id: str | None = None,
        file_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Generate fix suggestion context for a tension or changed file.

        Provides rich context including:
        - Change type analysis (structural, lexical, semantic)
        - Severity assessment
        - Likely causes of the tension
        - Suggested actions to fix the issue
        - Relevant code snippets from affected files
        - Step-by-step fix guidance

        This tool generates context that helps Claude provide intelligent
        fix suggestions based on the specific type of change detected.

        Args:
            tension_id: ID of a specific tension to analyze.
            file_path: Path to a changed file to analyze (uses latest delta).

        Returns:
            Rich context with analysis, snippets, and fix guidance.

        Examples:
            - Analyze a tension: tension_id="abc123"
            - Analyze a changed file: file_path="/path/to/changed.js"
        """
        with get_connection() as conn:
            cube = DeltaCodeCube(conn)
            return cube.get_suggestion_context(
                tension_id=tension_id,
                file_path=file_path,
            )

    @mcp.tool()
    def cube_export_html(
        output_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Export an interactive HTML visualization of the code cube.

        Creates a self-contained HTML file with:
        - 3D scatter plot of all indexed files
        - Color-coded by semantic domain
        - Hover tooltips with file info
        - Contract/dependency lines
        - Pan, zoom, and rotate controls

        No external dependencies - all JavaScript is embedded.

        Args:
            output_path: Optional path to save the HTML file.
                        If not provided, returns HTML content.

        Returns:
            Dictionary with success status and file path or HTML content.
        """
        from jig.engines.dcc.visualization import generate_html_visualization
        from jig.engines.dcc.cube import TensionDetector

        with get_connection() as conn:
            cube = DeltaCodeCube(conn)

            # Get data for visualization
            positions = cube.export_positions(format="3d")
            code_points = positions.get("points", [])

            # Get contracts
            contracts = cube.get_contracts(limit=500)

            # Get active tensions
            tension_detector = TensionDetector(conn)
            tensions = tension_detector.get_tensions(status="detected", limit=100)
            tensions_data = [t.to_dict() for t in tensions]

            # Generate HTML
            html = generate_html_visualization(
                code_points=code_points,
                contracts=contracts,
                tensions=tensions_data,
                output_path=output_path,
            )

            if output_path:
                return {
                    "success": True,
                    "message": f"HTML visualization saved to {output_path}",
                    "path": output_path,
                    "stats": {
                        "files": len(code_points),
                        "contracts": len(contracts),
                        "tensions": len(tensions_data),
                    },
                }
            else:
                return {
                    "success": True,
                    "html_length": len(html),
                    "html": html,
                    "stats": {
                        "files": len(code_points),
                        "contracts": len(contracts),
                        "tensions": len(tensions_data),
                    },
                }

    @mcp.tool()
    def cube_get_temporal(
        path: str,
    ) -> dict[str, Any]:
        """
        Get temporal (git history) features for a file.

        Extracts metrics from git history:
        - file_age: Days since first commit (0-1)
        - change_frequency: Commits in last 90 days (0-1)
        - author_diversity: Unique authors (0-1)
        - days_since_change: Recency of changes (0-1, higher = more recent)
        - stability_score: Inverse of change frequency (0-1)

        Useful for identifying:
        - Hot spots (frequently changed files)
        - Stale code (old, unchanged files)
        - Ownership patterns

        Args:
            path: Absolute path to the file.

        Returns:
            Dictionary with temporal features and interpretation.
        """
        from jig.engines.dcc.cube.features.temporal import extract_temporal_features, get_feature_names

        features = extract_temporal_features(path)
        names = get_feature_names()

        # Build feature dictionary
        feature_dict = {name: float(features[i]) for i, name in enumerate(names)}

        # Interpretation
        interpretation = []
        if feature_dict["change_frequency"] > 0.5:
            interpretation.append("Hot spot: This file changes frequently")
        if feature_dict["days_since_change"] < 0.2:
            interpretation.append("Stale: This file hasn't been changed recently")
        if feature_dict["author_diversity"] > 0.5:
            interpretation.append("Shared ownership: Multiple authors have contributed")
        if feature_dict["stability_score"] > 0.8:
            interpretation.append("Stable: This file rarely changes")

        return {
            "path": path,
            "features": feature_dict,
            "interpretation": interpretation or ["No notable patterns detected"],
        }
