"""
Delta - Tracks movement of CodePoints when code changes.

A Delta records the movement of a code file in the 63D feature space,
capturing what changed (lexical, structural, semantic) and by how much.
"""

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from jig.engines.dcc.cube.code_point import CodePoint, TOTAL_DIMS
from jig.engines.dcc.cube.features.lexical import LEXICAL_DIMS
from jig.engines.dcc.cube.features.structural import STRUCTURAL_DIMS
from jig.engines.dcc.cube.features.semantic import SEMANTIC_DIMS
from jig.engines.dcc.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Delta:
    """
    Records movement of a CodePoint in feature space.

    When a code file changes, a Delta captures:
    - Old and new positions in 63D space
    - Movement vector and magnitude
    - Breakdown by axis (lexical, structural, semantic)
    - Which axis changed the most (dominant_change)

    Attributes:
        id: Unique identifier for this delta.
        code_point_id: ID of the CodePoint that moved.
        file_path: Path to the file that changed.
        old_position: Previous position vector (63 dims).
        new_position: New position vector (63 dims).
        movement_magnitude: Total Euclidean distance moved.
        lexical_change: Movement in lexical dimensions (0-50).
        structural_change: Movement in structural dimensions (50-58).
        semantic_change: Movement in semantic dimensions (58-63).
        dominant_change: Which axis changed most ('lexical', 'structural', 'semantic').
        created_at: When the delta was detected.
    """

    id: str
    code_point_id: str
    file_path: str
    old_position: np.ndarray
    new_position: np.ndarray
    movement_magnitude: float
    lexical_change: float
    structural_change: float
    semantic_change: float
    dominant_change: str
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def movement(self) -> np.ndarray:
        """Movement vector (new - old)."""
        return self.new_position - self.old_position

    @property
    def is_significant(self) -> bool:
        """Check if the movement is significant (> 0.1)."""
        return self.movement_magnitude > 0.1

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "code_point_id": self.code_point_id,
            "file_path": self.file_path,
            "file_name": Path(self.file_path).name,
            "old_position": self.old_position.tolist(),
            "new_position": self.new_position.tolist(),
            "movement_magnitude": self.movement_magnitude,
            "lexical_change": self.lexical_change,
            "structural_change": self.structural_change,
            "semantic_change": self.semantic_change,
            "dominant_change": self.dominant_change,
            "is_significant": self.is_significant,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Delta":
        """Create Delta from dictionary."""
        return cls(
            id=data["id"],
            code_point_id=data["code_point_id"],
            file_path=data["file_path"],
            old_position=np.array(data["old_position"], dtype=np.float64),
            new_position=np.array(data["new_position"], dtype=np.float64),
            movement_magnitude=data["movement_magnitude"],
            lexical_change=data["lexical_change"],
            structural_change=data["structural_change"],
            semantic_change=data["semantic_change"],
            dominant_change=data["dominant_change"],
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if "created_at" in data
                else datetime.now()
            ),
        )

    def __repr__(self) -> str:
        return (
            f"Delta({Path(self.file_path).name}, "
            f"magnitude={self.movement_magnitude:.3f}, "
            f"dominant={self.dominant_change})"
        )


def create_delta(
    old_code_point: CodePoint,
    new_code_point: CodePoint,
) -> Delta:
    """
    Create a Delta from old and new CodePoints.

    Args:
        old_code_point: CodePoint before changes.
        new_code_point: CodePoint after changes.

    Returns:
        Delta capturing the movement.
    """
    old_pos = old_code_point.position
    new_pos = new_code_point.position

    # Calculate movement magnitude
    movement_magnitude = float(np.linalg.norm(new_pos - old_pos))

    # Calculate change per axis
    lexical_change = float(np.linalg.norm(
        new_pos[:LEXICAL_DIMS] - old_pos[:LEXICAL_DIMS]
    ))
    structural_change = float(np.linalg.norm(
        new_pos[LEXICAL_DIMS:LEXICAL_DIMS + STRUCTURAL_DIMS] -
        old_pos[LEXICAL_DIMS:LEXICAL_DIMS + STRUCTURAL_DIMS]
    ))
    semantic_change = float(np.linalg.norm(
        new_pos[LEXICAL_DIMS + STRUCTURAL_DIMS:] -
        old_pos[LEXICAL_DIMS + STRUCTURAL_DIMS:]
    ))

    # Determine dominant change
    changes = {
        "lexical": lexical_change,
        "structural": structural_change,
        "semantic": semantic_change,
    }
    dominant_change = max(changes, key=changes.get)

    # Generate ID
    delta_id = _generate_delta_id(old_code_point.id, new_code_point.updated_at)

    return Delta(
        id=delta_id,
        code_point_id=new_code_point.id,
        file_path=new_code_point.file_path,
        old_position=old_pos,
        new_position=new_pos,
        movement_magnitude=movement_magnitude,
        lexical_change=lexical_change,
        structural_change=structural_change,
        semantic_change=semantic_change,
        dominant_change=dominant_change,
        created_at=datetime.now(),
    )


def _generate_delta_id(code_point_id: str, timestamp: datetime) -> str:
    """Generate unique ID for a delta."""
    combined = f"{code_point_id}:{timestamp.isoformat()}"
    return hashlib.md5(combined.encode("utf-8")).hexdigest()[:12]


class DeltaTracker:
    """
    Tracks and persists deltas in the database.
    """

    def __init__(self, conn: sqlite3.Connection):
        """
        Initialize DeltaTracker with database connection.

        Args:
            conn: SQLite connection (should have dict_factory row_factory).
        """
        self.conn = conn

    def save_delta(self, delta: Delta) -> None:
        """Save a delta to the database."""
        self.conn.execute(
            """
            INSERT INTO deltas (
                id, code_point_id, old_position, new_position,
                movement_magnitude, lexical_change, structural_change,
                semantic_change, dominant_change, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                delta.id,
                delta.code_point_id,
                json.dumps(delta.old_position.tolist()),
                json.dumps(delta.new_position.tolist()),
                delta.movement_magnitude,
                delta.lexical_change,
                delta.structural_change,
                delta.semantic_change,
                delta.dominant_change,
                delta.created_at.isoformat(),
            ),
        )
        self.conn.commit()
        logger.info(f"Saved delta: {delta}")

    def get_deltas_for_file(
        self,
        code_point_id: str,
        limit: int = 10,
    ) -> list[Delta]:
        """Get recent deltas for a code point."""
        cursor = self.conn.execute(
            """
            SELECT d.*, cp.file_path
            FROM deltas d
            JOIN code_points cp ON d.code_point_id = cp.id
            WHERE d.code_point_id = ?
            ORDER BY d.created_at DESC
            LIMIT ?
            """,
            (code_point_id, limit),
        )
        return [self._row_to_delta(row) for row in cursor.fetchall()]

    def get_recent_deltas(self, limit: int = 20) -> list[Delta]:
        """Get most recent deltas across all files."""
        cursor = self.conn.execute(
            """
            SELECT d.*, cp.file_path
            FROM deltas d
            JOIN code_points cp ON d.code_point_id = cp.id
            ORDER BY d.created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [self._row_to_delta(row) for row in cursor.fetchall()]

    def get_significant_deltas(self, threshold: float = 0.1, limit: int = 20) -> list[Delta]:
        """Get deltas with movement above threshold."""
        cursor = self.conn.execute(
            """
            SELECT d.*, cp.file_path
            FROM deltas d
            JOIN code_points cp ON d.code_point_id = cp.id
            WHERE d.movement_magnitude > ?
            ORDER BY d.movement_magnitude DESC
            LIMIT ?
            """,
            (threshold, limit),
        )
        return [self._row_to_delta(row) for row in cursor.fetchall()]

    def _row_to_delta(self, row: dict[str, Any]) -> Delta:
        """Convert database row to Delta."""
        return Delta(
            id=row["id"],
            code_point_id=row["code_point_id"],
            file_path=row["file_path"],
            old_position=np.array(json.loads(row["old_position"]), dtype=np.float64),
            new_position=np.array(json.loads(row["new_position"]), dtype=np.float64),
            movement_magnitude=row["movement_magnitude"],
            lexical_change=row["lexical_change"],
            structural_change=row["structural_change"],
            semantic_change=row["semantic_change"],
            dominant_change=row["dominant_change"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
