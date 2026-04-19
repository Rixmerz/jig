"""
Tension - Detects when code changes break contract expectations.

A Tension is created when a code file changes and its distance to dependent
files deviates significantly from the baseline_distance recorded in contracts.
This indicates that the change may have broken implicit dependencies.

Features adaptive thresholds based on historical change patterns per file.
"""

import hashlib
import json
import sqlite3
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from jig.engines.dcc.cube.code_point import CodePoint
from jig.engines.dcc.cube.contracts import Contract
from jig.engines.dcc.cube.delta import Delta
from jig.engines.dcc.utils.logger import get_logger

logger = get_logger(__name__)

# Default threshold for tension detection (relative change from baseline)
DEFAULT_TENSION_THRESHOLD = 0.15  # 15% change from baseline

# Minimum samples required for adaptive threshold
MIN_SAMPLES_FOR_ADAPTIVE = 3

# Number of standard deviations for adaptive threshold
ADAPTIVE_STDEV_MULTIPLIER = 2.0


@dataclass
class Tension:
    """
    Represents a detected tension (potential contract violation).

    When a file changes, if the new distance to its dependents differs
    significantly from the baseline, a Tension is created.

    Attributes:
        id: Unique identifier for this tension.
        contract_id: ID of the affected Contract.
        delta_id: ID of the Delta that caused this tension.
        caller_path: Path to the file that depends on the changed file.
        callee_path: Path to the file that changed.
        baseline_distance: Original "healthy" distance.
        current_distance: Distance after the change.
        tension_magnitude: Absolute difference (current - baseline).
        tension_percent: Percentage change from baseline.
        status: 'detected', 'reviewed', 'resolved', 'ignored'.
        suggested_action: Recommendation for the developer.
        created_at: When the tension was detected.
        resolved_at: When the tension was resolved (if applicable).
    """

    id: str
    contract_id: str
    delta_id: str
    caller_path: str
    callee_path: str
    baseline_distance: float
    current_distance: float
    tension_magnitude: float
    tension_percent: float
    status: str = "detected"
    suggested_action: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    resolved_at: datetime | None = None

    @property
    def is_high(self) -> bool:
        """Check if tension is high (> 25% change)."""
        return self.tension_percent > 0.25

    @property
    def is_medium(self) -> bool:
        """Check if tension is medium (15-25% change)."""
        return 0.15 <= self.tension_percent <= 0.25

    @property
    def severity(self) -> str:
        """Get tension severity level."""
        if self.tension_percent > 0.25:
            return "high"
        elif self.tension_percent > 0.15:
            return "medium"
        else:
            return "low"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "contract_id": self.contract_id,
            "delta_id": self.delta_id,
            "caller_path": self.caller_path,
            "callee_path": self.callee_path,
            "caller_name": Path(self.caller_path).name,
            "callee_name": Path(self.callee_path).name,
            "baseline_distance": self.baseline_distance,
            "current_distance": self.current_distance,
            "tension_magnitude": self.tension_magnitude,
            "tension_percent": self.tension_percent,
            "severity": self.severity,
            "status": self.status,
            "suggested_action": self.suggested_action,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Tension":
        """Create Tension from dictionary."""
        return cls(
            id=data["id"],
            contract_id=data["contract_id"],
            delta_id=data["delta_id"],
            caller_path=data["caller_path"],
            callee_path=data["callee_path"],
            baseline_distance=data["baseline_distance"],
            current_distance=data["current_distance"],
            tension_magnitude=data["tension_magnitude"],
            tension_percent=data["tension_percent"],
            status=data.get("status", "detected"),
            suggested_action=data.get("suggested_action"),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if "created_at" in data
                else datetime.now()
            ),
            resolved_at=(
                datetime.fromisoformat(data["resolved_at"])
                if data.get("resolved_at")
                else None
            ),
        )

    def __repr__(self) -> str:
        caller_name = Path(self.caller_path).name
        callee_name = Path(self.callee_path).name
        return (
            f"Tension({caller_name} ← {callee_name}, "
            f"{self.tension_percent:.1%}, {self.severity})"
        )


class TensionDetector:
    """
    Detects and manages tensions when code changes.

    Features adaptive thresholds that learn from historical change patterns.
    If a file typically has small changes, the threshold is lower.
    If a file frequently has larger changes, the threshold adjusts accordingly.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        threshold: float = DEFAULT_TENSION_THRESHOLD,
        use_adaptive: bool = True,
    ):
        """
        Initialize TensionDetector.

        Args:
            conn: SQLite connection (should have dict_factory row_factory).
            threshold: Default minimum relative change to trigger tension (15%).
            use_adaptive: Whether to use adaptive thresholds based on history.
        """
        self.conn = conn
        self.default_threshold = threshold
        self.use_adaptive = use_adaptive

    def get_adaptive_threshold(self, code_point_id: str) -> float:
        """
        Calculate adaptive threshold based on file's change history.

        Uses the mean + 2*stdev of past tension percentages for this file.
        Falls back to default threshold if insufficient history.

        Args:
            code_point_id: ID of the code point to get threshold for.

        Returns:
            Adaptive threshold (or default if insufficient data).
        """
        if not self.use_adaptive:
            return self.default_threshold

        # Get historical deltas for this file
        cursor = self.conn.execute(
            """
            SELECT movement_magnitude
            FROM deltas
            WHERE code_point_id = ?
            ORDER BY created_at DESC
            LIMIT 20
            """,
            (code_point_id,),
        )

        magnitudes = [row["movement_magnitude"] for row in cursor.fetchall()]

        # Need minimum samples for adaptive
        if len(magnitudes) < MIN_SAMPLES_FOR_ADAPTIVE:
            return self.default_threshold

        try:
            mean = statistics.mean(magnitudes)
            stdev = statistics.stdev(magnitudes) if len(magnitudes) > 1 else 0

            # Adaptive threshold = mean + 2 standard deviations
            adaptive = mean + (ADAPTIVE_STDEV_MULTIPLIER * stdev)

            # Clamp to reasonable range (5% to 50%)
            adaptive = max(0.05, min(0.50, adaptive))

            logger.debug(
                f"Adaptive threshold for {code_point_id}: {adaptive:.2%} "
                f"(mean={mean:.2%}, stdev={stdev:.2%}, samples={len(magnitudes)})"
            )

            return adaptive

        except statistics.StatisticsError:
            return self.default_threshold

    def detect_tensions(
        self,
        delta: Delta,
        new_code_point: CodePoint,
        code_points: dict[str, CodePoint],
    ) -> list[Tension]:
        """
        Detect tensions caused by a code change.

        Finds all contracts where the changed file is the callee (dependency),
        calculates the new distance to each caller, and creates Tensions
        if the change exceeds the threshold.

        Args:
            delta: The Delta recording the movement.
            new_code_point: The updated CodePoint.
            code_points: Dictionary of all CodePoints {id: CodePoint}.

        Returns:
            List of detected Tensions.
        """
        tensions = []

        # Get all contracts where this file is the callee (incoming dependencies)
        cursor = self.conn.execute(
            """
            SELECT c.*, cp1.file_path as caller_path, cp2.file_path as callee_path
            FROM contracts c
            JOIN code_points cp1 ON c.caller_id = cp1.id
            JOIN code_points cp2 ON c.callee_id = cp2.id
            WHERE c.callee_id = ?
            """,
            (new_code_point.id,),
        )

        for row in cursor.fetchall():
            caller_id = row["caller_id"]
            baseline_distance = row["baseline_distance"]

            # Get caller CodePoint
            caller_cp = code_points.get(caller_id)
            if not caller_cp:
                # Try to load from database
                caller_cp = self._load_code_point(caller_id)
                if not caller_cp:
                    continue

            # Calculate new distance
            current_distance = caller_cp.distance_to(new_code_point)

            # Calculate tension
            tension_magnitude = abs(current_distance - baseline_distance)

            # Avoid division by zero
            if baseline_distance > 0:
                tension_percent = tension_magnitude / baseline_distance
            else:
                tension_percent = tension_magnitude

            # Get adaptive threshold for this file
            threshold = self.get_adaptive_threshold(new_code_point.id)

            # Check if exceeds threshold
            if tension_percent >= threshold:
                tension = Tension(
                    id=_generate_tension_id(row["id"], delta.id),
                    contract_id=row["id"],
                    delta_id=delta.id,
                    caller_path=row["caller_path"],
                    callee_path=row["callee_path"],
                    baseline_distance=baseline_distance,
                    current_distance=current_distance,
                    tension_magnitude=tension_magnitude,
                    tension_percent=tension_percent,
                    status="detected",
                    suggested_action=self._generate_suggestion(
                        delta, tension_percent, row["caller_path"]
                    ),
                    created_at=datetime.now(),
                )
                tensions.append(tension)
                logger.info(f"Detected tension: {tension}")

        return tensions

    def _generate_suggestion(
        self,
        delta: Delta,
        tension_percent: float,
        caller_path: str,
    ) -> str:
        """Generate a suggested action for the developer."""
        caller_name = Path(caller_path).name
        changed_name = Path(delta.file_path).name

        if delta.dominant_change == "structural":
            return (
                f"Review {caller_name}: {changed_name} had structural changes "
                f"(+{tension_percent:.0%}). Check function signatures and exports."
            )
        elif delta.dominant_change == "semantic":
            return (
                f"Review {caller_name}: {changed_name} changed domain/purpose "
                f"(+{tension_percent:.0%}). Verify it still serves its original role."
            )
        else:  # lexical
            return (
                f"Review {caller_name}: {changed_name} had terminology changes "
                f"(+{tension_percent:.0%}). Check variable/function names."
            )

    def _load_code_point(self, code_point_id: str) -> CodePoint | None:
        """Load a CodePoint from database."""
        cursor = self.conn.execute(
            "SELECT * FROM code_points WHERE id = ?",
            (code_point_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        from jig.engines.dcc.cube.code_point import CodePoint
        return CodePoint(
            id=row["id"],
            file_path=row["file_path"],
            function_name=row.get("function_name"),
            lexical=np.array(json.loads(row["lexical_features"]), dtype=np.float64),
            structural=np.array(json.loads(row["structural_features"]), dtype=np.float64),
            semantic=np.array(json.loads(row["semantic_features"]), dtype=np.float64),
            content_hash=row["content_hash"],
            line_count=row["line_count"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def save_tension(self, tension: Tension) -> None:
        """Save a tension to the database."""
        self.conn.execute(
            """
            INSERT INTO tensions (
                id, contract_id, delta_id, tension_magnitude,
                status, suggested_action, created_at, resolved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tension.id,
                tension.contract_id,
                tension.delta_id,
                tension.tension_magnitude,
                tension.status,
                tension.suggested_action,
                tension.created_at.isoformat(),
                tension.resolved_at.isoformat() if tension.resolved_at else None,
            ),
        )
        self.conn.commit()

    def save_tensions(self, tensions: list[Tension]) -> int:
        """Save multiple tensions to database."""
        saved = 0
        for tension in tensions:
            try:
                self.save_tension(tension)
                saved += 1
            except Exception as e:
                logger.warning(f"Failed to save tension {tension.id}: {e}")
        return saved

    def get_tensions(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Tension]:
        """
        Get tensions, optionally filtered by status.

        Args:
            status: Filter by status ('detected', 'reviewed', 'resolved', 'ignored').
            limit: Maximum results.

        Returns:
            List of Tensions.
        """
        if status:
            cursor = self.conn.execute(
                """
                SELECT t.*, c.caller_id, c.callee_id, c.baseline_distance,
                       cp1.file_path as caller_path, cp2.file_path as callee_path
                FROM tensions t
                JOIN contracts c ON t.contract_id = c.id
                JOIN code_points cp1 ON c.caller_id = cp1.id
                JOIN code_points cp2 ON c.callee_id = cp2.id
                WHERE t.status = ?
                ORDER BY t.tension_magnitude DESC
                LIMIT ?
                """,
                (status, limit),
            )
        else:
            cursor = self.conn.execute(
                """
                SELECT t.*, c.caller_id, c.callee_id, c.baseline_distance,
                       cp1.file_path as caller_path, cp2.file_path as callee_path
                FROM tensions t
                JOIN contracts c ON t.contract_id = c.id
                JOIN code_points cp1 ON c.caller_id = cp1.id
                JOIN code_points cp2 ON c.callee_id = cp2.id
                ORDER BY t.created_at DESC
                LIMIT ?
                """,
                (limit,),
            )

        tensions = []
        for row in cursor.fetchall():
            # Calculate current_distance and tension_percent from stored data
            tension_magnitude = row["tension_magnitude"]
            baseline_distance = row["baseline_distance"]
            current_distance = baseline_distance + tension_magnitude  # Approximation

            if baseline_distance > 0:
                tension_percent = tension_magnitude / baseline_distance
            else:
                tension_percent = tension_magnitude

            tensions.append(Tension(
                id=row["id"],
                contract_id=row["contract_id"],
                delta_id=row["delta_id"],
                caller_path=row["caller_path"],
                callee_path=row["callee_path"],
                baseline_distance=baseline_distance,
                current_distance=current_distance,
                tension_magnitude=tension_magnitude,
                tension_percent=tension_percent,
                status=row["status"],
                suggested_action=row.get("suggested_action"),
                created_at=datetime.fromisoformat(row["created_at"]),
                resolved_at=(
                    datetime.fromisoformat(row["resolved_at"])
                    if row.get("resolved_at")
                    else None
                ),
            ))

        return tensions

    def update_tension_status(
        self,
        tension_id: str,
        status: str,
    ) -> bool:
        """
        Update the status of a tension.

        Args:
            tension_id: ID of the tension to update.
            status: New status ('reviewed', 'resolved', 'ignored').

        Returns:
            True if updated, False if not found.
        """
        resolved_at = datetime.now().isoformat() if status == "resolved" else None

        cursor = self.conn.execute(
            """
            UPDATE tensions
            SET status = ?, resolved_at = ?
            WHERE id = ?
            """,
            (status, resolved_at, tension_id),
        )
        self.conn.commit()

        return cursor.rowcount > 0

    def get_tension_stats(self) -> dict[str, Any]:
        """Get statistics about tensions."""
        cursor = self.conn.execute("SELECT COUNT(*) as count FROM tensions")
        total = cursor.fetchone()["count"]

        cursor = self.conn.execute(
            """
            SELECT status, COUNT(*) as count
            FROM tensions
            GROUP BY status
            """
        )
        by_status = {row["status"]: row["count"] for row in cursor.fetchall()}

        cursor = self.conn.execute(
            """
            SELECT AVG(tension_magnitude) as avg_mag,
                   MAX(tension_magnitude) as max_mag
            FROM tensions
            WHERE status = 'detected'
            """
        )
        row = cursor.fetchone()

        return {
            "total_tensions": total,
            "by_status": by_status,
            "avg_tension_magnitude": row["avg_mag"] or 0,
            "max_tension_magnitude": row["max_mag"] or 0,
        }


def _generate_tension_id(contract_id: str, delta_id: str) -> str:
    """Generate unique ID for a tension."""
    combined = f"{contract_id}:{delta_id}"
    return hashlib.md5(combined.encode("utf-8")).hexdigest()[:12]
