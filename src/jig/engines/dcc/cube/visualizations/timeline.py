"""
Timeline Visualization for DeltaCodeCube.

Generates an interactive HTML timeline showing:
- Code evolution over time
- Deltas (code changes) as events
- Tension creation/resolution
- File activity patterns

Uses git history and stored deltas for data.
"""

import json
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from jig.engines.dcc.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TimelineEvent:
    """A single event on the timeline."""
    timestamp: datetime
    event_type: str  # "delta", "tension", "commit", "index"
    title: str
    description: str
    file_path: str | None
    severity: str | None  # "low", "medium", "high" for tensions
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "title": self.title,
            "description": self.description,
            "file_path": self.file_path,
            "file_name": Path(self.file_path).name if self.file_path else None,
            "severity": self.severity,
            "metadata": self.metadata,
        }


class TimelineGenerator:
    """Generates timeline visualization."""

    def __init__(self, conn: sqlite3.Connection, project_path: str):
        """Initialize with database connection and project path."""
        self.conn = conn
        self.project_path = Path(project_path)

    def collect_events(self, limit: int = 100) -> list[TimelineEvent]:
        """
        Collect all timeline events from various sources.

        Args:
            limit: Maximum events to collect.

        Returns:
            List of timeline events sorted by timestamp.
        """
        events = []

        # 1. Collect deltas from database
        events.extend(self._collect_delta_events())

        # 2. Collect tensions from database
        events.extend(self._collect_tension_events())

        # 3. Collect git commits
        events.extend(self._collect_git_events())

        # Sort by timestamp (newest first)
        events.sort(key=lambda e: e.timestamp, reverse=True)

        return events[:limit]

    def _collect_delta_events(self) -> list[TimelineEvent]:
        """Collect code change (delta) events."""
        events = []

        try:
            cursor = self.conn.execute("""
                SELECT d.id, d.created_at, d.total_distance,
                       d.lexical_change, d.structural_change, d.semantic_change,
                       cp.file_path
                FROM deltas d
                JOIN code_points cp ON d.code_point_id = cp.id
                ORDER BY d.created_at DESC
                LIMIT 50
            """)

            for row in cursor.fetchall():
                # Determine change magnitude
                distance = row["total_distance"]
                if distance > 0.5:
                    severity = "high"
                elif distance > 0.2:
                    severity = "medium"
                else:
                    severity = "low"

                # Determine dominant change type
                changes = {
                    "lexical": row["lexical_change"],
                    "structural": row["structural_change"],
                    "semantic": row["semantic_change"],
                }
                dominant = max(changes, key=changes.get)

                events.append(TimelineEvent(
                    timestamp=datetime.fromisoformat(row["created_at"]),
                    event_type="delta",
                    title=f"Code changed: {Path(row['file_path']).name}",
                    description=f"Dominant change: {dominant} ({changes[dominant]:.3f})",
                    file_path=row["file_path"],
                    severity=severity,
                    metadata={
                        "distance": distance,
                        "lexical": row["lexical_change"],
                        "structural": row["structural_change"],
                        "semantic": row["semantic_change"],
                    },
                ))

        except Exception as e:
            logger.debug(f"Could not collect delta events: {e}")

        return events

    def _collect_tension_events(self) -> list[TimelineEvent]:
        """Collect tension creation/resolution events."""
        events = []

        try:
            cursor = self.conn.execute("""
                SELECT t.id, t.created_at, t.status, t.severity,
                       t.distance_deviation, t.suggested_action,
                       cp.file_path
                FROM tensions t
                JOIN contracts c ON t.contract_id = c.id
                JOIN code_points cp ON c.callee_id = cp.id
                ORDER BY t.created_at DESC
                LIMIT 30
            """)

            for row in cursor.fetchall():
                status = row["status"]
                if status == "resolved":
                    title = f"Tension resolved: {Path(row['file_path']).name}"
                    event_type = "tension_resolved"
                else:
                    title = f"Tension detected: {Path(row['file_path']).name}"
                    event_type = "tension"

                events.append(TimelineEvent(
                    timestamp=datetime.fromisoformat(row["created_at"]),
                    event_type=event_type,
                    title=title,
                    description=row["suggested_action"] or "Review needed",
                    file_path=row["file_path"],
                    severity=row["severity"],
                    metadata={
                        "status": status,
                        "deviation": row["distance_deviation"],
                    },
                ))

        except Exception as e:
            logger.debug(f"Could not collect tension events: {e}")

        return events

    def _collect_git_events(self) -> list[TimelineEvent]:
        """Collect recent git commits."""
        events = []

        try:
            # Get recent commits
            result = subprocess.run(
                ["git", "log", "--oneline", "--format=%H|%ai|%s", "-n", "30"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if not line:
                        continue

                    parts = line.split("|", 2)
                    if len(parts) < 3:
                        continue

                    commit_hash, date_str, message = parts
                    timestamp = datetime.fromisoformat(date_str.replace(" ", "T").rsplit("+", 1)[0].rsplit("-", 1)[0])

                    events.append(TimelineEvent(
                        timestamp=timestamp,
                        event_type="commit",
                        title=f"Commit: {message[:50]}",
                        description=f"SHA: {commit_hash[:8]}",
                        file_path=None,
                        severity=None,
                        metadata={
                            "hash": commit_hash,
                            "message": message,
                        },
                    ))

        except Exception as e:
            logger.debug(f"Could not collect git events: {e}")

        return events

    def generate_html(self, events: list[TimelineEvent]) -> str:
        """
        Generate HTML visualization for timeline.

        Args:
            events: List of timeline events.

        Returns:
            Complete HTML page as string.
        """
        events_json = json.dumps([e.to_dict() for e in events])

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DeltaCodeCube Timeline</title>
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
            margin-bottom: 2rem;
            color: #a78bfa;
        }}
        .timeline {{
            max-width: 800px;
            margin: 0 auto;
            position: relative;
        }}
        .timeline::before {{
            content: '';
            position: absolute;
            left: 20px;
            top: 0;
            bottom: 0;
            width: 2px;
            background: linear-gradient(to bottom, #a78bfa, #6366f1, #8b5cf6);
        }}
        .event {{
            position: relative;
            padding-left: 50px;
            margin-bottom: 1.5rem;
        }}
        .event::before {{
            content: '';
            position: absolute;
            left: 12px;
            top: 8px;
            width: 18px;
            height: 18px;
            border-radius: 50%;
            border: 3px solid #1a1a2e;
        }}
        .event.delta::before {{ background: #3b82f6; }}
        .event.tension::before {{ background: #ef4444; }}
        .event.tension_resolved::before {{ background: #22c55e; }}
        .event.commit::before {{ background: #a78bfa; }}
        .event-card {{
            background: rgba(30, 30, 46, 0.8);
            border-radius: 12px;
            padding: 1rem 1.25rem;
            border: 1px solid rgba(167, 139, 250, 0.2);
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .event-card:hover {{
            transform: translateX(5px);
            box-shadow: 0 4px 20px rgba(139, 92, 246, 0.3);
        }}
        .event-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.5rem;
        }}
        .event-title {{
            font-weight: 600;
            color: #f4f4f5;
        }}
        .event-time {{
            font-size: 0.8rem;
            color: #a1a1aa;
        }}
        .event-desc {{
            font-size: 0.9rem;
            color: #a1a1aa;
            margin-bottom: 0.5rem;
        }}
        .event-type {{
            display: inline-block;
            padding: 0.2rem 0.6rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 500;
        }}
        .type-delta {{ background: rgba(59, 130, 246, 0.2); color: #60a5fa; }}
        .type-tension {{ background: rgba(239, 68, 68, 0.2); color: #f87171; }}
        .type-tension_resolved {{ background: rgba(34, 197, 94, 0.2); color: #4ade80; }}
        .type-commit {{ background: rgba(167, 139, 250, 0.2); color: #c4b5fd; }}
        .severity {{
            margin-left: 0.5rem;
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            font-size: 0.7rem;
            text-transform: uppercase;
        }}
        .severity-high {{ background: rgba(239, 68, 68, 0.3); color: #fca5a5; }}
        .severity-medium {{ background: rgba(251, 191, 36, 0.3); color: #fcd34d; }}
        .severity-low {{ background: rgba(34, 197, 94, 0.3); color: #86efac; }}
        .filters {{
            display: flex;
            justify-content: center;
            gap: 0.5rem;
            margin-bottom: 2rem;
            flex-wrap: wrap;
        }}
        .filter-btn {{
            padding: 0.5rem 1rem;
            border: 1px solid rgba(167, 139, 250, 0.3);
            background: transparent;
            color: #a78bfa;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .filter-btn:hover, .filter-btn.active {{
            background: rgba(167, 139, 250, 0.2);
            border-color: #a78bfa;
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
    <h1>📊 DeltaCodeCube Timeline</h1>

    <div class="stats" id="stats"></div>

    <div class="filters">
        <button class="filter-btn active" data-filter="all">All</button>
        <button class="filter-btn" data-filter="delta">Deltas</button>
        <button class="filter-btn" data-filter="tension">Tensions</button>
        <button class="filter-btn" data-filter="commit">Commits</button>
    </div>

    <div class="timeline" id="timeline"></div>

    <script>
        const events = {events_json};
        let currentFilter = 'all';

        function formatDate(isoString) {{
            const date = new Date(isoString);
            return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], {{hour: '2-digit', minute:'2-digit'}});
        }}

        function renderStats() {{
            const stats = {{
                total: events.length,
                deltas: events.filter(e => e.event_type === 'delta').length,
                tensions: events.filter(e => e.event_type === 'tension' || e.event_type === 'tension_resolved').length,
                commits: events.filter(e => e.event_type === 'commit').length,
            }};

            document.getElementById('stats').innerHTML = `
                <div class="stat"><div class="stat-value">${{stats.total}}</div><div class="stat-label">Total Events</div></div>
                <div class="stat"><div class="stat-value">${{stats.deltas}}</div><div class="stat-label">Code Changes</div></div>
                <div class="stat"><div class="stat-value">${{stats.tensions}}</div><div class="stat-label">Tensions</div></div>
                <div class="stat"><div class="stat-value">${{stats.commits}}</div><div class="stat-label">Commits</div></div>
            `;
        }}

        function renderTimeline() {{
            const filtered = currentFilter === 'all'
                ? events
                : events.filter(e => e.event_type.startsWith(currentFilter));

            const html = filtered.map(event => `
                <div class="event ${{event.event_type}}">
                    <div class="event-card">
                        <div class="event-header">
                            <span class="event-title">${{event.title}}</span>
                            <span class="event-time">${{formatDate(event.timestamp)}}</span>
                        </div>
                        <div class="event-desc">${{event.description}}</div>
                        <span class="event-type type-${{event.event_type}}">${{event.event_type.replace('_', ' ')}}</span>
                        ${{event.severity ? `<span class="severity severity-${{event.severity}}">${{event.severity}}</span>` : ''}}
                    </div>
                </div>
            `).join('');

            document.getElementById('timeline').innerHTML = html || '<p style="text-align:center;color:#71717a;">No events found</p>';
        }}

        // Filter buttons
        document.querySelectorAll('.filter-btn').forEach(btn => {{
            btn.addEventListener('click', () => {{
                document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                currentFilter = btn.dataset.filter;
                renderTimeline();
            }});
        }});

        // Initial render
        renderStats();
        renderTimeline();
    </script>
</body>
</html>"""

        return html


def generate_timeline(
    conn: sqlite3.Connection,
    project_path: str,
    output_path: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Generate timeline visualization.

    Args:
        conn: Database connection.
        project_path: Path to the project root.
        output_path: Where to save the HTML file.
        limit: Maximum events to include.

    Returns:
        Result with event count and output path.
    """
    generator = TimelineGenerator(conn, project_path)
    events = generator.collect_events(limit)

    if not output_path:
        output_path = str(Path(project_path) / "deltacodecube_timeline.html")

    html = generator.generate_html(events)
    Path(output_path).write_text(html, encoding="utf-8")

    return {
        "events_count": len(events),
        "output_path": output_path,
        "by_type": {
            "deltas": len([e for e in events if e.event_type == "delta"]),
            "tensions": len([e for e in events if e.event_type.startswith("tension")]),
            "commits": len([e for e in events if e.event_type == "commit"]),
        },
    }
