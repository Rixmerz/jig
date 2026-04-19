"""
Dependency Drift Detection for DeltaCodeCube.

Detects when files that should be similar are drifting apart,
or when tightly coupled files are diverging.

Drift types:
1. Semantic Drift: Files in same domain diverging in style/patterns
2. Contract Drift: Dependent files moving apart in feature space
3. Cluster Drift: Files leaving their natural cluster
4. Temporal Drift: Some files updated while related files are stale

Useful for:
- Detecting inconsistent code evolution
- Finding files that need synchronization
- Identifying modules that are growing apart
"""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from jig.engines.dcc.cube.code_point import CodePoint
from jig.engines.dcc.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class DriftDetection:
    """A detected drift."""
    drift_type: str  # "semantic", "contract", "cluster", "temporal"
    severity: str  # "low", "medium", "high"
    file_a: str
    file_b: str
    description: str
    current_distance: float
    expected_distance: float
    drift_amount: float
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "drift_type": self.drift_type,
            "severity": self.severity,
            "file_a": Path(self.file_a).name,
            "file_b": Path(self.file_b).name,
            "file_a_path": self.file_a,
            "file_b_path": self.file_b,
            "description": self.description,
            "current_distance": round(self.current_distance, 4),
            "expected_distance": round(self.expected_distance, 4),
            "drift_amount": round(self.drift_amount, 4),
            "recommendation": self.recommendation,
        }


class DriftDetector:
    """
    Detects various types of code drift.
    """

    SEMANTIC_DRIFT_THRESHOLD = 0.4  # Max expected distance within same domain
    CONTRACT_DRIFT_THRESHOLD = 0.3  # Max drift from baseline
    TEMPORAL_DRIFT_DAYS = 60  # Days difference to flag temporal drift

    def __init__(self, conn: sqlite3.Connection):
        """Initialize with database connection."""
        self.conn = conn

    def _normalize_vectors(self, v1: np.ndarray, v2: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Normalize two vectors to the same dimension by padding the shorter one."""
        if len(v1) == len(v2):
            return v1, v2
        max_len = max(len(v1), len(v2))
        if len(v1) < max_len:
            v1 = np.pad(v1, (0, max_len - len(v1)), mode='constant', constant_values=0)
        if len(v2) < max_len:
            v2 = np.pad(v2, (0, max_len - len(v2)), mode='constant', constant_values=0)
        return v1, v2

    def detect_all(self) -> list[DriftDetection]:
        """
        Detect all types of drift.

        Returns:
            List of detected drifts.
        """
        drifts = []

        drifts.extend(self._detect_semantic_drift())
        drifts.extend(self._detect_contract_drift())
        drifts.extend(self._detect_temporal_drift())

        # Sort by severity
        severity_order = {"high": 0, "medium": 1, "low": 2}
        drifts.sort(key=lambda d: severity_order.get(d.severity, 3))

        return drifts

    def _detect_semantic_drift(self) -> list[DriftDetection]:
        """
        Detect files in the same domain that are diverging.

        Files in the same semantic domain should have similar patterns.
        Large distances between them indicate drift.
        """
        drifts = []

        # Load code points grouped by domain
        cursor = self.conn.execute("""
            SELECT id, file_path, lexical_features, structural_features, semantic_features
            FROM code_points
        """)

        by_domain: dict[str, list[dict]] = {}

        for row in cursor.fetchall():
            semantic = json.loads(row["semantic_features"])
            domains = ["auth", "db", "api", "ui", "util"]
            domain_idx = np.argmax(semantic[:len(domains)])
            domain = domains[domain_idx] if domain_idx < len(domains) else "unknown"

            if domain not in by_domain:
                by_domain[domain] = []

            by_domain[domain].append({
                "id": row["id"],
                "file_path": row["file_path"],
                "lexical": np.array(json.loads(row["lexical_features"])),
                "structural": np.array(json.loads(row["structural_features"])),
                "semantic": np.array(semantic),
            })

        # Check within each domain
        for domain, files in by_domain.items():
            if len(files) < 2:
                continue

            for i, file_a in enumerate(files):
                for file_b in files[i + 1:]:
                    # Calculate distance using concatenated features
                    pos_a = np.concatenate([file_a["lexical"], file_a["structural"]])
                    pos_b = np.concatenate([file_b["lexical"], file_b["structural"]])

                    # Normalize to same dimension
                    pos_a, pos_b = self._normalize_vectors(pos_a, pos_b)

                    # Cosine distance
                    norm_a = np.linalg.norm(pos_a)
                    norm_b = np.linalg.norm(pos_b)
                    if norm_a > 0 and norm_b > 0:
                        similarity = np.dot(pos_a, pos_b) / (norm_a * norm_b)
                        distance = 1 - similarity
                    else:
                        distance = 1.0

                    if distance > self.SEMANTIC_DRIFT_THRESHOLD:
                        drift_amount = distance - self.SEMANTIC_DRIFT_THRESHOLD

                        if drift_amount > 0.3:
                            severity = "high"
                        elif drift_amount > 0.15:
                            severity = "medium"
                        else:
                            severity = "low"

                        drifts.append(DriftDetection(
                            drift_type="semantic",
                            severity=severity,
                            file_a=file_a["file_path"],
                            file_b=file_b["file_path"],
                            description=f"Files in '{domain}' domain are diverging",
                            current_distance=distance,
                            expected_distance=self.SEMANTIC_DRIFT_THRESHOLD,
                            drift_amount=drift_amount,
                            recommendation=f"Review if both files still belong to '{domain}' domain, "
                                          "or harmonize their patterns",
                        ))

        return drifts

    def _detect_contract_drift(self) -> list[DriftDetection]:
        """
        Detect when dependent files are drifting from baseline.

        Uses the contract baseline_distance and compares to current.
        """
        drifts = []

        cursor = self.conn.execute("""
            SELECT c.baseline_distance,
                   cp1.file_path as caller_path, cp1.lexical_features as caller_lex,
                   cp1.structural_features as caller_struct, cp1.semantic_features as caller_sem,
                   cp2.file_path as callee_path, cp2.lexical_features as callee_lex,
                   cp2.structural_features as callee_struct, cp2.semantic_features as callee_sem
            FROM contracts c
            JOIN code_points cp1 ON c.caller_id = cp1.id
            JOIN code_points cp2 ON c.callee_id = cp2.id
        """)

        for row in cursor.fetchall():
            baseline = row["baseline_distance"]

            # Calculate current distance
            caller_pos = np.concatenate([
                np.array(json.loads(row["caller_lex"])),
                np.array(json.loads(row["caller_struct"])),
                np.array(json.loads(row["caller_sem"])),
            ])
            callee_pos = np.concatenate([
                np.array(json.loads(row["callee_lex"])),
                np.array(json.loads(row["callee_struct"])),
                np.array(json.loads(row["callee_sem"])),
            ])

            # Normalize to same dimension
            caller_pos, callee_pos = self._normalize_vectors(caller_pos, callee_pos)

            # Cosine distance
            norm_a = np.linalg.norm(caller_pos)
            norm_b = np.linalg.norm(callee_pos)
            if norm_a > 0 and norm_b > 0:
                similarity = np.dot(caller_pos, callee_pos) / (norm_a * norm_b)
                current = 1 - similarity
            else:
                current = 1.0

            # Check drift from baseline
            if baseline > 0:
                drift = abs(current - baseline) / baseline
            else:
                drift = current

            if drift > self.CONTRACT_DRIFT_THRESHOLD:
                if drift > 0.5:
                    severity = "high"
                elif drift > 0.35:
                    severity = "medium"
                else:
                    severity = "low"

                drifts.append(DriftDetection(
                    drift_type="contract",
                    severity=severity,
                    file_a=row["caller_path"],
                    file_b=row["callee_path"],
                    description="Dependent files drifting from baseline",
                    current_distance=current,
                    expected_distance=baseline,
                    drift_amount=drift,
                    recommendation="Review the dependency - files may need synchronization "
                                  "or the contract may need updating",
                ))

        return drifts

    def _detect_temporal_drift(self) -> list[DriftDetection]:
        """
        Detect when dependent files have very different update patterns.

        If file A depends on file B, and B is updated but A is stale,
        there may be a maintenance issue.
        """
        drifts = []

        from jig.engines.dcc.cube.features.temporal import extract_temporal_features

        cursor = self.conn.execute("""
            SELECT cp1.file_path as caller_path, cp2.file_path as callee_path
            FROM contracts c
            JOIN code_points cp1 ON c.caller_id = cp1.id
            JOIN code_points cp2 ON c.callee_id = cp2.id
        """)

        for row in cursor.fetchall():
            try:
                caller_temporal = extract_temporal_features(row["caller_path"])
                callee_temporal = extract_temporal_features(row["callee_path"])

                # Compare days_since_change (index 3, inverted)
                caller_recency = caller_temporal[3]  # 1 = recent, 0 = stale
                callee_recency = callee_temporal[3]

                # If callee is recent but caller is stale, flag it
                if callee_recency > 0.7 and caller_recency < 0.3:
                    drift_amount = callee_recency - caller_recency

                    drifts.append(DriftDetection(
                        drift_type="temporal",
                        severity="medium",
                        file_a=row["caller_path"],
                        file_b=row["callee_path"],
                        description=f"{Path(row['callee_path']).name} was updated recently, "
                                   f"but dependent {Path(row['caller_path']).name} is stale",
                        current_distance=drift_amount,
                        expected_distance=0.0,
                        drift_amount=drift_amount,
                        recommendation=f"Review if {Path(row['caller_path']).name} needs updates "
                                      f"after changes to {Path(row['callee_path']).name}",
                    ))

            except Exception as e:
                logger.debug(f"Could not get temporal features: {e}")

        return drifts


def detect_drift(conn: sqlite3.Connection) -> dict[str, Any]:
    """
    Detect all types of drift in the codebase.

    Args:
        conn: Database connection.

    Returns:
        Drift detection results.
    """
    detector = DriftDetector(conn)
    drifts = detector.detect_all()

    # Group by type
    by_type: dict[str, int] = {}
    by_severity: dict[str, int] = {}

    for d in drifts:
        by_type[d.drift_type] = by_type.get(d.drift_type, 0) + 1
        by_severity[d.severity] = by_severity.get(d.severity, 0) + 1

    return {
        "total_drifts": len(drifts),
        "by_type": by_type,
        "by_severity": by_severity,
        "drifts": [d.to_dict() for d in drifts[:30]],  # Top 30
    }
