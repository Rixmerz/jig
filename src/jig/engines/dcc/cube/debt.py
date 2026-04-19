"""
Technical Debt Score for DeltaCodeCube.

Calculates a composite technical debt score for files and the entire codebase.
Combines multiple metrics into a single actionable score.

Debt factors:
1. Complexity Debt: High cyclomatic/Halstead complexity
2. Size Debt: Files that are too large
3. Coupling Debt: Too many dependencies
4. Duplication Debt: Code clones
5. Staleness Debt: Old, unchanged code
6. Documentation Debt: Low comment ratio
7. Smell Debt: Code smells detected
8. Tension Debt: Unresolved tensions

Each factor is normalized to 0-100 and weighted to produce final score.
"""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from jig.engines.dcc.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class DebtBreakdown:
    """Breakdown of debt by factor."""
    complexity: float = 0.0
    size: float = 0.0
    coupling: float = 0.0
    duplication: float = 0.0
    staleness: float = 0.0
    documentation: float = 0.0
    smells: float = 0.0
    tensions: float = 0.0

    def to_dict(self) -> dict[str, float]:
        """Convert to dictionary."""
        return {
            "complexity": round(self.complexity, 1),
            "size": round(self.size, 1),
            "coupling": round(self.coupling, 1),
            "duplication": round(self.duplication, 1),
            "staleness": round(self.staleness, 1),
            "documentation": round(self.documentation, 1),
            "smells": round(self.smells, 1),
            "tensions": round(self.tensions, 1),
        }

    @property
    def total(self) -> float:
        """Weighted total score."""
        weights = {
            "complexity": 0.20,
            "size": 0.10,
            "coupling": 0.15,
            "duplication": 0.15,
            "staleness": 0.10,
            "documentation": 0.05,
            "smells": 0.15,
            "tensions": 0.10,
        }
        return (
            self.complexity * weights["complexity"] +
            self.size * weights["size"] +
            self.coupling * weights["coupling"] +
            self.duplication * weights["duplication"] +
            self.staleness * weights["staleness"] +
            self.documentation * weights["documentation"] +
            self.smells * weights["smells"] +
            self.tensions * weights["tensions"]
        )


@dataclass
class FileDebt:
    """Technical debt for a single file."""
    file_path: str
    file_name: str
    score: float  # 0-100, higher = more debt
    grade: str  # A, B, C, D, F
    breakdown: DebtBreakdown
    recommendations: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "file_path": self.file_path,
            "file_name": self.file_name,
            "score": round(self.score, 1),
            "grade": self.grade,
            "breakdown": self.breakdown.to_dict(),
            "recommendations": self.recommendations,
        }


class TechnicalDebtCalculator:
    """
    Calculates technical debt scores.

    Score interpretation:
    - 0-20: A (Excellent) - Minimal debt
    - 21-40: B (Good) - Acceptable debt
    - 41-60: C (Fair) - Should address soon
    - 61-80: D (Poor) - Needs attention
    - 81-100: F (Critical) - Immediate action required
    """

    # Thresholds for debt calculation
    MAX_LINES = 500
    MAX_COMPLEXITY = 0.7
    MAX_COUPLING = 0.8
    MIN_COMMENT_RATIO = 0.1

    def __init__(self, conn: sqlite3.Connection):
        """Initialize with database connection."""
        self.conn = conn
        self.file_clones: dict[str, int] = {}
        self.file_smells: dict[str, int] = {}
        self.file_tensions: dict[str, int] = {}

    def calculate_all(self) -> dict[str, Any]:
        """
        Calculate debt for all files and codebase.

        Returns:
            Complete debt analysis.
        """
        # Pre-calculate shared metrics
        self._calculate_clone_counts()
        self._calculate_smell_counts()
        self._calculate_tension_counts()

        # Calculate for each file
        file_debts = self._calculate_file_debts()

        # Calculate codebase summary
        if file_debts:
            avg_score = sum(f.score for f in file_debts) / len(file_debts)
            max_score = max(f.score for f in file_debts)
            min_score = min(f.score for f in file_debts)

            # Distribution by grade
            by_grade = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
            for f in file_debts:
                by_grade[f.grade] = by_grade.get(f.grade, 0) + 1

            # Top debt files
            top_debt = sorted(file_debts, key=lambda f: f.score, reverse=True)[:10]
        else:
            avg_score = 0
            max_score = 0
            min_score = 0
            by_grade = {}
            top_debt = []

        return {
            "codebase_score": round(avg_score, 1),
            "codebase_grade": self._score_to_grade(avg_score),
            "total_files": len(file_debts),
            "by_grade": by_grade,
            "max_debt": round(max_score, 1),
            "min_debt": round(min_score, 1),
            "top_debt_files": [f.to_dict() for f in top_debt],
            "all_files": [f.to_dict() for f in file_debts],
        }

    def calculate_for_file(self, file_path: str) -> FileDebt | None:
        """
        Calculate debt for a specific file.

        Args:
            file_path: Path to the file.

        Returns:
            FileDebt or None if file not found.
        """
        self._calculate_clone_counts()
        self._calculate_smell_counts()
        self._calculate_tension_counts()

        cursor = self.conn.execute("""
            SELECT * FROM code_points WHERE file_path = ?
        """, (file_path,))
        row = cursor.fetchone()

        if not row:
            return None

        return self._calculate_file_debt(row)

    def _calculate_file_debts(self) -> list[FileDebt]:
        """Calculate debt for all files."""
        cursor = self.conn.execute("SELECT * FROM code_points")
        return [self._calculate_file_debt(row) for row in cursor.fetchall()]

    def _calculate_file_debt(self, row: dict) -> FileDebt:
        """Calculate debt for a single file from database row."""
        file_path = row["file_path"]
        file_name = Path(file_path).name

        structural = json.loads(row["structural_features"])
        breakdown = DebtBreakdown()
        recommendations = []

        # 1. Complexity Debt (cyclomatic + Halstead)
        cyclomatic = structural[6] if len(structural) > 6 else 0
        halstead_difficulty = structural[10] if len(structural) > 10 else 0
        complexity_score = (cyclomatic + halstead_difficulty) / 2
        breakdown.complexity = min(complexity_score * 100, 100)

        if breakdown.complexity > 60:
            recommendations.append("Reduce complexity by extracting functions")

        # 2. Size Debt
        line_count = row["line_count"]
        if line_count > self.MAX_LINES:
            breakdown.size = min((line_count / self.MAX_LINES) * 50, 100)
            recommendations.append(f"File too large ({line_count} lines), consider splitting")
        else:
            breakdown.size = (line_count / self.MAX_LINES) * 20

        # 3. Coupling Debt
        coupling = structural[15] if len(structural) > 15 else 0
        import_diversity = structural[13] if len(structural) > 13 else 0
        coupling_score = (coupling + import_diversity) / 2
        breakdown.coupling = min(coupling_score * 100, 100)

        if breakdown.coupling > 60:
            recommendations.append("High coupling - consider dependency injection")

        # 4. Duplication Debt
        clone_count = self.file_clones.get(file_path, 0)
        breakdown.duplication = min(clone_count * 25, 100)

        if clone_count > 0:
            recommendations.append(f"Found {clone_count} code clones - extract shared code")

        # 5. Staleness Debt (using temporal features if available)
        try:
            from jig.engines.dcc.cube.features.temporal import extract_temporal_features
            temporal = extract_temporal_features(file_path)
            days_since = temporal[3]  # Inverted: 0 = stale
            if days_since < 0.2:
                breakdown.staleness = 60
                recommendations.append("File hasn't been updated recently - verify still relevant")
            else:
                breakdown.staleness = (1 - days_since) * 30
        except Exception:
            breakdown.staleness = 0

        # 6. Documentation Debt
        comment_ratio = structural[5] if len(structural) > 5 else 0
        if comment_ratio < self.MIN_COMMENT_RATIO:
            breakdown.documentation = (1 - comment_ratio / self.MIN_COMMENT_RATIO) * 50
            if breakdown.documentation > 30:
                recommendations.append("Low documentation - add comments/docstrings")
        else:
            breakdown.documentation = 0

        # 7. Smell Debt
        smell_count = self.file_smells.get(file_path, 0)
        breakdown.smells = min(smell_count * 30, 100)

        if smell_count > 0:
            recommendations.append(f"Address {smell_count} detected code smells")

        # 8. Tension Debt
        tension_count = self.file_tensions.get(file_path, 0)
        breakdown.tensions = min(tension_count * 40, 100)

        if tension_count > 0:
            recommendations.append(f"Resolve {tension_count} active tensions")

        # Calculate total score
        score = breakdown.total
        grade = self._score_to_grade(score)

        return FileDebt(
            file_path=file_path,
            file_name=file_name,
            score=score,
            grade=grade,
            breakdown=breakdown,
            recommendations=recommendations[:5],  # Top 5 recommendations
        )

    def _calculate_clone_counts(self) -> None:
        """Pre-calculate clone counts per file."""
        try:
            from jig.engines.dcc.cube.clones import CloneDetector
            detector = CloneDetector(self.conn)
            clones = detector.analyze()

            for clone in clones:
                self.file_clones[clone.file_a] = self.file_clones.get(clone.file_a, 0) + 1
                self.file_clones[clone.file_b] = self.file_clones.get(clone.file_b, 0) + 1
        except Exception as e:
            logger.debug(f"Could not calculate clones: {e}")

    def _calculate_smell_counts(self) -> None:
        """Pre-calculate smell counts per file."""
        try:
            from jig.engines.dcc.cube.smells import SmellDetector
            detector = SmellDetector(self.conn)
            smells = detector.detect_all()

            for smell in smells:
                self.file_smells[smell.file_path] = self.file_smells.get(smell.file_path, 0) + 1
        except Exception as e:
            logger.debug(f"Could not calculate smells: {e}")

    def _calculate_tension_counts(self) -> None:
        """Pre-calculate tension counts per file."""
        try:
            cursor = self.conn.execute("""
                SELECT cp.file_path, COUNT(*) as count
                FROM tensions t
                JOIN contracts c ON t.contract_id = c.id
                JOIN code_points cp ON c.callee_id = cp.id
                WHERE t.status = 'detected'
                GROUP BY cp.file_path
            """)

            for row in cursor.fetchall():
                self.file_tensions[row["file_path"]] = row["count"]
        except Exception as e:
            logger.debug(f"Could not calculate tensions: {e}")

    def _score_to_grade(self, score: float) -> str:
        """Convert score to letter grade."""
        if score <= 20:
            return "A"
        elif score <= 40:
            return "B"
        elif score <= 60:
            return "C"
        elif score <= 80:
            return "D"
        else:
            return "F"


def calculate_technical_debt(conn: sqlite3.Connection) -> dict[str, Any]:
    """
    Calculate technical debt for the codebase.

    Args:
        conn: Database connection.

    Returns:
        Debt analysis results.
    """
    calculator = TechnicalDebtCalculator(conn)
    return calculator.calculate_all()


def calculate_file_debt(conn: sqlite3.Connection, file_path: str) -> dict[str, Any]:
    """
    Calculate technical debt for a specific file.

    Args:
        conn: Database connection.
        file_path: Path to the file.

    Returns:
        File debt or error.
    """
    calculator = TechnicalDebtCalculator(conn)
    result = calculator.calculate_for_file(file_path)

    if result is None:
        return {"error": f"File not found: {file_path}"}

    return result.to_dict()
