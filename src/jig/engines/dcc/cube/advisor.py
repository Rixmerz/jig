"""
Refactoring Advisor for DeltaCodeCube.

Combines all analysis (graph, smells, clustering, tensions) to provide
actionable refactoring suggestions prioritized by impact and effort.

Suggestion types:
1. Split: Divide a large file into smaller ones
2. Merge: Combine related small files
3. Move: Relocate file to better module
4. Extract: Pull out shared code into utility
5. Stabilize: Add protection to critical interfaces
6. Remove: Delete dead code
7. Decouple: Break circular or tight dependencies
"""

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from jig.engines.dcc.cube.graph import DependencyGraph
from jig.engines.dcc.cube.smells import SmellDetector
from jig.engines.dcc.cube.clustering import SemanticClustering
from jig.engines.dcc.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RefactoringSuggestion:
    """A refactoring suggestion."""
    action: str  # split, merge, move, extract, stabilize, remove, decouple
    priority: str  # critical, high, medium, low
    impact: str  # high, medium, low
    effort: str  # high, medium, low
    target_files: list[str]
    description: str
    rationale: str
    steps: list[str]
    metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "action": self.action,
            "priority": self.priority,
            "impact": self.impact,
            "effort": self.effort,
            "target_files": self.target_files,
            "description": self.description,
            "rationale": self.rationale,
            "steps": self.steps,
            "metrics": self.metrics,
        }


class RefactoringAdvisor:
    """
    Generates refactoring suggestions based on comprehensive analysis.
    """

    def __init__(self, conn: sqlite3.Connection):
        """Initialize with database connection."""
        self.conn = conn
        self.suggestions: list[RefactoringSuggestion] = []

        # Run all analyses
        self.graph = DependencyGraph(conn)
        self.smell_detector = SmellDetector(conn)
        self.clustering = SemanticClustering(conn)

    def analyze(self) -> list[RefactoringSuggestion]:
        """
        Run comprehensive analysis and generate suggestions.

        Returns:
            List of prioritized refactoring suggestions.
        """
        self.suggestions = []

        # Build graph and compute metrics
        self.graph.build_graph()
        self.graph.compute_pagerank()
        self.graph.compute_hits()
        self.graph.compute_betweenness()

        # Detect smells
        smells = self.smell_detector.detect_all()

        # Run clustering
        self.clustering.load_data()
        clustering_result = self.clustering.cluster()

        # Generate suggestions from each source
        self._suggest_from_smells(smells)
        self._suggest_from_clustering(clustering_result)
        self._suggest_from_graph()
        self._suggest_from_tensions()

        # Deduplicate and prioritize
        self._deduplicate()
        self._prioritize()

        return self.suggestions

    def _suggest_from_smells(self, smells: list) -> None:
        """Generate suggestions from code smells."""
        for smell in smells:
            if smell.smell_type == "god_file":
                self.suggestions.append(RefactoringSuggestion(
                    action="split",
                    priority="high" if smell.severity == "critical" else "medium",
                    impact="high",
                    effort="high",
                    target_files=[smell.file_name],
                    description=f"Split {smell.file_name} into smaller, focused modules",
                    rationale=smell.description,
                    steps=[
                        f"1. Analyze {smell.file_name} to identify distinct responsibilities",
                        "2. Group related functions/classes together",
                        "3. Create new files for each responsibility group",
                        "4. Update imports in dependent files",
                        "5. Run tests to verify functionality",
                    ],
                    metrics=smell.metrics,
                ))

            elif smell.smell_type == "circular_dependency":
                self.suggestions.append(RefactoringSuggestion(
                    action="decouple",
                    priority="high",
                    impact="medium",
                    effort="medium",
                    target_files=[smell.file_name],
                    description=f"Break circular dependency: {smell.file_name}",
                    rationale=smell.description,
                    steps=[
                        "1. Identify shared functionality causing the cycle",
                        "2. Extract shared code into a new utility module",
                        "3. Have both files import from the new module",
                        "4. Remove direct imports between the cyclic files",
                    ],
                    metrics=smell.metrics,
                ))

            elif smell.smell_type == "feature_envy":
                self.suggestions.append(RefactoringSuggestion(
                    action="move",
                    priority="low",
                    impact="low",
                    effort="low",
                    target_files=[smell.file_name],
                    description=f"Consider moving {smell.file_name} to '{smell.metrics.get('dominant_module', 'target')}' module",
                    rationale=smell.description,
                    steps=[
                        f"1. Review if {smell.file_name} logically belongs to the other module",
                        "2. If yes, move the file to the appropriate directory",
                        "3. Update all import paths",
                    ],
                    metrics=smell.metrics,
                ))

            elif smell.smell_type == "dead_code_candidate":
                self.suggestions.append(RefactoringSuggestion(
                    action="remove",
                    priority="low",
                    impact="low",
                    effort="low",
                    target_files=[smell.file_name],
                    description=f"Verify and potentially remove {smell.file_name}",
                    rationale=smell.description,
                    steps=[
                        f"1. Search codebase for any references to {smell.file_name}",
                        "2. Check if it's an entry point or CLI script",
                        "3. If truly unused, archive or delete the file",
                    ],
                    metrics=smell.metrics,
                ))

            elif smell.smell_type == "unstable_interface":
                self.suggestions.append(RefactoringSuggestion(
                    action="stabilize",
                    priority="high",
                    impact="high",
                    effort="medium",
                    target_files=[smell.file_name],
                    description=f"Stabilize the interface of {smell.file_name}",
                    rationale=smell.description,
                    steps=[
                        "1. Document the public API clearly",
                        "2. Add comprehensive tests for the interface",
                        "3. Consider versioning or deprecation strategy",
                        "4. Extract volatile parts to separate files",
                    ],
                    metrics=smell.metrics,
                ))

            elif smell.smell_type == "hub_overload":
                self.suggestions.append(RefactoringSuggestion(
                    action="split",
                    priority="medium",
                    impact="medium",
                    effort="medium",
                    target_files=[smell.file_name],
                    description=f"Reduce dependencies in {smell.file_name}",
                    rationale=smell.description,
                    steps=[
                        "1. Group imports by functionality",
                        "2. Split file into smaller files with focused imports",
                        "3. Use lazy imports for optional dependencies",
                    ],
                    metrics=smell.metrics,
                ))

    def _suggest_from_clustering(self, result) -> None:
        """Generate suggestions from clustering analysis."""
        # Suggest moves for misclassified files
        for misclassified in result.misclassified:
            self.suggestions.append(RefactoringSuggestion(
                action="move",
                priority="low",
                impact="low",
                effort="low",
                target_files=[misclassified["name"]],
                description=f"Consider reorganizing {misclassified['name']}",
                rationale=f"This file is {misclassified['improvement']} to cluster "
                         f"{misclassified['suggested_cluster']} than its current cluster",
                steps=[
                    "1. Review the file's actual purpose",
                    "2. Compare with files in the suggested cluster",
                    "3. Move if it logically fits better there",
                ],
                metrics={
                    "current_cluster": misclassified["current_cluster"],
                    "suggested_cluster": misclassified["suggested_cluster"],
                    "improvement": misclassified["improvement"],
                },
            ))

        # Suggest merges for small clusters with similar files
        small_clusters = [c for c in result.clusters if c.size <= 2]
        for cluster in small_clusters:
            if cluster.size == 1:
                self.suggestions.append(RefactoringSuggestion(
                    action="merge",
                    priority="low",
                    impact="low",
                    effort="low",
                    target_files=[f["name"] for f in cluster.files],
                    description=f"Isolated file: {cluster.files[0]['name']}",
                    rationale="This file forms its own cluster - it may be an outlier "
                             "that should be merged with related code",
                    steps=[
                        "1. Review the file's functionality",
                        "2. Find the most similar existing file",
                        "3. Merge if functionality overlaps",
                    ],
                    metrics={"cluster_size": 1},
                ))

    def _suggest_from_graph(self) -> None:
        """Generate suggestions from graph analysis."""
        # Find critical bridges
        for node in self.graph.nodes.values():
            if node.betweenness > 0.15:
                self.suggestions.append(RefactoringSuggestion(
                    action="extract",
                    priority="medium",
                    impact="high",
                    effort="high",
                    target_files=[node.name],
                    description=f"Extract shared utilities from {node.name}",
                    rationale=f"This file is a critical bridge (betweenness: {node.betweenness:.2f}). "
                             "It connects many parts of the codebase.",
                    steps=[
                        "1. Identify what makes this file a bridge",
                        "2. Extract commonly used utilities to separate files",
                        "3. Reduce the file's centrality by distributing functionality",
                    ],
                    metrics={
                        "betweenness": node.betweenness,
                        "in_degree": node.in_degree,
                        "out_degree": node.out_degree,
                    },
                ))

    def _suggest_from_tensions(self) -> None:
        """Generate suggestions from active tensions."""
        from jig.engines.dcc.cube.tension import TensionDetector

        detector = TensionDetector(self.conn)
        tensions = detector.get_tensions(status="detected", limit=20)

        for tension in tensions:
            if tension.tension_percent > 0.25:
                self.suggestions.append(RefactoringSuggestion(
                    action="stabilize",
                    priority="high",
                    impact="high",
                    effort="medium",
                    target_files=[Path(tension.callee_path).name, Path(tension.caller_path).name],
                    description=f"Resolve tension between {Path(tension.callee_path).name} "
                               f"and {Path(tension.caller_path).name}",
                    rationale=f"Recent changes caused {tension.tension_percent:.0%} deviation "
                             f"from baseline distance",
                    steps=[
                        f"1. Review recent changes to {Path(tension.callee_path).name}",
                        f"2. Check if {Path(tension.caller_path).name} needs updates",
                        "3. Run tests to verify compatibility",
                        "4. Mark tension as resolved when fixed",
                    ],
                    metrics={
                        "tension_percent": tension.tension_percent,
                        "baseline_distance": tension.baseline_distance,
                        "current_distance": tension.current_distance,
                    },
                ))

    def _deduplicate(self) -> None:
        """Remove duplicate suggestions for the same file."""
        seen = set()
        unique = []

        for suggestion in self.suggestions:
            key = (suggestion.action, tuple(sorted(suggestion.target_files)))
            if key not in seen:
                seen.add(key)
                unique.append(suggestion)

        self.suggestions = unique

    def _prioritize(self) -> None:
        """Sort suggestions by priority."""
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        self.suggestions.sort(key=lambda s: (priority_order.get(s.priority, 4), s.action))


def get_refactoring_suggestions(conn: sqlite3.Connection) -> dict[str, Any]:
    """
    Get prioritized refactoring suggestions.

    Args:
        conn: Database connection.

    Returns:
        Dictionary with suggestions and summary.
    """
    advisor = RefactoringAdvisor(conn)
    suggestions = advisor.analyze()

    # Group by action type
    by_action: dict[str, list] = {}
    by_priority: dict[str, int] = {}

    for s in suggestions:
        by_action.setdefault(s.action, []).append(s.to_dict())
        by_priority[s.priority] = by_priority.get(s.priority, 0) + 1

    return {
        "total_suggestions": len(suggestions),
        "by_action": {k: len(v) for k, v in by_action.items()},
        "by_priority": by_priority,
        "suggestions": [s.to_dict() for s in suggestions],
    }
