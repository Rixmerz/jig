"""
CodePoint - Representation of code as a point in 3D feature space.

A CodePoint represents a code file (or function) as a vector in 86-dimensional space:
- Lexical features (65 dims): TF-IDF unigrams (50) + bigrams (15)
- Structural features (16 dims): Basic (8) + Halstead (5) + Coupling (3)
- Semantic features (5 dims): Domain classification (configurable)
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from jig.engines.dcc.cube.features import (
    extract_lexical_features,
    extract_semantic_features,
    extract_structural_features,
)
from jig.engines.dcc.cube.features.lexical import LEXICAL_DIMS
from jig.engines.dcc.cube.features.semantic import SEMANTIC_DIMS, get_dominant_domain
from jig.engines.dcc.cube.features.structural import STRUCTURAL_DIMS

# Total dimensions
TOTAL_DIMS = LEXICAL_DIMS + STRUCTURAL_DIMS + SEMANTIC_DIMS  # 65 + 16 + 5 = 86


@dataclass
class CodePoint:
    """
    Represents a code file as a point in 3D feature space.

    The position vector is 86 dimensions:
    - [0:65] Lexical features (unigrams + bigrams)
    - [65:81] Structural features (basic + Halstead + coupling)
    - [81:86] Semantic features (domain classification)
    """

    # Identification
    id: str
    file_path: str
    function_name: str | None = None

    # Feature vectors
    lexical: np.ndarray = field(default_factory=lambda: np.zeros(LEXICAL_DIMS))
    structural: np.ndarray = field(default_factory=lambda: np.zeros(STRUCTURAL_DIMS))
    semantic: np.ndarray = field(default_factory=lambda: np.zeros(SEMANTIC_DIMS))

    # Metadata
    content_hash: str = ""
    line_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    @property
    def position(self) -> np.ndarray:
        """
        Full position vector in 63-dimensional space.

        Returns:
            Concatenated feature vector [lexical, structural, semantic].
        """
        return np.concatenate([self.lexical, self.structural, self.semantic])

    @property
    def dominant_domain(self) -> str:
        """Get the dominant semantic domain."""
        return get_dominant_domain(self.semantic)

    def distance_to(self, other: "CodePoint", method: str = "cosine") -> float:
        """
        Calculate distance to another CodePoint.

        Args:
            other: Another CodePoint.
            method: Distance method - "cosine" (default, better for TF-IDF) or "euclidean".

        Returns:
            Distance between positions.
        """
        if method == "cosine":
            return self.cosine_distance_to(other)
        else:
            return self.euclidean_distance_to(other)

    @staticmethod
    def _normalize_vectors(v1: np.ndarray, v2: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Normalize two vectors to the same dimension by padding the shorter one."""
        if len(v1) == len(v2):
            return v1, v2
        max_len = max(len(v1), len(v2))
        if len(v1) < max_len:
            v1 = np.pad(v1, (0, max_len - len(v1)), mode='constant', constant_values=0)
        if len(v2) < max_len:
            v2 = np.pad(v2, (0, max_len - len(v2)), mode='constant', constant_values=0)
        return v1, v2

    def euclidean_distance_to(self, other: "CodePoint") -> float:
        """
        Calculate Euclidean distance to another CodePoint.

        Args:
            other: Another CodePoint.

        Returns:
            Euclidean distance between positions.
        """
        pos1, pos2 = self._normalize_vectors(self.position, other.position)
        return float(np.linalg.norm(pos1 - pos2))

    def cosine_distance_to(self, other: "CodePoint") -> float:
        """
        Calculate cosine distance to another CodePoint.

        Cosine distance = 1 - cosine similarity.
        Better for sparse vectors like TF-IDF.

        Args:
            other: Another CodePoint.

        Returns:
            Cosine distance (0 = identical, 2 = opposite).
        """
        similarity = self.similarity_to(other)
        return 1.0 - similarity

    def distance_in_axis(self, other: "CodePoint", axis: str, method: str = "cosine") -> float:
        """
        Calculate distance in a specific axis/dimension.

        Args:
            other: Another CodePoint.
            axis: One of 'lexical', 'structural', 'semantic'.
            method: Distance method - "cosine" (default) or "euclidean".

        Returns:
            Distance in specified dimensions only.
        """
        if axis == "lexical":
            v1, v2 = self.lexical, other.lexical
        elif axis == "structural":
            v1, v2 = self.structural, other.structural
        elif axis == "semantic":
            v1, v2 = self.semantic, other.semantic
        else:
            raise ValueError(f"Unknown axis: {axis}. Use 'lexical', 'structural', or 'semantic'.")

        # Normalize vectors to same dimension
        v1, v2 = self._normalize_vectors(v1, v2)

        if method == "cosine":
            return self._cosine_distance(v1, v2)
        else:
            return float(np.linalg.norm(v1 - v2))

    @staticmethod
    def _cosine_distance(v1: np.ndarray, v2: np.ndarray) -> float:
        """Calculate cosine distance between two vectors."""
        # Normalize to same dimension
        if len(v1) != len(v2):
            max_len = max(len(v1), len(v2))
            if len(v1) < max_len:
                v1 = np.pad(v1, (0, max_len - len(v1)), mode='constant', constant_values=0)
            if len(v2) < max_len:
                v2 = np.pad(v2, (0, max_len - len(v2)), mode='constant', constant_values=0)

        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)

        if norm1 == 0 or norm2 == 0:
            return 1.0  # Maximum distance if either vector is zero

        similarity = float(np.dot(v1, v2) / (norm1 * norm2))
        return 1.0 - similarity

    def similarity_to(self, other: "CodePoint") -> float:
        """
        Calculate cosine similarity to another CodePoint.

        Args:
            other: Another CodePoint.

        Returns:
            Cosine similarity (0 to 1, higher is more similar).
        """
        pos1, pos2 = self._normalize_vectors(self.position, other.position)
        norm1 = np.linalg.norm(pos1)
        norm2 = np.linalg.norm(pos2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(np.dot(pos1, pos2) / (norm1 * norm2))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "file_path": self.file_path,
            "function_name": self.function_name,
            "lexical": self.lexical.tolist(),
            "structural": self.structural.tolist(),
            "semantic": self.semantic.tolist(),
            "content_hash": self.content_hash,
            "line_count": self.line_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CodePoint":
        """Create CodePoint from dictionary."""
        return cls(
            id=data["id"],
            file_path=data["file_path"],
            function_name=data.get("function_name"),
            lexical=np.array(data["lexical"], dtype=np.float64),
            structural=np.array(data["structural"], dtype=np.float64),
            semantic=np.array(data["semantic"], dtype=np.float64),
            content_hash=data.get("content_hash", ""),
            line_count=data.get("line_count", 0),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if "updated_at" in data else datetime.now(),
        )

    def __repr__(self) -> str:
        return (
            f"CodePoint(id='{self.id}', "
            f"file='{Path(self.file_path).name}', "
            f"domain='{self.dominant_domain}')"
        )


def create_code_point(
    file_path: str,
    content: str | None = None,
    function_name: str | None = None,
) -> CodePoint:
    """
    Create a CodePoint from a file path or content.

    Args:
        file_path: Path to the code file.
        content: Optional content (reads from file if not provided).
        function_name: Optional function name if indexing a specific function.

    Returns:
        CodePoint with extracted features.
    """
    path = Path(file_path)

    # Read content if not provided
    if content is None:
        content = path.read_text(encoding="utf-8")

    # Generate ID
    point_id = _generate_id(file_path, function_name)

    # Calculate hash
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    # Get file extension
    extension = path.suffix

    # Extract features
    lexical = extract_lexical_features(content)
    structural = extract_structural_features(content, extension)
    semantic = extract_semantic_features(content)

    # Count lines
    line_count = content.count("\n") + 1

    return CodePoint(
        id=point_id,
        file_path=str(path.absolute()),
        function_name=function_name,
        lexical=lexical,
        structural=structural,
        semantic=semantic,
        content_hash=content_hash,
        line_count=line_count,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


def _generate_id(file_path: str, function_name: str | None = None) -> str:
    """Generate unique ID for a CodePoint."""
    base = file_path
    if function_name:
        base = f"{file_path}::{function_name}"

    # Create short hash
    return hashlib.md5(base.encode("utf-8")).hexdigest()[:12]
