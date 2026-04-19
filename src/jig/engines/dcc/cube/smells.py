"""
Code Smell Detection for DeltaCodeCube.

Detects problematic patterns in the codebase using:
- Graph centrality metrics
- Structural features
- Temporal features
- Contract analysis

Detected smells:
1. God File: Too many responsibilities (high in-degree + high complexity)
2. Orphan: No dependencies in or out (isolated code)
3. Circular Dependencies: A -> B -> A cycles
4. Feature Envy: Imports heavily from one specific module
5. Shotgun Surgery: High volatility + many dependents
6. Hub Overload: Too many outgoing dependencies
7. Unstable Interface: High PageRank + high change frequency
8. Dead Code Candidate: No incoming dependencies, low temporal activity
"""

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from jig.engines.dcc.cube.graph import DependencyGraph
from jig.engines.dcc.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class CodeSmell:
    """A detected code smell."""
    smell_type: str
    severity: str  # "low", "medium", "high", "critical"
    file_path: str
    file_name: str
    description: str
    metrics: dict[str, Any]
    suggestion: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.smell_type,
            "severity": self.severity,
            "file_path": self.file_path,
            "file_name": self.file_name,
            "description": self.description,
            "metrics": self.metrics,
            "suggestion": self.suggestion,
        }


class SmellDetector:
    """
    Detects code smells using graph and structural analysis.
    """

    # Thresholds for smell detection
    GOD_FILE_IN_DEGREE = 8
    GOD_FILE_COMPLEXITY = 0.6
    GOD_FILE_LINES = 500

    HUB_OVERLOAD_OUT_DEGREE = 15
    FEATURE_ENVY_RATIO = 0.6  # 60% of imports from one source

    HIGH_PAGERANK = 0.1
    HIGH_BETWEENNESS = 0.1
    HIGH_CHANGE_FREQ = 0.5

    def __init__(self, conn: sqlite3.Connection):
        """Initialize with database connection."""
        self.conn = conn
        self.graph = DependencyGraph(conn)
        self.smells: list[CodeSmell] = []

    def detect_all(self) -> list[CodeSmell]:
        """
        Run all smell detectors.

        Returns:
            List of detected code smells.
        """
        self.smells = []

        # Build and analyze graph
        self.graph.build_graph()
        self.graph.compute_pagerank()
        self.graph.compute_hits()
        self.graph.compute_betweenness()

        # Load structural features
        structural_data = self._load_structural_features()

        # Run detectors
        self._detect_god_files(structural_data)
        self._detect_orphans()
        self._detect_circular_dependencies()
        self._detect_feature_envy()
        self._detect_hub_overload()
        self._detect_unstable_interfaces()
        self._detect_dead_code_candidates()

        # Sort by severity
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        self.smells.sort(key=lambda s: severity_order.get(s.severity, 4))

        return self.smells

    def _load_structural_features(self) -> dict[str, dict[str, float]]:
        """Load structural features from database."""
        import json

        cursor = self.conn.execute("""
            SELECT id, file_path, structural_features, line_count
            FROM code_points
        """)

        data = {}
        for row in cursor.fetchall():
            features = json.loads(row["structural_features"])
            data[row["id"]] = {
                "file_path": row["file_path"],
                "line_count": row["line_count"],
                "cyclomatic": features[6] if len(features) > 6 else 0,  # cyclomatic_estimate
                "num_functions": features[1] if len(features) > 1 else 0,
                "coupling": features[15] if len(features) > 15 else 0,  # coupling_estimate
            }
        return data

    def _detect_god_files(self, structural_data: dict[str, dict]) -> None:
        """
        Detect God Files - files with too many responsibilities.

        Criteria:
        - High in-degree (many files depend on it)
        - High complexity
        - High line count
        """
        for node_id, node in self.graph.nodes.items():
            struct = structural_data.get(node_id, {})
            line_count = struct.get("line_count", 0)
            complexity = struct.get("cyclomatic", 0)

            is_god = (
                node.in_degree >= self.GOD_FILE_IN_DEGREE and
                (complexity >= self.GOD_FILE_COMPLEXITY or line_count >= self.GOD_FILE_LINES)
            )

            if is_god:
                severity = "critical" if node.in_degree > 12 else "high"
                self.smells.append(CodeSmell(
                    smell_type="god_file",
                    severity=severity,
                    file_path=node.file_path,
                    file_name=node.name,
                    description=f"God File: {node.in_degree} files depend on this, "
                               f"{line_count} lines, complexity {complexity:.2f}",
                    metrics={
                        "in_degree": node.in_degree,
                        "line_count": line_count,
                        "complexity": complexity,
                        "pagerank": node.pagerank,
                    },
                    suggestion="Consider splitting into smaller, focused modules. "
                              "Extract related functionality into separate files.",
                ))

    def _detect_orphans(self) -> None:
        """
        Detect Orphan files - completely isolated code.

        Criteria:
        - No incoming dependencies
        - No outgoing dependencies
        - Not an entry point (index, main, app)
        """
        entry_patterns = ["index", "main", "app", "server", "__init__", "mod"]

        for node_id, node in self.graph.nodes.items():
            is_entry = any(p in node.name.lower() for p in entry_patterns)

            if node.in_degree == 0 and node.out_degree == 0 and not is_entry:
                self.smells.append(CodeSmell(
                    smell_type="orphan",
                    severity="medium",
                    file_path=node.file_path,
                    file_name=node.name,
                    description="Orphan: No dependencies detected (isolated code)",
                    metrics={
                        "in_degree": 0,
                        "out_degree": 0,
                    },
                    suggestion="This file may be dead code, or imports weren't detected. "
                              "Consider removing if unused, or verify it's a valid entry point.",
                ))

    def _detect_circular_dependencies(self) -> None:
        """
        Detect circular dependencies in the graph.

        Uses DFS to find back edges indicating cycles.
        """
        visited = set()
        rec_stack = set()
        cycles = []

        def dfs(node_id: str, path: list[str]) -> None:
            visited.add(node_id)
            rec_stack.add(node_id)
            path.append(node_id)

            for neighbor_id in self.graph.adjacency.get(node_id, set()):
                if neighbor_id not in visited:
                    dfs(neighbor_id, path)
                elif neighbor_id in rec_stack:
                    # Found cycle
                    cycle_start = path.index(neighbor_id)
                    cycle = path[cycle_start:] + [neighbor_id]
                    cycles.append(cycle)

            path.pop()
            rec_stack.remove(node_id)

        for node_id in self.graph.nodes:
            if node_id not in visited:
                dfs(node_id, [])

        # Report unique cycles
        reported = set()
        for cycle in cycles:
            if len(cycle) <= 3:  # Direct A <-> B cycles
                cycle_key = tuple(sorted(cycle[:2]))
                if cycle_key not in reported:
                    reported.add(cycle_key)

                    node_a = self.graph.nodes[cycle[0]]
                    node_b = self.graph.nodes[cycle[1]]

                    self.smells.append(CodeSmell(
                        smell_type="circular_dependency",
                        severity="high",
                        file_path=node_a.file_path,
                        file_name=f"{node_a.name} <-> {node_b.name}",
                        description=f"Circular dependency: {node_a.name} and {node_b.name} depend on each other",
                        metrics={
                            "cycle_length": len(cycle) - 1,
                            "files": [self.graph.nodes[nid].name for nid in cycle[:-1]],
                        },
                        suggestion="Break the cycle by extracting shared code into a third module, "
                                  "or use dependency injection.",
                    ))

    def _detect_feature_envy(self) -> None:
        """
        Detect Feature Envy - files that import heavily from one source.

        Criteria:
        - More than 60% of imports from a single other file/module
        """
        for node_id, node in self.graph.nodes.items():
            targets = self.graph.adjacency.get(node_id, set())

            if len(targets) < 3:  # Need at least 3 imports to detect envy
                continue

            # Count imports by target
            target_domains: dict[str, int] = {}
            for target_id in targets:
                target_node = self.graph.nodes.get(target_id)
                if target_node:
                    # Group by parent directory
                    parent = str(Path(target_node.file_path).parent.name)
                    target_domains[parent] = target_domains.get(parent, 0) + 1

            if not target_domains:
                continue

            # Check if one domain dominates
            max_domain = max(target_domains, key=target_domains.get)
            max_count = target_domains[max_domain]
            total = sum(target_domains.values())
            ratio = max_count / total

            if ratio >= self.FEATURE_ENVY_RATIO and max_count >= 3:
                self.smells.append(CodeSmell(
                    smell_type="feature_envy",
                    severity="medium",
                    file_path=node.file_path,
                    file_name=node.name,
                    description=f"Feature Envy: {ratio:.0%} of imports from '{max_domain}' module",
                    metrics={
                        "dominant_module": max_domain,
                        "ratio": ratio,
                        "imports_from_dominant": max_count,
                        "total_imports": total,
                    },
                    suggestion=f"Consider moving this file to the '{max_domain}' module, "
                              "or extract the shared functionality.",
                ))

    def _detect_hub_overload(self) -> None:
        """
        Detect Hub Overload - files with too many outgoing dependencies.

        Criteria:
        - Very high out-degree (imports many files)
        """
        for node_id, node in self.graph.nodes.items():
            # Skip known hub patterns
            hub_patterns = ["index", "barrel", "exports", "__init__"]
            is_intended_hub = any(p in node.name.lower() for p in hub_patterns)

            if node.out_degree >= self.HUB_OVERLOAD_OUT_DEGREE and not is_intended_hub:
                severity = "high" if node.out_degree > 20 else "medium"
                self.smells.append(CodeSmell(
                    smell_type="hub_overload",
                    severity=severity,
                    file_path=node.file_path,
                    file_name=node.name,
                    description=f"Hub Overload: Imports {node.out_degree} other files",
                    metrics={
                        "out_degree": node.out_degree,
                        "hub_score": node.hub_score,
                    },
                    suggestion="This file has too many dependencies. Consider splitting "
                              "into smaller files with focused responsibilities.",
                ))

    def _detect_unstable_interfaces(self) -> None:
        """
        Detect Unstable Interfaces - high-importance files that change frequently.

        Criteria:
        - High PageRank (many depend on it)
        - High change frequency (from git history)
        """
        # Get temporal features if available
        from jig.engines.dcc.cube.features.temporal import extract_temporal_features

        for node_id, node in self.graph.nodes.items():
            if node.pagerank < self.HIGH_PAGERANK:
                continue

            # Get temporal features
            try:
                temporal = extract_temporal_features(node.file_path)
                change_freq = temporal[1]  # change_frequency index
            except Exception:
                change_freq = 0

            if change_freq >= self.HIGH_CHANGE_FREQ:
                self.smells.append(CodeSmell(
                    smell_type="unstable_interface",
                    severity="high",
                    file_path=node.file_path,
                    file_name=node.name,
                    description=f"Unstable Interface: Important file (PageRank {node.pagerank:.2f}) "
                               f"with high change frequency ({change_freq:.0%})",
                    metrics={
                        "pagerank": node.pagerank,
                        "change_frequency": change_freq,
                        "in_degree": node.in_degree,
                    },
                    suggestion="This critical file changes too often. Consider stabilizing "
                              "the API, adding tests, or extracting volatile parts.",
                ))

    def _detect_dead_code_candidates(self) -> None:
        """
        Detect Dead Code Candidates - unused files with no activity.

        Criteria:
        - No incoming dependencies
        - Low/no recent git activity
        """
        from jig.engines.dcc.cube.features.temporal import extract_temporal_features

        for node_id, node in self.graph.nodes.items():
            if node.in_degree > 0:
                continue

            # Skip entry points
            entry_patterns = ["index", "main", "app", "server", "__init__", "test", "spec"]
            if any(p in node.name.lower() for p in entry_patterns):
                continue

            # Check temporal features
            try:
                temporal = extract_temporal_features(node.file_path)
                days_since = temporal[3]  # days_since_change (inverted, 0 = stale)
                stability = temporal[4]   # stability_score
            except Exception:
                days_since = 0
                stability = 1

            # No dependencies and stale
            if days_since < 0.2 and stability > 0.8:
                self.smells.append(CodeSmell(
                    smell_type="dead_code_candidate",
                    severity="low",
                    file_path=node.file_path,
                    file_name=node.name,
                    description="Dead Code Candidate: No files depend on this and it hasn't "
                               "been modified recently",
                    metrics={
                        "in_degree": 0,
                        "days_since_change": days_since,
                        "stability": stability,
                    },
                    suggestion="Verify if this file is still used. It may be safe to remove, "
                              "or it could be an undiscovered entry point.",
                ))


def detect_code_smells(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """
    Convenience function to detect all code smells.

    Args:
        conn: Database connection.

    Returns:
        List of detected smells as dictionaries.
    """
    detector = SmellDetector(conn)
    smells = detector.detect_all()
    return [s.to_dict() for s in smells]


_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def get_smell_summary(
    conn: sqlite3.Connection,
    summary_only: bool = False,
    min_severity: str | None = None,
    smell_type: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """
    Get summary of detected code smells with optional filtering.

    Args:
        conn: Database connection.
        summary_only: If True, return only aggregated counts (no smells array).
        min_severity: Filter smells to this severity or higher
                      (critical > high > medium > low).
        smell_type: Filter by smell type (god_file, orphan, etc.).
        limit: Max smells to include in the details array (default 50).

    Returns:
        Summary with counts by type and severity, and optionally filtered smells.
    """
    detector = SmellDetector(conn)
    all_smells = detector.detect_all()

    # --- aggregated counts (always computed from ALL smells, pre-filter) ---
    by_type: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for smell in all_smells:
        by_type[smell.smell_type] = by_type.get(smell.smell_type, 0) + 1
        by_severity[smell.severity] = by_severity.get(smell.severity, 0) + 1

    result: dict[str, Any] = {
        "total_smells": len(all_smells),
        "by_type": by_type,
        "by_severity": by_severity,
    }

    if summary_only:
        result["hint"] = (
            "Use cube_detect_smells(smell_type='...') or "
            "cube_detect_smells(min_severity='critical') to see full details."
        )
        return result

    # --- apply filters for the details array ---
    filtered = all_smells

    if min_severity is not None:
        threshold = _SEVERITY_RANK.get(min_severity, 3)
        filtered = [s for s in filtered if _SEVERITY_RANK.get(s.severity, 4) <= threshold]

    if smell_type is not None:
        filtered = [s for s in filtered if s.smell_type == smell_type]

    result["smells"] = [s.to_dict() for s in filtered[:limit]]
    return result
