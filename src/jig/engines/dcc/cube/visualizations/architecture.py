"""
Architecture Diagram Visualization for DeltaCodeCube.

Generates an interactive HTML architecture diagram showing:
- Module relationships as a force-directed graph
- Domain clusters with color coding
- Dependency flow visualization
- Hub/Authority highlighting from HITS algorithm
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
class ArchNode:
    """A node in the architecture diagram."""
    id: str
    file_path: str
    file_name: str
    domain: str
    line_count: int
    importance: float  # 0-1 based on centrality
    hub_score: float
    authority_score: float
    in_degree: int
    out_degree: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "path": self.file_path,
            "name": self.file_name,
            "domain": self.domain,
            "lines": self.line_count,
            "importance": round(self.importance, 4),
            "hub": round(self.hub_score, 4),
            "authority": round(self.authority_score, 4),
            "in_deg": self.in_degree,
            "out_deg": self.out_degree,
        }


@dataclass
class ArchLink:
    """A link in the architecture diagram."""
    source: str
    target: str
    distance: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "distance": round(self.distance, 4),
        }


class ArchitectureGenerator:
    """Generates architecture diagram visualization."""

    DOMAINS = ["auth", "db", "api", "ui", "util"]
    DOMAIN_COLORS = {
        "auth": "#ef4444",
        "db": "#3b82f6",
        "api": "#22c55e",
        "ui": "#a78bfa",
        "util": "#71717a",
    }

    def __init__(self, conn: sqlite3.Connection):
        """Initialize with database connection."""
        self.conn = conn

    def build_graph(self) -> tuple[list[ArchNode], list[ArchLink]]:
        """
        Build the architecture graph.

        Returns:
            Tuple of (nodes, links).
        """
        nodes = []
        links = []

        # Get all files with features
        cursor = self.conn.execute("""
            SELECT id, file_path, line_count, semantic_features
            FROM code_points
        """)
        files = {row["id"]: row for row in cursor.fetchall()}

        if not files:
            return [], []

        # Get dependencies
        cursor = self.conn.execute("""
            SELECT c.caller_id, c.callee_id, c.baseline_distance
            FROM contracts c
        """)
        deps = cursor.fetchall()

        # Calculate degrees
        in_degrees = {}
        out_degrees = {}
        for dep in deps:
            caller = dep["caller_id"]
            callee = dep["callee_id"]
            out_degrees[caller] = out_degrees.get(caller, 0) + 1
            in_degrees[callee] = in_degrees.get(callee, 0) + 1

        # Calculate simple hub/authority scores
        hub_scores = {}
        auth_scores = {}
        max_out = max(out_degrees.values()) if out_degrees else 1
        max_in = max(in_degrees.values()) if in_degrees else 1

        for file_id in files:
            hub_scores[file_id] = out_degrees.get(file_id, 0) / max_out
            auth_scores[file_id] = in_degrees.get(file_id, 0) / max_in

        # Create nodes
        for file_id, f in files.items():
            semantic = json.loads(f["semantic_features"])
            domain_scores = semantic[:len(self.DOMAINS)]
            domain_idx = int(np.argmax(domain_scores))
            domain = self.DOMAINS[domain_idx] if domain_idx < len(self.DOMAINS) else "util"

            # Importance = combination of hub + authority
            importance = (hub_scores.get(file_id, 0) + auth_scores.get(file_id, 0)) / 2

            nodes.append(ArchNode(
                id=str(file_id),
                file_path=f["file_path"],
                file_name=Path(f["file_path"]).name,
                domain=domain,
                line_count=f["line_count"],
                importance=importance,
                hub_score=hub_scores.get(file_id, 0),
                authority_score=auth_scores.get(file_id, 0),
                in_degree=in_degrees.get(file_id, 0),
                out_degree=out_degrees.get(file_id, 0),
            ))

        # Create links
        for dep in deps:
            links.append(ArchLink(
                source=str(dep["caller_id"]),
                target=str(dep["callee_id"]),
                distance=dep["baseline_distance"],
            ))

        return nodes, links

    def generate_html(self, nodes: list[ArchNode], links: list[ArchLink]) -> str:
        """
        Generate HTML visualization for architecture diagram.

        Uses a simple force-directed layout implemented in JavaScript.

        Args:
            nodes: List of ArchNode objects.
            links: List of ArchLink objects.

        Returns:
            Complete HTML page as string.
        """
        nodes_json = json.dumps([n.to_dict() for n in nodes])
        links_json = json.dumps([l.to_dict() for l in links])
        colors_json = json.dumps(self.DOMAIN_COLORS)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DeltaCodeCube Architecture</title>
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
            overflow: hidden;
        }}
        h1 {{
            position: absolute;
            top: 1rem;
            left: 50%;
            transform: translateX(-50%);
            color: #a78bfa;
            z-index: 100;
            text-shadow: 0 2px 10px rgba(0,0,0,0.5);
        }}
        #canvas {{
            width: 100vw;
            height: 100vh;
            cursor: grab;
        }}
        #canvas:active {{
            cursor: grabbing;
        }}
        .controls {{
            position: absolute;
            top: 4rem;
            left: 1rem;
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
            z-index: 100;
        }}
        .control-btn {{
            padding: 0.5rem 1rem;
            border: 1px solid rgba(167, 139, 250, 0.3);
            background: rgba(30, 30, 46, 0.8);
            color: #a78bfa;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .control-btn:hover {{
            background: rgba(167, 139, 250, 0.2);
        }}
        .legend {{
            position: absolute;
            bottom: 1rem;
            left: 1rem;
            background: rgba(30, 30, 46, 0.9);
            border: 1px solid rgba(167, 139, 250, 0.3);
            border-radius: 8px;
            padding: 1rem;
            z-index: 100;
        }}
        .legend-title {{
            font-size: 0.9rem;
            color: #a78bfa;
            margin-bottom: 0.5rem;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.8rem;
            color: #a1a1aa;
            margin: 0.3rem 0;
        }}
        .legend-color {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }}
        .stats {{
            position: absolute;
            top: 4rem;
            right: 1rem;
            background: rgba(30, 30, 46, 0.9);
            border: 1px solid rgba(167, 139, 250, 0.3);
            border-radius: 8px;
            padding: 1rem;
            z-index: 100;
        }}
        .stat {{
            font-size: 0.85rem;
            color: #a1a1aa;
            margin: 0.3rem 0;
        }}
        .stat-value {{
            color: #a78bfa;
            font-weight: bold;
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
    </style>
</head>
<body>
    <h1>🏗️ Architecture Diagram</h1>

    <div class="controls">
        <button class="control-btn" id="resetBtn">Reset View</button>
        <button class="control-btn" id="toggleLabels">Toggle Labels</button>
    </div>

    <div class="legend">
        <div class="legend-title">Domains</div>
        <div class="legend-item"><div class="legend-color" style="background:#ef4444"></div> Auth</div>
        <div class="legend-item"><div class="legend-color" style="background:#3b82f6"></div> Database</div>
        <div class="legend-item"><div class="legend-color" style="background:#22c55e"></div> API</div>
        <div class="legend-item"><div class="legend-color" style="background:#a78bfa"></div> UI</div>
        <div class="legend-item"><div class="legend-color" style="background:#71717a"></div> Utility</div>
    </div>

    <div class="stats" id="stats"></div>

    <canvas id="canvas"></canvas>
    <div class="tooltip" id="tooltip"></div>

    <script>
        const nodesData = {nodes_json};
        const linksData = {links_json};
        const domainColors = {colors_json};

        const canvas = document.getElementById('canvas');
        const ctx = canvas.getContext('2d');
        const tooltip = document.getElementById('tooltip');

        let width, height;
        let nodes = [];
        let links = [];
        let showLabels = true;

        // Camera state
        let offsetX = 0, offsetY = 0;
        let scale = 1;
        let isDragging = false;
        let dragStart = {{x: 0, y: 0}};

        function resize() {{
            width = canvas.width = window.innerWidth;
            height = canvas.height = window.innerHeight;
        }}

        function init() {{
            resize();

            // Initialize node positions with force-directed placement
            nodes = nodesData.map((n, i) => ({{
                ...n,
                x: width / 2 + (Math.random() - 0.5) * 400,
                y: height / 2 + (Math.random() - 0.5) * 400,
                vx: 0,
                vy: 0,
                radius: Math.max(10, Math.sqrt(n.lines) * 0.5 + n.importance * 20),
            }}));

            links = linksData.map(l => ({{
                ...l,
                sourceNode: nodes.find(n => n.id === l.source),
                targetNode: nodes.find(n => n.id === l.target),
            }})).filter(l => l.sourceNode && l.targetNode);

            // Render stats
            document.getElementById('stats').innerHTML = `
                <div class="stat">Modules: <span class="stat-value">${{nodes.length}}</span></div>
                <div class="stat">Dependencies: <span class="stat-value">${{links.length}}</span></div>
                <div class="stat">Hubs: <span class="stat-value">${{nodes.filter(n => n.hub > 0.5).length}}</span></div>
                <div class="stat">Authorities: <span class="stat-value">${{nodes.filter(n => n.authority > 0.5).length}}</span></div>
            `;

            simulate();
        }}

        function simulate() {{
            // Simple force-directed simulation
            const iterations = 100;

            for (let iter = 0; iter < iterations; iter++) {{
                // Repulsion between all nodes
                for (let i = 0; i < nodes.length; i++) {{
                    for (let j = i + 1; j < nodes.length; j++) {{
                        const dx = nodes[j].x - nodes[i].x;
                        const dy = nodes[j].y - nodes[i].y;
                        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
                        const force = 5000 / (dist * dist);

                        const fx = (dx / dist) * force;
                        const fy = (dy / dist) * force;

                        nodes[i].vx -= fx;
                        nodes[i].vy -= fy;
                        nodes[j].vx += fx;
                        nodes[j].vy += fy;
                    }}
                }}

                // Attraction along links
                for (const link of links) {{
                    const dx = link.targetNode.x - link.sourceNode.x;
                    const dy = link.targetNode.y - link.sourceNode.y;
                    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
                    const force = (dist - 100) * 0.05;

                    const fx = (dx / dist) * force;
                    const fy = (dy / dist) * force;

                    link.sourceNode.vx += fx;
                    link.sourceNode.vy += fy;
                    link.targetNode.vx -= fx;
                    link.targetNode.vy -= fy;
                }}

                // Center gravity
                for (const node of nodes) {{
                    node.vx += (width / 2 - node.x) * 0.001;
                    node.vy += (height / 2 - node.y) * 0.001;
                }}

                // Apply velocities with damping
                for (const node of nodes) {{
                    node.x += node.vx * 0.5;
                    node.y += node.vy * 0.5;
                    node.vx *= 0.8;
                    node.vy *= 0.8;
                }}
            }}

            draw();
        }}

        function draw() {{
            ctx.clearRect(0, 0, width, height);

            ctx.save();
            ctx.translate(offsetX, offsetY);
            ctx.scale(scale, scale);

            // Draw links
            ctx.lineWidth = 1 / scale;
            for (const link of links) {{
                const opacity = Math.max(0.1, 1 - link.distance);
                ctx.strokeStyle = `rgba(167, 139, 250, ${{opacity * 0.5}})`;
                ctx.beginPath();
                ctx.moveTo(link.sourceNode.x, link.sourceNode.y);
                ctx.lineTo(link.targetNode.x, link.targetNode.y);
                ctx.stroke();

                // Arrow head
                const angle = Math.atan2(
                    link.targetNode.y - link.sourceNode.y,
                    link.targetNode.x - link.sourceNode.x
                );
                const arrowX = link.targetNode.x - Math.cos(angle) * link.targetNode.radius;
                const arrowY = link.targetNode.y - Math.sin(angle) * link.targetNode.radius;

                ctx.fillStyle = `rgba(167, 139, 250, ${{opacity * 0.5}})`;
                ctx.beginPath();
                ctx.moveTo(arrowX, arrowY);
                ctx.lineTo(
                    arrowX - 8 * Math.cos(angle - 0.3),
                    arrowY - 8 * Math.sin(angle - 0.3)
                );
                ctx.lineTo(
                    arrowX - 8 * Math.cos(angle + 0.3),
                    arrowY - 8 * Math.sin(angle + 0.3)
                );
                ctx.closePath();
                ctx.fill();
            }}

            // Draw nodes
            for (const node of nodes) {{
                const color = domainColors[node.domain] || '#71717a';

                // Glow for important nodes
                if (node.importance > 0.5) {{
                    ctx.shadowColor = color;
                    ctx.shadowBlur = 20;
                }}

                ctx.fillStyle = color;
                ctx.beginPath();
                ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
                ctx.fill();

                ctx.shadowBlur = 0;

                // Label
                if (showLabels && scale > 0.5) {{
                    ctx.fillStyle = '#e4e4e7';
                    ctx.font = `${{10 / scale}}px sans-serif`;
                    ctx.textAlign = 'center';
                    ctx.fillText(node.name, node.x, node.y + node.radius + 12 / scale);
                }}
            }}

            ctx.restore();

            requestAnimationFrame(draw);
        }}

        // Mouse interactions
        canvas.addEventListener('mousedown', (e) => {{
            isDragging = true;
            dragStart = {{x: e.clientX - offsetX, y: e.clientY - offsetY}};
        }});

        canvas.addEventListener('mousemove', (e) => {{
            if (isDragging) {{
                offsetX = e.clientX - dragStart.x;
                offsetY = e.clientY - dragStart.y;
            }} else {{
                // Tooltip
                const mx = (e.clientX - offsetX) / scale;
                const my = (e.clientY - offsetY) / scale;

                let found = null;
                for (const node of nodes) {{
                    const dx = mx - node.x;
                    const dy = my - node.y;
                    if (dx * dx + dy * dy < node.radius * node.radius) {{
                        found = node;
                        break;
                    }}
                }}

                if (found) {{
                    tooltip.innerHTML = `
                        <h4>${{found.name}}</h4>
                        <p>Domain: ${{found.domain}}</p>
                        <p>Lines: ${{found.lines}}</p>
                        <p>Hub: ${{(found.hub * 100).toFixed(1)}}%</p>
                        <p>Authority: ${{(found.authority * 100).toFixed(1)}}%</p>
                        <p>In: ${{found.in_deg}} | Out: ${{found.out_deg}}</p>
                    `;
                    tooltip.style.display = 'block';
                    tooltip.style.left = (e.clientX + 15) + 'px';
                    tooltip.style.top = (e.clientY + 15) + 'px';
                }} else {{
                    tooltip.style.display = 'none';
                }}
            }}
        }});

        canvas.addEventListener('mouseup', () => {{
            isDragging = false;
        }});

        canvas.addEventListener('wheel', (e) => {{
            e.preventDefault();
            const zoom = e.deltaY > 0 ? 0.9 : 1.1;
            scale *= zoom;
            scale = Math.max(0.1, Math.min(5, scale));
        }});

        // Controls
        document.getElementById('resetBtn').addEventListener('click', () => {{
            offsetX = 0;
            offsetY = 0;
            scale = 1;
        }});

        document.getElementById('toggleLabels').addEventListener('click', () => {{
            showLabels = !showLabels;
        }});

        window.addEventListener('resize', resize);

        init();
    </script>
</body>
</html>"""

        return html


def generate_architecture(
    conn: sqlite3.Connection,
    output_path: str | None = None,
    project_path: str = ".",
) -> dict[str, Any]:
    """
    Generate architecture diagram visualization.

    Args:
        conn: Database connection.
        output_path: Where to save the HTML file.
        project_path: Path to the project root.

    Returns:
        Result with node/link counts and output path.
    """
    generator = ArchitectureGenerator(conn)
    nodes, links = generator.build_graph()

    if not output_path:
        output_path = str(Path(project_path) / "deltacodecube_architecture.html")

    if not nodes:
        return {
            "error": "No files indexed",
            "nodes_count": 0,
        }

    # Calculate stats
    domains = {}
    for node in nodes:
        domains[node.domain] = domains.get(node.domain, 0) + 1

    hubs = len([n for n in nodes if n.hub_score > 0.5])
    authorities = len([n for n in nodes if n.authority_score > 0.5])

    html = generator.generate_html(nodes, links)
    Path(output_path).write_text(html, encoding="utf-8")

    return {
        "nodes_count": len(nodes),
        "links_count": len(links),
        "domains": domains,
        "hubs": hubs,
        "authorities": authorities,
        "output_path": output_path,
    }
