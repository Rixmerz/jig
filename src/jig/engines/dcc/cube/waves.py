"""
Tension Waves for DeltaCodeCube.

A novel algorithm that simulates how changes propagate through the dependency graph.
When a file changes, the "wave" of potential impact travels through its dependents,
attenuating based on distance and coupling strength.

Features:
1. Predict which files will be affected by a change
2. Estimate the "ripple effect" magnitude
3. Identify natural boundaries where waves stop
4. Prioritize code review order based on wave intensity
"""

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from jig.engines.dcc.cube.graph import DependencyGraph
from jig.engines.dcc.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class WaveNode:
    """A node in the wave propagation."""
    file_path: str
    file_name: str
    wave_intensity: float  # 0.0 to 1.0
    distance_from_source: int
    reached_via: list[str]  # Path of propagation
    is_boundary: bool = False  # Wave stopped here

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "file_path": self.file_path,
            "file_name": self.file_name,
            "wave_intensity": round(self.wave_intensity, 4),
            "distance_from_source": self.distance_from_source,
            "reached_via": self.reached_via,
            "is_boundary": self.is_boundary,
        }


@dataclass
class WaveSimulation:
    """Results of a wave simulation."""
    source_file: str
    initial_intensity: float
    affected_files: list[WaveNode]
    total_affected: int
    max_depth: int
    boundaries: list[str]
    review_order: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "source_file": self.source_file,
            "initial_intensity": self.initial_intensity,
            "total_affected": self.total_affected,
            "max_depth": self.max_depth,
            "boundaries_count": len(self.boundaries),
            "boundaries": self.boundaries,
            "review_order": self.review_order,
            "affected_files": [f.to_dict() for f in self.affected_files],
        }


class TensionWaveSimulator:
    """
    Simulates how changes propagate through the codebase.

    The algorithm:
    1. Start at the source file with intensity 1.0
    2. Propagate to dependents (files that import the source)
    3. Intensity attenuates based on:
       - Distance (farther = weaker)
       - Coupling (weaker coupling = faster attenuation)
       - Domain similarity (different domain = boundary)
    4. Stop when intensity falls below threshold
    5. Mark natural boundaries (domain changes, isolated files)
    """

    DEFAULT_ATTENUATION = 0.6  # Intensity multiplier per hop
    INTENSITY_THRESHOLD = 0.05  # Stop propagation below this
    DOMAIN_CHANGE_PENALTY = 0.5  # Extra attenuation for domain change

    def __init__(self, conn: sqlite3.Connection):
        """Initialize with database connection."""
        self.conn = conn
        self.graph = DependencyGraph(conn)
        self.graph.build_graph()

    def simulate_wave(
        self,
        source_path: str,
        initial_intensity: float = 1.0,
        attenuation: float | None = None,
    ) -> WaveSimulation:
        """
        Simulate a tension wave starting from a source file.

        Args:
            source_path: Path to the file that changed.
            initial_intensity: Starting intensity (0.0-1.0).
            attenuation: Custom attenuation factor per hop.

        Returns:
            WaveSimulation with all affected files.
        """
        attenuation = attenuation or self.DEFAULT_ATTENUATION

        # Find source node
        source_node = None
        for node in self.graph.nodes.values():
            if node.file_path == source_path or node.file_path.endswith(source_path):
                source_node = node
                break

        if not source_node:
            return WaveSimulation(
                source_file=source_path,
                initial_intensity=initial_intensity,
                affected_files=[],
                total_affected=0,
                max_depth=0,
                boundaries=[],
                review_order=[],
            )

        # BFS propagation with attenuation
        affected: dict[str, WaveNode] = {}
        boundaries = []
        queue = [(source_node.id, initial_intensity, 0, [source_node.name])]
        visited = {source_node.id}

        while queue:
            current_id, intensity, distance, path = queue.pop(0)
            current_node = self.graph.nodes[current_id]

            # Skip source in affected (we already know it changed)
            if distance > 0:
                affected[current_id] = WaveNode(
                    file_path=current_node.file_path,
                    file_name=current_node.name,
                    wave_intensity=intensity,
                    distance_from_source=distance,
                    reached_via=path,
                    is_boundary=False,
                )

            # Get dependents (files that import this file)
            dependents = self.graph.reverse_adjacency.get(current_id, set())

            if not dependents and distance > 0:
                # This is a boundary - no further propagation
                affected[current_id].is_boundary = True
                boundaries.append(current_node.name)
                continue

            for dep_id in dependents:
                if dep_id in visited:
                    continue

                dep_node = self.graph.nodes[dep_id]
                visited.add(dep_id)

                # Calculate new intensity with attenuation
                new_intensity = intensity * attenuation

                # Apply domain change penalty
                if dep_node.domain != current_node.domain:
                    new_intensity *= self.DOMAIN_CHANGE_PENALTY

                # Stop if below threshold
                if new_intensity < self.INTENSITY_THRESHOLD:
                    affected[dep_id] = WaveNode(
                        file_path=dep_node.file_path,
                        file_name=dep_node.name,
                        wave_intensity=new_intensity,
                        distance_from_source=distance + 1,
                        reached_via=path + [dep_node.name],
                        is_boundary=True,
                    )
                    boundaries.append(dep_node.name)
                    continue

                queue.append((
                    dep_id,
                    new_intensity,
                    distance + 1,
                    path + [dep_node.name],
                ))

        # Sort affected by intensity (highest first = review first)
        affected_list = sorted(
            affected.values(),
            key=lambda x: x.wave_intensity,
            reverse=True,
        )

        # Generate review order
        review_order = [
            {
                "priority": i + 1,
                "file": f.file_name,
                "intensity": round(f.wave_intensity, 2),
                "distance": f.distance_from_source,
            }
            for i, f in enumerate(affected_list)
            if f.wave_intensity >= self.INTENSITY_THRESHOLD
        ]

        max_depth = max((f.distance_from_source for f in affected_list), default=0)

        return WaveSimulation(
            source_file=source_node.name,
            initial_intensity=initial_intensity,
            affected_files=affected_list,
            total_affected=len(affected_list),
            max_depth=max_depth,
            boundaries=boundaries,
            review_order=review_order,
        )

    def simulate_multi_wave(
        self,
        source_paths: list[str],
        initial_intensity: float = 1.0,
    ) -> dict[str, Any]:
        """
        Simulate waves from multiple source files.

        Useful when multiple files change at once (e.g., a PR).
        Combines waves and identifies common affected files.

        Args:
            source_paths: List of changed file paths.
            initial_intensity: Starting intensity for each source.

        Returns:
            Combined wave analysis.
        """
        all_waves = []
        combined_intensity: dict[str, float] = {}
        combined_distance: dict[str, int] = {}

        for path in source_paths:
            wave = self.simulate_wave(path, initial_intensity)
            all_waves.append(wave)

            for affected in wave.affected_files:
                file_path = affected.file_path
                # Use maximum intensity from any wave
                if file_path not in combined_intensity or affected.wave_intensity > combined_intensity[file_path]:
                    combined_intensity[file_path] = affected.wave_intensity
                # Use minimum distance
                if file_path not in combined_distance or affected.distance_from_source < combined_distance[file_path]:
                    combined_distance[file_path] = affected.distance_from_source

        # Sort by combined intensity
        sorted_files = sorted(
            combined_intensity.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        return {
            "source_files": source_paths,
            "individual_waves": [w.to_dict() for w in all_waves],
            "total_unique_affected": len(combined_intensity),
            "combined_review_order": [
                {
                    "priority": i + 1,
                    "file": Path(path).name,
                    "max_intensity": round(intensity, 2),
                    "min_distance": combined_distance.get(path, 0),
                }
                for i, (path, intensity) in enumerate(sorted_files)
            ],
        }

    def predict_impact(self, file_path: str) -> dict[str, Any]:
        """
        Predict the impact of changing a file.

        Returns:
            Impact prediction with risk assessment.
        """
        wave = self.simulate_wave(file_path)

        # Calculate risk metrics
        high_intensity_count = sum(1 for f in wave.affected_files if f.wave_intensity > 0.5)
        medium_intensity_count = sum(1 for f in wave.affected_files if 0.2 < f.wave_intensity <= 0.5)

        # Determine risk level
        if high_intensity_count > 5 or wave.total_affected > 10:
            risk_level = "high"
            recommendation = "Consider splitting this change into smaller PRs"
        elif high_intensity_count > 2 or wave.total_affected > 5:
            risk_level = "medium"
            recommendation = "Request additional code review for affected files"
        else:
            risk_level = "low"
            recommendation = "Standard review process should suffice"

        return {
            "file": wave.source_file,
            "risk_level": risk_level,
            "total_affected": wave.total_affected,
            "high_impact_files": high_intensity_count,
            "medium_impact_files": medium_intensity_count,
            "max_propagation_depth": wave.max_depth,
            "natural_boundaries": wave.boundaries,
            "recommendation": recommendation,
            "review_order": wave.review_order[:10],  # Top 10
        }


def simulate_tension_wave(
    conn: sqlite3.Connection,
    source_path: str,
    initial_intensity: float = 1.0,
) -> dict[str, Any]:
    """
    Convenience function to simulate a tension wave.

    Args:
        conn: Database connection.
        source_path: Path to the source file.
        initial_intensity: Starting intensity.

    Returns:
        Wave simulation results.
    """
    simulator = TensionWaveSimulator(conn)
    wave = simulator.simulate_wave(source_path, initial_intensity)
    return wave.to_dict()


def predict_change_impact(conn: sqlite3.Connection, file_path: str) -> dict[str, Any]:
    """
    Predict the impact of changing a file.

    Args:
        conn: Database connection.
        file_path: Path to the file.

    Returns:
        Impact prediction.
    """
    simulator = TensionWaveSimulator(conn)
    return simulator.predict_impact(file_path)
