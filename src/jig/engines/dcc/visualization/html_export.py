"""
HTML visualization export for DeltaCodeCube.

Generates an interactive HTML file with:
- 3D scatter plot of code points (reduced to 3D via PCA-like projection)
- Color-coded by semantic domain
- Hover tooltips with file info
- Contract/dependency lines
- Pan, zoom, and rotate controls

All JavaScript is embedded inline - no external dependencies.
"""

import json
from pathlib import Path
from typing import Any


# Domain colors (matching semantic domains)
DOMAIN_COLORS = {
    "auth": "#e74c3c",    # Red
    "db": "#3498db",      # Blue
    "api": "#2ecc71",     # Green
    "ui": "#9b59b6",      # Purple
    "util": "#f39c12",    # Orange
    "unknown": "#95a5a6", # Gray
}


def generate_html_visualization(
    code_points: list[dict[str, Any]],
    contracts: list[dict[str, Any]] | None = None,
    tensions: list[dict[str, Any]] | None = None,
    output_path: str | None = None,
) -> str:
    """
    Generate an interactive HTML visualization of the code cube.

    Args:
        code_points: List of code point dictionaries with positions.
        contracts: Optional list of contract relationships.
        tensions: Optional list of detected tensions.
        output_path: Optional path to save the HTML file.

    Returns:
        HTML content as string.
    """
    contracts = contracts or []
    tensions = tensions or []

    # Prepare data for JavaScript
    points_data = []
    for cp in code_points:
        # Use the 3D export format if available
        if "x" in cp and "y" in cp and "z" in cp:
            point = {
                "id": cp.get("id", ""),
                "name": cp.get("name", Path(cp.get("file_path", "")).name),
                "path": cp.get("file_path", ""),
                "domain": cp.get("domain", "unknown"),
                "x": cp["x"],
                "y": cp["y"],
                "z": cp["z"],
                "lines": cp.get("line_count", 0),
            }
        else:
            # Fallback - use first 3 dimensions
            pos = cp.get("position", [0, 0, 0])
            point = {
                "id": cp.get("id", ""),
                "name": cp.get("name", Path(cp.get("file_path", "")).name),
                "path": cp.get("file_path", ""),
                "domain": cp.get("domain", "unknown"),
                "x": pos[0] if len(pos) > 0 else 0,
                "y": pos[1] if len(pos) > 1 else 0,
                "z": pos[2] if len(pos) > 2 else 0,
                "lines": cp.get("line_count", 0),
            }
        points_data.append(point)

    # Prepare contract lines
    contract_lines = []
    point_ids = {p["id"] for p in points_data}
    for contract in contracts:
        caller_id = contract.get("caller_id", "")
        callee_id = contract.get("callee_id", "")
        if caller_id in point_ids and callee_id in point_ids:
            contract_lines.append({
                "from": caller_id,
                "to": callee_id,
                "distance": contract.get("baseline_distance", 0),
            })

    # Prepare tension highlights
    tension_ids = set()
    for tension in tensions:
        if tension.get("status") == "detected":
            # Mark files involved in tensions
            tension_ids.add(tension.get("caller_path", ""))
            tension_ids.add(tension.get("callee_path", ""))

    html = _generate_html(points_data, contract_lines, list(tension_ids))

    if output_path:
        Path(output_path).write_text(html, encoding="utf-8")

    return html


def _generate_html(
    points: list[dict],
    contracts: list[dict],
    tension_paths: list[str],
) -> str:
    """Generate the complete HTML document."""
    points_json = json.dumps(points)
    contracts_json = json.dumps(contracts)
    tension_paths_json = json.dumps(tension_paths)
    domain_colors_json = json.dumps(DOMAIN_COLORS)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DeltaCodeCube Visualization</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            overflow: hidden;
        }}
        #container {{
            width: 100vw;
            height: 100vh;
            position: relative;
        }}
        canvas {{
            display: block;
        }}
        #info {{
            position: absolute;
            top: 20px;
            left: 20px;
            background: rgba(0,0,0,0.7);
            padding: 15px;
            border-radius: 8px;
            max-width: 300px;
        }}
        #info h1 {{
            font-size: 18px;
            margin-bottom: 10px;
            color: #fff;
        }}
        #stats {{
            font-size: 12px;
            color: #aaa;
        }}
        #legend {{
            position: absolute;
            top: 20px;
            right: 20px;
            background: rgba(0,0,0,0.7);
            padding: 15px;
            border-radius: 8px;
        }}
        #legend h3 {{
            margin-bottom: 10px;
            font-size: 14px;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            margin: 5px 0;
            font-size: 12px;
        }}
        .legend-color {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
        }}
        #tooltip {{
            position: absolute;
            background: rgba(0,0,0,0.9);
            padding: 10px 15px;
            border-radius: 6px;
            font-size: 12px;
            pointer-events: none;
            display: none;
            z-index: 100;
            border: 1px solid #444;
        }}
        #tooltip .name {{
            font-weight: bold;
            color: #fff;
            margin-bottom: 5px;
        }}
        #tooltip .details {{
            color: #aaa;
        }}
        #controls {{
            position: absolute;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(0,0,0,0.7);
            padding: 10px 20px;
            border-radius: 8px;
            font-size: 12px;
            color: #888;
        }}
    </style>
</head>
<body>
    <div id="container">
        <canvas id="canvas"></canvas>
        <div id="info">
            <h1>DeltaCodeCube</h1>
            <div id="stats">Loading...</div>
        </div>
        <div id="legend">
            <h3>Domains</h3>
            <div id="legend-items"></div>
        </div>
        <div id="tooltip">
            <div class="name"></div>
            <div class="details"></div>
        </div>
        <div id="controls">
            Drag to rotate | Scroll to zoom | Shift+drag to pan
        </div>
    </div>
    <script>
        // Data
        const points = {points_json};
        const contracts = {contracts_json};
        const tensionPaths = new Set({tension_paths_json});
        const domainColors = {domain_colors_json};

        // Canvas setup
        const canvas = document.getElementById('canvas');
        const ctx = canvas.getContext('2d');
        let width, height;

        function resize() {{
            width = window.innerWidth;
            height = window.innerHeight;
            canvas.width = width;
            canvas.height = height;
        }}
        resize();
        window.addEventListener('resize', resize);

        // Camera
        let rotationX = 0.3;
        let rotationY = 0.5;
        let zoom = 2;
        let panX = 0;
        let panY = 0;

        // Find data bounds
        let minX = Infinity, maxX = -Infinity;
        let minY = Infinity, maxY = -Infinity;
        let minZ = Infinity, maxZ = -Infinity;

        points.forEach(p => {{
            minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x);
            minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y);
            minZ = Math.min(minZ, p.z); maxZ = Math.max(maxZ, p.z);
        }});

        const rangeX = maxX - minX || 1;
        const rangeY = maxY - minY || 1;
        const rangeZ = maxZ - minZ || 1;
        const maxRange = Math.max(rangeX, rangeY, rangeZ);

        // Normalize points to [-1, 1]
        points.forEach(p => {{
            p.nx = ((p.x - minX) / maxRange - 0.5) * 2;
            p.ny = ((p.y - minY) / maxRange - 0.5) * 2;
            p.nz = ((p.z - minZ) / maxRange - 0.5) * 2;
        }});

        // Project 3D to 2D
        function project(x, y, z) {{
            // Rotate around Y axis
            const cosY = Math.cos(rotationY);
            const sinY = Math.sin(rotationY);
            const x1 = x * cosY - z * sinY;
            const z1 = x * sinY + z * cosY;

            // Rotate around X axis
            const cosX = Math.cos(rotationX);
            const sinX = Math.sin(rotationX);
            const y1 = y * cosX - z1 * sinX;
            const z2 = y * sinX + z1 * cosX;

            // Perspective projection
            const scale = 200 * zoom / (z2 + 3);
            const px = x1 * scale + width / 2 + panX;
            const py = -y1 * scale + height / 2 + panY;

            return {{ x: px, y: py, z: z2, scale: scale }};
        }}

        // Mouse interaction
        let isDragging = false;
        let lastX, lastY;
        let shiftKey = false;

        canvas.addEventListener('mousedown', e => {{
            isDragging = true;
            lastX = e.clientX;
            lastY = e.clientY;
            shiftKey = e.shiftKey;
        }});

        canvas.addEventListener('mousemove', e => {{
            if (isDragging) {{
                const dx = e.clientX - lastX;
                const dy = e.clientY - lastY;

                if (shiftKey) {{
                    panX += dx;
                    panY += dy;
                }} else {{
                    rotationY += dx * 0.01;
                    rotationX += dy * 0.01;
                }}

                lastX = e.clientX;
                lastY = e.clientY;
            }} else {{
                // Hover detection
                checkHover(e.clientX, e.clientY);
            }}
        }});

        canvas.addEventListener('mouseup', () => isDragging = false);
        canvas.addEventListener('mouseleave', () => isDragging = false);

        canvas.addEventListener('wheel', e => {{
            e.preventDefault();
            zoom *= e.deltaY > 0 ? 0.9 : 1.1;
            zoom = Math.max(0.5, Math.min(10, zoom));
        }});

        // Tooltip
        const tooltip = document.getElementById('tooltip');
        let hoveredPoint = null;

        function checkHover(mx, my) {{
            hoveredPoint = null;
            let minDist = 20;

            points.forEach(p => {{
                const proj = project(p.nx, p.ny, p.nz);
                const dist = Math.sqrt((proj.x - mx) ** 2 + (proj.y - my) ** 2);
                if (dist < minDist) {{
                    minDist = dist;
                    hoveredPoint = p;
                }}
            }});

            if (hoveredPoint) {{
                tooltip.style.display = 'block';
                tooltip.style.left = (mx + 15) + 'px';
                tooltip.style.top = (my + 15) + 'px';
                tooltip.querySelector('.name').textContent = hoveredPoint.name;
                tooltip.querySelector('.details').innerHTML =
                    `Domain: ${{hoveredPoint.domain}}<br>` +
                    `Lines: ${{hoveredPoint.lines}}<br>` +
                    `Path: ${{hoveredPoint.path}}`;
            }} else {{
                tooltip.style.display = 'none';
            }}
        }}

        // Render
        function render() {{
            ctx.fillStyle = '#1a1a2e';
            ctx.fillRect(0, 0, width, height);

            // Sort points by Z for depth ordering
            const projected = points.map(p => ({{
                ...p,
                proj: project(p.nx, p.ny, p.nz)
            }}));
            projected.sort((a, b) => b.proj.z - a.proj.z);

            // Draw contract lines
            ctx.strokeStyle = 'rgba(100, 100, 100, 0.3)';
            ctx.lineWidth = 1;
            contracts.forEach(c => {{
                const from = points.find(p => p.id === c.from);
                const to = points.find(p => p.id === c.to);
                if (from && to) {{
                    const p1 = project(from.nx, from.ny, from.nz);
                    const p2 = project(to.nx, to.ny, to.nz);
                    ctx.beginPath();
                    ctx.moveTo(p1.x, p1.y);
                    ctx.lineTo(p2.x, p2.y);
                    ctx.stroke();
                }}
            }});

            // Draw points
            projected.forEach(p => {{
                const {{ proj }} = p;
                const radius = Math.max(3, Math.min(15, proj.scale * 0.05));
                const color = domainColors[p.domain] || domainColors.unknown;
                const hasTension = tensionPaths.has(p.path);

                // Glow for hovered or tension points
                if (p === hoveredPoint || hasTension) {{
                    ctx.beginPath();
                    ctx.arc(proj.x, proj.y, radius + 5, 0, Math.PI * 2);
                    ctx.fillStyle = hasTension ? 'rgba(231, 76, 60, 0.3)' : 'rgba(255, 255, 255, 0.3)';
                    ctx.fill();
                }}

                ctx.beginPath();
                ctx.arc(proj.x, proj.y, radius, 0, Math.PI * 2);
                ctx.fillStyle = color;
                ctx.fill();

                // Border
                ctx.strokeStyle = p === hoveredPoint ? '#fff' : 'rgba(255,255,255,0.3)';
                ctx.lineWidth = p === hoveredPoint ? 2 : 1;
                ctx.stroke();
            }});

            requestAnimationFrame(render);
        }}

        // Update stats
        const domainCounts = {{}};
        points.forEach(p => {{
            domainCounts[p.domain] = (domainCounts[p.domain] || 0) + 1;
        }});

        document.getElementById('stats').innerHTML =
            `${{points.length}} files indexed<br>` +
            `${{contracts.length}} contracts detected<br>` +
            `${{tensionPaths.size}} files with tensions`;

        // Build legend
        const legendItems = document.getElementById('legend-items');
        Object.entries(domainColors).forEach(([domain, color]) => {{
            const count = domainCounts[domain] || 0;
            if (count > 0 || domain !== 'unknown') {{
                const item = document.createElement('div');
                item.className = 'legend-item';
                item.innerHTML = `<div class="legend-color" style="background: ${{color}}"></div>${{domain}} (${{count}})`;
                legendItems.appendChild(item);
            }}
        }});

        // Start rendering
        render();
    </script>
</body>
</html>
'''
