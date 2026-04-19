"""
Dependency Matrix Visualization for DeltaCodeCube.

Generates an interactive HTML matrix showing:
- File dependencies as a grid
- Color-coded by distance/coupling
- Click to see relationship details
- Sortable by various metrics
"""

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from jig.engines.dcc.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class MatrixCell:
    """A cell in the dependency matrix."""
    row_file: str
    col_file: str
    has_dependency: bool
    distance: float
    is_bidirectional: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "row": Path(self.row_file).name,
            "col": Path(self.col_file).name,
            "row_path": self.row_file,
            "col_path": self.col_file,
            "has_dep": self.has_dependency,
            "distance": round(self.distance, 4) if self.distance else 0,
            "bidirectional": self.is_bidirectional,
        }


class DependencyMatrixGenerator:
    """Generates dependency matrix visualization."""

    def __init__(self, conn: sqlite3.Connection):
        """Initialize with database connection."""
        self.conn = conn

    def _normalize_vectors(self, v1: np.ndarray, v2: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Normalize two vectors to the same dimension by padding the shorter one."""
        if len(v1) == len(v2):
            return v1, v2
        max_len = max(len(v1), len(v2))
        if len(v1) < max_len:
            v1 = np.pad(v1, (0, max_len - len(v1)), mode='constant', constant_values=0)
        if len(v2) < max_len:
            v2 = np.pad(v2, (0, max_len - len(v2)), mode='constant', constant_values=0)
        return v1, v2

    def build_matrix(self) -> tuple[list[str], list[list[MatrixCell]]]:
        """
        Build the dependency matrix.

        Returns:
            Tuple of (file_paths, matrix_cells).
        """
        # Get all files
        cursor = self.conn.execute("""
            SELECT file_path, lexical_features, structural_features, semantic_features
            FROM code_points
            ORDER BY file_path
        """)
        files = cursor.fetchall()

        if not files:
            return [], []

        file_paths = [f["file_path"] for f in files]
        file_features = {}

        for f in files:
            file_features[f["file_path"]] = np.concatenate([
                np.array(json.loads(f["lexical_features"])),
                np.array(json.loads(f["structural_features"])),
                np.array(json.loads(f["semantic_features"])),
            ])

        # Get dependencies
        cursor = self.conn.execute("""
            SELECT cp1.file_path as caller, cp2.file_path as callee, c.baseline_distance
            FROM contracts c
            JOIN code_points cp1 ON c.caller_id = cp1.id
            JOIN code_points cp2 ON c.callee_id = cp2.id
        """)

        dependencies = {}
        for row in cursor.fetchall():
            key = (row["caller"], row["callee"])
            dependencies[key] = row["baseline_distance"]

        # Build matrix
        matrix = []
        for row_path in file_paths:
            row_cells = []
            for col_path in file_paths:
                if row_path == col_path:
                    # Diagonal
                    cell = MatrixCell(
                        row_file=row_path,
                        col_file=col_path,
                        has_dependency=False,
                        distance=0,
                        is_bidirectional=False,
                    )
                else:
                    has_dep = (row_path, col_path) in dependencies
                    reverse_dep = (col_path, row_path) in dependencies
                    distance = dependencies.get((row_path, col_path), 0)

                    if not has_dep and not reverse_dep:
                        # Calculate cosine distance anyway
                        if row_path in file_features and col_path in file_features:
                            v1 = file_features[row_path]
                            v2 = file_features[col_path]
                            # Normalize vectors to same dimension
                            v1, v2 = self._normalize_vectors(v1, v2)
                            norm1, norm2 = np.linalg.norm(v1), np.linalg.norm(v2)
                            if norm1 > 0 and norm2 > 0:
                                distance = 1 - np.dot(v1, v2) / (norm1 * norm2)
                            else:
                                distance = 1.0

                    cell = MatrixCell(
                        row_file=row_path,
                        col_file=col_path,
                        has_dependency=has_dep,
                        distance=distance,
                        is_bidirectional=has_dep and reverse_dep,
                    )

                row_cells.append(cell)
            matrix.append(row_cells)

        return file_paths, matrix

    def generate_html(self, file_paths: list[str], matrix: list[list[MatrixCell]]) -> str:
        """
        Generate HTML visualization for dependency matrix.

        Args:
            file_paths: List of file paths.
            matrix: 2D list of MatrixCell objects.

        Returns:
            Complete HTML page as string.
        """
        # Convert to JSON-serializable format
        files_json = json.dumps([Path(p).name for p in file_paths])
        paths_json = json.dumps(file_paths)

        matrix_data = []
        for row in matrix:
            matrix_data.append([cell.to_dict() for cell in row])
        matrix_json = json.dumps(matrix_data)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DeltaCodeCube Dependency Matrix</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #e4e4e7;
            min-height: 100vh;
            padding: 2rem;
        }}
        h1 {{
            text-align: center;
            margin-bottom: 1rem;
            color: #a78bfa;
        }}
        .info {{
            text-align: center;
            margin-bottom: 2rem;
            color: #71717a;
            font-size: 0.9rem;
        }}
        .matrix-container {{
            overflow: auto;
            max-width: 100%;
            margin: 0 auto;
        }}
        .matrix {{
            border-collapse: collapse;
            margin: 0 auto;
        }}
        .matrix th {{
            padding: 0.5rem;
            font-size: 0.7rem;
            font-weight: 500;
            color: #a1a1aa;
            max-width: 80px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        .matrix th.row-header {{
            text-align: right;
            padding-right: 0.8rem;
        }}
        .matrix th.col-header {{
            writing-mode: vertical-rl;
            text-orientation: mixed;
            height: 100px;
            text-align: left;
            padding-bottom: 0.8rem;
        }}
        .matrix td {{
            width: 20px;
            height: 20px;
            border: 1px solid rgba(30, 30, 46, 0.8);
            cursor: pointer;
            transition: transform 0.1s;
        }}
        .matrix td:hover {{
            transform: scale(1.5);
            z-index: 10;
            position: relative;
        }}
        .cell-none {{ background: rgba(30, 30, 46, 0.3); }}
        .cell-self {{ background: #3f3f46; }}
        .cell-dep {{ background: #3b82f6; }}
        .cell-bidep {{ background: #8b5cf6; }}
        .cell-close {{ background: #22c55e; }}
        .cell-far {{ background: #f59e0b; }}
        .cell-very-far {{ background: #ef4444; }}
        .legend {{
            display: flex;
            justify-content: center;
            gap: 1.5rem;
            margin-top: 2rem;
            flex-wrap: wrap;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.8rem;
            color: #a1a1aa;
        }}
        .legend-color {{
            width: 16px;
            height: 16px;
            border-radius: 3px;
        }}
        .tooltip {{
            position: fixed;
            background: rgba(30, 30, 46, 0.95);
            border: 1px solid rgba(167, 139, 250, 0.3);
            border-radius: 8px;
            padding: 1rem;
            font-size: 0.85rem;
            pointer-events: none;
            z-index: 1000;
            display: none;
            max-width: 300px;
        }}
        .tooltip h4 {{
            color: #a78bfa;
            margin-bottom: 0.5rem;
        }}
        .tooltip p {{
            color: #a1a1aa;
            margin: 0.25rem 0;
        }}
        .stats {{
            display: flex;
            justify-content: center;
            gap: 2rem;
            margin-bottom: 2rem;
            flex-wrap: wrap;
        }}
        .stat {{
            text-align: center;
            padding: 1rem;
            background: rgba(30, 30, 46, 0.6);
            border-radius: 8px;
            min-width: 100px;
        }}
        .stat-value {{
            font-size: 1.5rem;
            font-weight: bold;
            color: #a78bfa;
        }}
        .stat-label {{
            font-size: 0.8rem;
            color: #71717a;
        }}
    </style>
</head>
<body>
    <h1>🔗 Dependency Matrix</h1>
    <p class="info">Rows depend on Columns | Click cells for details</p>

    <div class="stats" id="stats"></div>

    <div class="matrix-container">
        <table class="matrix" id="matrix"></table>
    </div>

    <div class="legend">
        <div class="legend-item"><div class="legend-color cell-dep"></div> Direct dependency</div>
        <div class="legend-item"><div class="legend-color cell-bidep"></div> Bidirectional</div>
        <div class="legend-item"><div class="legend-color cell-close"></div> Close (< 0.3)</div>
        <div class="legend-item"><div class="legend-color cell-far"></div> Far (0.3-0.6)</div>
        <div class="legend-item"><div class="legend-color cell-very-far"></div> Very far (> 0.6)</div>
    </div>

    <div class="tooltip" id="tooltip"></div>

    <script>
        const files = {files_json};
        const paths = {paths_json};
        const matrix = {matrix_json};

        function getCellClass(cell) {{
            if (cell.row === cell.col) return 'cell-self';
            if (cell.bidirectional) return 'cell-bidep';
            if (cell.has_dep) return 'cell-dep';
            if (cell.distance < 0.3) return 'cell-close';
            if (cell.distance < 0.6) return 'cell-far';
            if (cell.distance > 0) return 'cell-very-far';
            return 'cell-none';
        }}

        function renderStats() {{
            let deps = 0, bideps = 0;
            matrix.forEach(row => row.forEach(cell => {{
                if (cell.has_dep) deps++;
                if (cell.bidirectional) bideps++;
            }}));

            document.getElementById('stats').innerHTML = `
                <div class="stat"><div class="stat-value">${{files.length}}</div><div class="stat-label">Files</div></div>
                <div class="stat"><div class="stat-value">${{deps}}</div><div class="stat-label">Dependencies</div></div>
                <div class="stat"><div class="stat-value">${{Math.floor(bideps/2)}}</div><div class="stat-label">Bidirectional</div></div>
            `;
        }}

        function renderMatrix() {{
            let html = '<tr><th></th>';

            // Header row
            files.forEach(f => {{
                html += `<th class="col-header" title="${{f}}">${{f}}</th>`;
            }});
            html += '</tr>';

            // Data rows
            matrix.forEach((row, i) => {{
                html += `<tr><th class="row-header" title="${{paths[i]}}">${{files[i]}}</th>`;
                row.forEach(cell => {{
                    html += `<td class="${{getCellClass(cell)}}" data-row="${{cell.row}}" data-col="${{cell.col}}" data-dep="${{cell.has_dep}}" data-dist="${{cell.distance}}" data-bidi="${{cell.bidirectional}}"></td>`;
                }});
                html += '</tr>';
            }});

            document.getElementById('matrix').innerHTML = html;
        }}

        // Tooltip
        const tooltip = document.getElementById('tooltip');

        document.getElementById('matrix').addEventListener('mousemove', (e) => {{
            if (e.target.tagName === 'TD') {{
                const row = e.target.dataset.row;
                const col = e.target.dataset.col;
                const hasDep = e.target.dataset.dep === 'true';
                const dist = parseFloat(e.target.dataset.dist) || 0;
                const bidi = e.target.dataset.bidi === 'true';

                let relationship = 'No direct dependency';
                if (row === col) relationship = 'Same file';
                else if (bidi) relationship = 'Bidirectional dependency';
                else if (hasDep) relationship = 'Direct dependency';

                tooltip.innerHTML = `
                    <h4>${{row}} → ${{col}}</h4>
                    <p>Relationship: ${{relationship}}</p>
                    <p>Distance: ${{dist.toFixed(4)}}</p>
                `;
                tooltip.style.display = 'block';
                tooltip.style.left = (e.clientX + 15) + 'px';
                tooltip.style.top = (e.clientY + 15) + 'px';
            }}
        }});

        document.getElementById('matrix').addEventListener('mouseleave', () => {{
            tooltip.style.display = 'none';
        }});

        // Initial render
        renderStats();
        renderMatrix();
    </script>
</body>
</html>"""

        return html


def generate_dependency_matrix(
    conn: sqlite3.Connection,
    output_path: str | None = None,
    project_path: str = ".",
) -> dict[str, Any]:
    """
    Generate dependency matrix visualization.

    Args:
        conn: Database connection.
        output_path: Where to save the HTML file.
        project_path: Path to the project root.

    Returns:
        Result with file count and output path.
    """
    generator = DependencyMatrixGenerator(conn)
    file_paths, matrix = generator.build_matrix()

    if not output_path:
        output_path = str(Path(project_path) / "deltacodecube_matrix.html")

    if not file_paths:
        return {
            "error": "No files indexed",
            "files_count": 0,
        }

    # Count dependencies
    dep_count = sum(1 for row in matrix for cell in row if cell.has_dependency)
    bidi_count = sum(1 for row in matrix for cell in row if cell.is_bidirectional) // 2

    html = generator.generate_html(file_paths, matrix)
    Path(output_path).write_text(html, encoding="utf-8")

    return {
        "files_count": len(file_paths),
        "dependencies_count": dep_count,
        "bidirectional_count": bidi_count,
        "output_path": output_path,
    }
