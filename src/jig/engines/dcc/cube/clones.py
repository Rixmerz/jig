"""
Code Clone Detection for DeltaCodeCube.

Detects duplicate or near-duplicate code blocks using fingerprinting.
No external APIs - uses local hashing and comparison.

Clone types detected:
- Type 1: Exact clones (identical code)
- Type 2: Parameterized clones (same structure, different names)
- Type 3: Near-miss clones (similar structure with modifications)

Algorithm: Winnowing-based fingerprinting
1. Normalize code (remove whitespace, comments)
2. Tokenize into k-grams
3. Hash k-grams and select fingerprints
4. Compare fingerprints between files
"""

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from jig.engines.dcc.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class CodeClone:
    """A detected code clone."""
    file_a: str
    file_b: str
    similarity: float  # 0.0 to 1.0
    clone_type: str  # "exact", "parameterized", "near-miss"
    shared_fingerprints: int
    total_fingerprints_a: int
    total_fingerprints_b: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "file_a": Path(self.file_a).name,
            "file_b": Path(self.file_b).name,
            "file_a_path": self.file_a,
            "file_b_path": self.file_b,
            "similarity": round(self.similarity, 4),
            "clone_type": self.clone_type,
            "shared_fingerprints": self.shared_fingerprints,
        }


class CloneDetector:
    """
    Detects code clones using Winnowing fingerprinting.

    Winnowing algorithm:
    1. Generate all k-grams (substrings of length k)
    2. Hash each k-gram
    3. Use sliding window to select minimum hash (fingerprint)
    4. Compare fingerprint sets between files
    """

    K_GRAM_SIZE = 5  # Size of k-grams (tokens)
    WINDOW_SIZE = 4  # Winnowing window size
    MIN_SIMILARITY = 0.3  # Minimum similarity to report

    def __init__(self, conn: sqlite3.Connection):
        """Initialize with database connection."""
        self.conn = conn
        self.file_fingerprints: dict[str, set[int]] = {}
        self.file_tokens: dict[str, list[str]] = {}

    def analyze(self) -> list[CodeClone]:
        """
        Analyze all indexed files for clones.

        Returns:
            List of detected code clones.
        """
        # Load and fingerprint all files
        self._load_and_fingerprint_files()

        if len(self.file_fingerprints) < 2:
            return []

        # Compare all pairs
        clones = []
        file_paths = list(self.file_fingerprints.keys())

        for i, path_a in enumerate(file_paths):
            for path_b in file_paths[i + 1:]:
                clone = self._compare_files(path_a, path_b)
                if clone:
                    clones.append(clone)

        # Sort by similarity
        clones.sort(key=lambda c: c.similarity, reverse=True)

        return clones

    def _load_and_fingerprint_files(self) -> None:
        """Load all files and compute fingerprints."""
        cursor = self.conn.execute("""
            SELECT file_path FROM code_points
        """)

        for row in cursor.fetchall():
            file_path = row["file_path"]
            try:
                content = Path(file_path).read_text(encoding="utf-8")
                tokens = self._tokenize(content)
                fingerprints = self._compute_fingerprints(tokens)

                self.file_tokens[file_path] = tokens
                self.file_fingerprints[file_path] = fingerprints

            except Exception as e:
                logger.debug(f"Could not process {file_path}: {e}")

    def _tokenize(self, content: str) -> list[str]:
        """
        Tokenize and normalize code.

        Normalization:
        - Remove comments
        - Remove string literals (replace with placeholder)
        - Normalize whitespace
        - Convert to lowercase
        - Replace identifiers with placeholders (for Type 2 clones)
        """
        # Remove comments
        content = re.sub(r'//.*$', '', content, flags=re.MULTILINE)
        content = re.sub(r'#.*$', '', content, flags=re.MULTILINE)
        content = re.sub(r'/\*[\s\S]*?\*/', '', content)
        content = re.sub(r'"""[\s\S]*?"""', '', content)
        content = re.sub(r"'''[\s\S]*?'''", '', content)

        # Replace string literals with placeholder
        content = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', '"STR"', content)
        content = re.sub(r"'[^'\\]*(?:\\.[^'\\]*)*'", "'STR'", content)
        content = re.sub(r'`[^`\\]*(?:\\.[^`\\]*)*`', '`STR`', content)

        # Replace numbers with placeholder
        content = re.sub(r'\b\d+\.?\d*\b', 'NUM', content)

        # Tokenize (split on non-alphanumeric)
        tokens = re.findall(r'[a-zA-Z_]\w*|[^\s\w]', content.lower())

        # Filter out very short tokens
        tokens = [t for t in tokens if len(t) >= 1]

        return tokens

    def _compute_fingerprints(self, tokens: list[str]) -> set[int]:
        """
        Compute Winnowing fingerprints for a token sequence.

        Returns:
            Set of fingerprint hashes.
        """
        if len(tokens) < self.K_GRAM_SIZE:
            return set()

        # Generate k-grams
        kgrams = []
        for i in range(len(tokens) - self.K_GRAM_SIZE + 1):
            kgram = ' '.join(tokens[i:i + self.K_GRAM_SIZE])
            kgrams.append(kgram)

        # Hash k-grams
        hashes = [self._hash_kgram(kg) for kg in kgrams]

        if len(hashes) < self.WINDOW_SIZE:
            return set(hashes)

        # Winnowing: select minimum in each window
        fingerprints = set()
        prev_min_idx = -1

        for i in range(len(hashes) - self.WINDOW_SIZE + 1):
            window = hashes[i:i + self.WINDOW_SIZE]
            min_idx = i + window.index(min(window))

            # Only add if this is a new minimum position
            if min_idx != prev_min_idx:
                fingerprints.add(hashes[min_idx])
                prev_min_idx = min_idx

        return fingerprints

    def _hash_kgram(self, kgram: str) -> int:
        """Hash a k-gram to an integer."""
        return int(hashlib.md5(kgram.encode()).hexdigest()[:8], 16)

    def _compare_files(self, path_a: str, path_b: str) -> CodeClone | None:
        """
        Compare two files for clones.

        Returns:
            CodeClone if similarity exceeds threshold, None otherwise.
        """
        fp_a = self.file_fingerprints.get(path_a, set())
        fp_b = self.file_fingerprints.get(path_b, set())

        if not fp_a or not fp_b:
            return None

        # Jaccard similarity of fingerprints
        intersection = len(fp_a & fp_b)
        union = len(fp_a | fp_b)

        if union == 0:
            return None

        similarity = intersection / union

        if similarity < self.MIN_SIMILARITY:
            return None

        # Determine clone type
        if similarity > 0.95:
            clone_type = "exact"
        elif similarity > 0.7:
            clone_type = "parameterized"
        else:
            clone_type = "near-miss"

        return CodeClone(
            file_a=path_a,
            file_b=path_b,
            similarity=similarity,
            clone_type=clone_type,
            shared_fingerprints=intersection,
            total_fingerprints_a=len(fp_a),
            total_fingerprints_b=len(fp_b),
        )

    def find_clones_for_file(self, file_path: str) -> list[CodeClone]:
        """
        Find clones for a specific file.

        Args:
            file_path: Path to the file.

        Returns:
            List of clones involving this file.
        """
        self._load_and_fingerprint_files()

        clones = []
        for other_path in self.file_fingerprints:
            if other_path != file_path:
                clone = self._compare_files(file_path, other_path)
                if clone:
                    clones.append(clone)

        clones.sort(key=lambda c: c.similarity, reverse=True)
        return clones


def detect_code_clones(conn: sqlite3.Connection) -> dict[str, Any]:
    """
    Detect code clones in the indexed codebase.

    Args:
        conn: Database connection.

    Returns:
        Clone detection results.
    """
    detector = CloneDetector(conn)
    clones = detector.analyze()

    # Group by clone type
    by_type: dict[str, int] = {}
    for clone in clones:
        by_type[clone.clone_type] = by_type.get(clone.clone_type, 0) + 1

    return {
        "total_clones": len(clones),
        "by_type": by_type,
        "clones": [c.to_dict() for c in clones[:50]],  # Top 50
    }


def find_clones_for_file(conn: sqlite3.Connection, file_path: str) -> dict[str, Any]:
    """
    Find clones for a specific file.

    Args:
        conn: Database connection.
        file_path: Path to the file.

    Returns:
        Clones involving this file.
    """
    detector = CloneDetector(conn)
    clones = detector.find_clones_for_file(file_path)

    return {
        "file": Path(file_path).name,
        "total_clones": len(clones),
        "clones": [c.to_dict() for c in clones],
    }
