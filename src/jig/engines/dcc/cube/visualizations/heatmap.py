"""
Heat Map Visualization for DeltaCodeCube.

Generates an interactive HTML heatmap showing:
- File activity levels (changes, tensions)
- Hotspots (files with most activity)
- Technical debt heat
- Complexity distribution

Multiple heatmap views for different metrics.
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
class HeatmapCell:
    """A cell in the heatmap."""
    file_path: str
    file_name: str
    activity_score: float  # 0-1 normalized
    change_count: int
    tension_count: int
    complexity_score: float
    debt_score: float
    domain: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.file_path,
            "name": self.file_name,
            "activity": round(self.activity_score, 4),
            "changes": self.change_count,
            "tensions": self.tension_count,
            "complexity": round(self.complexity_score, 4),
            "debt": round(self.debt_score, 4),
            "domain": self.domain,
        }


class HeatmapGenerator:
    """Generates heatmap visualization."""

    DOMAINS = ["auth", "db", "api", "ui", "util"]

    def __init__(self, conn: sqlite3.Connection):
        """Initialize with database connection."""
        self.conn = conn

    def collect_data(self) -> list[HeatmapCell]:
        """
        Collect heatmap data for all files.

        Returns:
            List of HeatmapCell objects.
        """
        cells = []

        # Get file data with features
        cursor = self.conn.execute("""
            SELECT id, file_path, line_count,
                   lexical_features, structural_features, semantic_features
            FROM code_points
        """)

        files = cursor.fetchall()

        # Count deltas per file
        delta_counts = {}
        try:
            cursor = self.conn.execute("""
                SELECT code_point_id, COUNT(*) as count
                FROM deltas
                GROUP BY code_point_id
            """)
            for row in cursor.fetchall():
                delta_counts[row["code_point_id"]] = row["count"]
        except Exception:
            pass

        # Count tensions per file
        tension_counts = {}
        try:
            cursor = self.conn.execute("""
                SELECT cp.id, COUNT(*) as count
                FROM tensions t
                JOIN contracts c ON t.contract_id = c.id
                JOIN code_points cp ON c.callee_id = cp.id
                WHERE t.status = 'detected'
                GROUP BY cp.id
            """)
            for row in cursor.fetchall():
                tension_counts[row["id"]] = row["count"]
        except Exception:
            pass

        # Process each file
        max_changes = max(delta_counts.values()) if delta_counts else 1
        max_tensions = max(tension_counts.values()) if tension_counts else 1

        for f in files:
            file_id = f["id"]
            file_path = f["file_path"]

            # Parse features
            structural = json.loads(f["structural_features"])
            semantic = json.loads(f["semantic_features"])

            # Determine domain
            domain_scores = semantic[:len(self.DOMAINS)]
            domain_idx = int(np.argmax(domain_scores))
            domain = self.DOMAINS[domain_idx] if domain_idx < len(self.DOMAINS) else "util"

            # Get counts
            change_count = delta_counts.get(file_id, 0)
            tension_count = tension_counts.get(file_id, 0)

            # Calculate complexity (from structural features)
            cyclomatic = structural[6] if len(structural) > 6 else 0
            halstead = structural[10] if len(structural) > 10 else 0
            complexity_score = (cyclomatic + halstead) / 2

            # Calculate simple debt proxy
            coupling = structural[15] if len(structural) > 15 else 0
            size_norm = min(f["line_count"] / 500, 1.0)
            debt_score = (complexity_score + coupling + size_norm) / 3

            # Activity score (normalized)
            activity_score = (
                (change_count / max_changes) * 0.5 +
                (tension_count / max_tensions) * 0.5
            ) if max_changes > 0 and max_tensions > 0 else 0

            cells.append(HeatmapCell(
                file_path=file_path,
                file_name=Path(file_path).name,
                activity_score=activity_score,
                change_count=change_count,
                tension_count=tension_count,
                complexity_score=complexity_score,
                debt_score=debt_score,
                domain=domain,
            ))

        # Sort by activity
        cells.sort(key=lambda c: c.activity_score, reverse=True)

        return cells

    def generate_html(self, cells: list[HeatmapCell]) -> str:
        """
        Generate HTML visualization for heatmap.

        Args:
            cells: List of HeatmapCell objects.

        Returns:
            Complete HTML page as string.
        """
        cells_json = json.dumps([c.to_dict() for c in cells])

        # Group by domain
        by_domain = {}
        for cell in cells:
            if cell.domain not in by_domain:
                by_domain[cell.domain] = []
            by_domain[cell.domain].append(cell.to_dict())
        domains_json = json.dumps(by_domain)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DeltaCodeCube Heat Map</title>
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
            margin-bottom: 0.5rem;
            color: #a78bfa;
        }}
        .subtitle {{
            text-align: center;
            color: #71717a;
            margin-bottom: 2rem;
        }}
        .controls {{
            display: flex;
            justify-content: center;
            gap: 1rem;
            margin-bottom: 2rem;
            flex-wrap: wrap;
        }}
        .metric-btn {{
            padding: 0.5rem 1rem;
            border: 1px solid rgba(167, 139, 250, 0.3);
            background: transparent;
            color: #a78bfa;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .metric-btn:hover, .metric-btn.active {{
            background: rgba(167, 139, 250, 0.2);
            border-color: #a78bfa;
        }}
        .heatmap-container {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            justify-content: center;
            max-width: 1200px;
            margin: 0 auto;
        }}
        .heat-cell {{
            width: 40px;
            height: 40px;
            border-radius: 6px;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.6rem;
            font-weight: bold;
            color: rgba(0,0,0,0.5);
        }}
        .heat-cell:hover {{
            transform: scale(1.3);
            z-index: 10;
            box-shadow: 0 4px 20px rgba(0,0,0,0.5);
        }}
        .domain-section {{
            margin-bottom: 2rem;
        }}
        .domain-title {{
            font-size: 1rem;
            color: #a78bfa;
            margin-bottom: 0.5rem;
            padding-left: 0.5rem;
            border-left: 3px solid #a78bfa;
        }}
        .domain-grid {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.4rem;
        }}
        .legend {{
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 0.5rem;
            margin: 2rem 0;
        }}
        .legend-gradient {{
            width: 200px;
            height: 20px;
            background: linear-gradient(to right, #22c55e, #eab308, #f97316, #ef4444, #991b1b);
            border-radius: 4px;
        }}
        .legend-label {{
            font-size: 0.8rem;
            color: #71717a;
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
        .hotspot {{
            color: #ef4444;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <h1>🔥 Code Heat Map</h1>
    <p class="subtitle">Visualize code hotspots and activity patterns</p>

    <div class="stats" id="stats"></div>

    <div class="controls">
        <button class="metric-btn active" data-metric="activity">Activity</button>
        <button class="metric-btn" data-metric="complexity">Complexity</button>
        <button class="metric-btn" data-metric="debt">Tech Debt</button>
        <button class="metric-btn" data-metric="tensions">Tensions</button>
    </div>

    <div class="legend">
        <span class="legend-label">Low</span>
        <div class="legend-gradient"></div>
        <span class="legend-label">High</span>
    </div>

    <div id="heatmap"></div>

    <div class="tooltip" id="tooltip"></div>

    <script>
        const cells = {cells_json};
        const byDomain = {domains_json};
        let currentMetric = 'activity';

        function getColor(value) {{
            // Green -> Yellow -> Orange -> Red -> Dark Red
            const colors = [
                [34, 197, 94],    // green
                [234, 179, 8],    // yellow
                [249, 115, 22],   // orange
                [239, 68, 68],    // red
                [153, 27, 27],    // dark red
            ];

            const idx = Math.min(Math.floor(value * (colors.length - 1)), colors.length - 2);
            const t = (value * (colors.length - 1)) - idx;

            const r = Math.round(colors[idx][0] + t * (colors[idx + 1][0] - colors[idx][0]));
            const g = Math.round(colors[idx][1] + t * (colors[idx + 1][1] - colors[idx][1]));
            const b = Math.round(colors[idx][2] + t * (colors[idx + 1][2] - colors[idx][2]));

            return `rgb(${{r}},${{g}},${{b}})`;
        }}

        function getValue(cell, metric) {{
            switch (metric) {{
                case 'activity': return cell.activity;
                case 'complexity': return cell.complexity;
                case 'debt': return cell.debt;
                case 'tensions': return Math.min(cell.tensions / 5, 1);
                default: return cell.activity;
            }}
        }}

        function renderStats() {{
            const hotspots = cells.filter(c => c.activity > 0.7).length;
            const highDebt = cells.filter(c => c.debt > 0.6).length;
            const tensioned = cells.filter(c => c.tensions > 0).length;

            document.getElementById('stats').innerHTML = `
                <div class="stat"><div class="stat-value">${{cells.length}}</div><div class="stat-label">Files</div></div>
                <div class="stat"><div class="stat-value hotspot">${{hotspots}}</div><div class="stat-label">Hotspots</div></div>
                <div class="stat"><div class="stat-value">${{highDebt}}</div><div class="stat-label">High Debt</div></div>
                <div class="stat"><div class="stat-value">${{tensioned}}</div><div class="stat-label">With Tensions</div></div>
            `;
        }}

        function renderHeatmap() {{
            let html = '';

            Object.keys(byDomain).sort().forEach(domain => {{
                const domainCells = byDomain[domain];
                if (domainCells.length === 0) return;

                html += `<div class="domain-section">`;
                html += `<div class="domain-title">${{domain.toUpperCase()}} (${{domainCells.length}} files)</div>`;
                html += `<div class="domain-grid">`;

                domainCells.forEach(cell => {{
                    const value = getValue(cell, currentMetric);
                    const color = getColor(value);
                    html += `<div class="heat-cell" style="background:${{color}}"
                                 data-name="${{cell.name}}"
                                 data-path="${{cell.path}}"
                                 data-activity="${{cell.activity}}"
                                 data-complexity="${{cell.complexity}}"
                                 data-debt="${{cell.debt}}"
                                 data-changes="${{cell.changes}}"
                                 data-tensions="${{cell.tensions}}"
                                 data-domain="${{cell.domain}}"
                                 title="${{cell.name}}"></div>`;
                }});

                html += `</div></div>`;
            }});

            document.getElementById('heatmap').innerHTML = html || '<p style="text-align:center;color:#71717a;">No files to display</p>';
        }}

        // Metric buttons
        document.querySelectorAll('.metric-btn').forEach(btn => {{
            btn.addEventListener('click', () => {{
                document.querySelectorAll('.metric-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                currentMetric = btn.dataset.metric;
                renderHeatmap();
            }});
        }});

        // Tooltip
        const tooltip = document.getElementById('tooltip');

        document.getElementById('heatmap').addEventListener('mousemove', (e) => {{
            if (e.target.classList.contains('heat-cell')) {{
                const d = e.target.dataset;
                tooltip.innerHTML = `
                    <h4>${{d.name}}</h4>
                    <p>Domain: ${{d.domain}}</p>
                    <p>Activity: ${{(parseFloat(d.activity) * 100).toFixed(1)}}%</p>
                    <p>Complexity: ${{(parseFloat(d.complexity) * 100).toFixed(1)}}%</p>
                    <p>Tech Debt: ${{(parseFloat(d.debt) * 100).toFixed(1)}}%</p>
                    <p>Changes: ${{d.changes}} | Tensions: ${{d.tensions}}</p>
                `;
                tooltip.style.display = 'block';
                tooltip.style.left = (e.clientX + 15) + 'px';
                tooltip.style.top = (e.clientY + 15) + 'px';
            }}
        }});

        document.getElementById('heatmap').addEventListener('mouseleave', () => {{
            tooltip.style.display = 'none';
        }});

        // Initial render
        renderStats();
        renderHeatmap();
    </script>
</body>
</html>"""

        return html


def generate_heatmap(
    conn: sqlite3.Connection,
    output_path: str | None = None,
    project_path: str = ".",
) -> dict[str, Any]:
    """
    Generate heatmap visualization.

    Args:
        conn: Database connection.
        output_path: Where to save the HTML file.
        project_path: Path to the project root.

    Returns:
        Result with file count and output path.
    """
    generator = HeatmapGenerator(conn)
    cells = generator.collect_data()

    if not output_path:
        output_path = str(Path(project_path) / "deltacodecube_heatmap.html")

    if not cells:
        return {
            "error": "No files indexed",
            "files_count": 0,
        }

    # Calculate stats
    hotspots = len([c for c in cells if c.activity_score > 0.7])
    high_debt = len([c for c in cells if c.debt_score > 0.6])

    html = generator.generate_html(cells)
    Path(output_path).write_text(html, encoding="utf-8")

    return {
        "files_count": len(cells),
        "hotspots": hotspots,
        "high_debt_files": high_debt,
        "output_path": output_path,
    }
