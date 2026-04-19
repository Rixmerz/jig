"""
DeltaCodeCube - Main class for 3D code indexing system.

Manages CodePoints in a 63-dimensional feature space and provides:
- Indexing of code files
- Similarity search
- Position queries
- Persistence to SQLite
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from jig.engines.dcc.cube.code_point import CodePoint, create_code_point
from jig.engines.dcc.cube.contracts import Contract, ContractDetector
from jig.engines.dcc.cube.delta import Delta, DeltaTracker, create_delta
from jig.engines.dcc.cube.features.semantic import get_dominant_domain
from jig.engines.dcc.cube.tension import Tension, TensionDetector
from jig.engines.dcc.cube.suggestions import SuggestionGenerator
from jig.engines.dcc.utils.logger import get_logger

logger = get_logger(__name__)


class DeltaCodeCube:
    """
    3D code indexing system based on feature space representation.

    Each code file is represented as a point in 63-dimensional space:
    - Lexical (50 dims): Term importance via TF
    - Structural (8 dims): Code structure metrics
    - Semantic (5 dims): Domain classification

    Supports:
    - Indexing individual files or directories
    - Similarity search (find similar files)
    - Position queries (get file's position in cube)
    - Persistence to SQLite database
    """

    def __init__(self, conn: sqlite3.Connection):
        """
        Initialize DeltaCodeCube with database connection.

        Args:
            conn: SQLite connection (should have dict_factory row_factory).
        """
        self.conn = conn
        self._ensure_tables()
        self.contract_detector = ContractDetector(conn)
        self.delta_tracker = DeltaTracker(conn)
        self.tension_detector = TensionDetector(conn)
        self.suggestion_generator = SuggestionGenerator(conn)

    def _ensure_tables(self) -> None:
        """Ensure cube tables exist in database."""
        # Tables are created by main schema, but verify
        cursor = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='code_points'"
        )
        if not cursor.fetchone():
            logger.warning("code_points table not found - cube features may not work")

    def index_file(self, file_path: str, content: str | None = None) -> CodePoint:
        """
        Index a single code file.

        Args:
            file_path: Path to the code file.
            content: Optional content (reads from file if not provided).

        Returns:
            Created or updated CodePoint.
        """
        path = Path(file_path).resolve()

        # Read content if not provided
        if content is None:
            content = path.read_text(encoding="utf-8")

        # Create CodePoint
        code_point = create_code_point(str(path), content)

        # Check if exists
        existing = self._get_code_point_by_path(str(path))

        if existing:
            # Update existing
            code_point.created_at = existing.created_at
            self._update_code_point(code_point)
            logger.info(f"Updated code point: {path.name}")
        else:
            # Insert new
            self._insert_code_point(code_point)
            logger.info(f"Indexed code point: {path.name}")

        return code_point

    def index_directory(
        self,
        directory: str,
        patterns: list[str] | None = None,
        recursive: bool = True,
    ) -> list[CodePoint]:
        """
        Index all code files in a directory.

        Args:
            directory: Path to directory.
            patterns: Glob patterns for files (default: common code extensions).
            recursive: Whether to search recursively.

        Returns:
            List of created CodePoints.
        """
        dir_path = Path(directory).resolve()

        if patterns is None:
            patterns = ["*.js", "*.jsx", "*.ts", "*.tsx", "*.py", "*.go", "*.java"]

        code_points = []

        for pattern in patterns:
            if recursive:
                files = dir_path.rglob(pattern)
            else:
                files = dir_path.glob(pattern)

            for file_path in files:
                # Skip node_modules, .git, etc.
                if self._should_skip(file_path):
                    continue

                try:
                    cp = self.index_file(str(file_path))
                    code_points.append(cp)
                except Exception as e:
                    logger.warning(f"Failed to index {file_path}: {e}")

        logger.info(f"Indexed {len(code_points)} files from {dir_path}")

        # Detect contracts between indexed files
        if code_points:
            contracts = self._detect_and_save_contracts(code_points)
            logger.info(f"Detected {len(contracts)} contracts")

        return code_points

    def _should_skip(self, file_path: Path) -> bool:
        """Check if file should be skipped during indexing."""
        skip_dirs = {
            "node_modules",
            ".git",
            ".next",
            "__pycache__",
            ".venv",
            "venv",
            "dist",
            "build",
            ".cache",
            "coverage",
        }

        for part in file_path.parts:
            if part in skip_dirs:
                return True

        return False

    def get_code_point(self, file_path: str) -> CodePoint | None:
        """
        Get CodePoint for a file.

        Args:
            file_path: Path to the code file.

        Returns:
            CodePoint if found, None otherwise.
        """
        path = Path(file_path).resolve()
        return self._get_code_point_by_path(str(path))

    def get_position(self, file_path: str) -> dict[str, Any] | None:
        """
        Get position of a file in the cube.

        Args:
            file_path: Path to the code file.

        Returns:
            Dictionary with position info, or None if not indexed.
        """
        code_point = self.get_code_point(file_path)

        if not code_point:
            return None

        return {
            "file_path": code_point.file_path,
            "id": code_point.id,
            "position": {
                "lexical": code_point.lexical.tolist(),
                "structural": code_point.structural.tolist(),
                "semantic": code_point.semantic.tolist(),
                "full": code_point.position.tolist(),
            },
            "dominant_domain": code_point.dominant_domain,
            "line_count": code_point.line_count,
            "content_hash": code_point.content_hash,
        }

    def find_similar(
        self,
        file_path: str,
        limit: int = 5,
        axis: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Find files similar to a given file.

        Args:
            file_path: Path to reference file.
            limit: Maximum results to return.
            axis: Specific axis to compare ('lexical', 'structural', 'semantic', or None for all).

        Returns:
            List of similar files with distances.
        """
        reference = self.get_code_point(file_path)

        if not reference:
            return []

        # Get all code points
        all_points = self._get_all_code_points()

        # Calculate distances
        results = []
        for cp in all_points:
            if cp.id == reference.id:
                continue

            if axis:
                distance = reference.distance_in_axis(cp, axis)
            else:
                distance = reference.distance_to(cp)

            results.append({
                "file_path": cp.file_path,
                "id": cp.id,
                "distance": distance,
                "similarity": reference.similarity_to(cp),
                "dominant_domain": cp.dominant_domain,
            })

        # Sort by distance (ascending)
        results.sort(key=lambda x: x["distance"])

        return results[:limit]

    def compare_files(
        self,
        file_path_a: str,
        file_path_b: str,
    ) -> dict[str, Any]:
        """
        Compare two files in the cube.

        Shows detailed comparison including:
        - Distance in each axis
        - Similarity score
        - What makes them similar/different

        Args:
            file_path_a: Path to first file.
            file_path_b: Path to second file.

        Returns:
            Detailed comparison dictionary.
        """
        path_a = str(Path(file_path_a).resolve())
        path_b = str(Path(file_path_b).resolve())

        cp_a = self.get_code_point(path_a)
        cp_b = self.get_code_point(path_b)

        if not cp_a:
            return {"error": f"File not indexed: {path_a}"}
        if not cp_b:
            return {"error": f"File not indexed: {path_b}"}

        # Calculate distances
        total_distance = cp_a.distance_to(cp_b)
        lexical_distance = cp_a.distance_in_axis(cp_b, "lexical")
        structural_distance = cp_a.distance_in_axis(cp_b, "structural")
        semantic_distance = cp_a.distance_in_axis(cp_b, "semantic")
        similarity = cp_a.similarity_to(cp_b)

        # Determine what axis contributes most to difference
        distances = {
            "lexical": lexical_distance,
            "structural": structural_distance,
            "semantic": semantic_distance,
        }
        most_different = max(distances, key=distances.get)
        most_similar = min(distances, key=distances.get)

        # Generate insights
        insights = []
        if lexical_distance < 0.5:
            insights.append("Similar terminology/naming conventions")
        elif lexical_distance > 1.5:
            insights.append("Very different vocabulary")

        if structural_distance < 0.3:
            insights.append("Similar code structure (complexity, size)")
        elif structural_distance > 0.8:
            insights.append("Different structural complexity")

        if semantic_distance < 0.2:
            insights.append("Same functional domain")
        elif semantic_distance > 0.5:
            insights.append("Different functional domains")

        return {
            "file_a": {
                "path": path_a,
                "name": Path(path_a).name,
                "domain": cp_a.dominant_domain,
                "lines": cp_a.line_count,
            },
            "file_b": {
                "path": path_b,
                "name": Path(path_b).name,
                "domain": cp_b.dominant_domain,
                "lines": cp_b.line_count,
            },
            "comparison": {
                "total_distance": total_distance,
                "similarity": similarity,
                "similarity_percent": f"{similarity * 100:.1f}%",
                "lexical_distance": lexical_distance,
                "structural_distance": structural_distance,
                "semantic_distance": semantic_distance,
                "most_different_axis": most_different,
                "most_similar_axis": most_similar,
            },
            "insights": insights,
        }

    def export_positions(
        self,
        format: str = "json",
        include_features: bool = False,
    ) -> dict[str, Any]:
        """
        Export all code point positions for visualization.

        Args:
            format: Export format ('json', 'csv', '3d').
            include_features: Include full feature vectors.

        Returns:
            Export data suitable for visualization tools.
        """
        all_points = self._get_all_code_points()

        if format == "3d":
            # Use PCA to reduce from full feature space to 3D
            points_3d = []
            if all_points:
                features = np.array([
                    np.concatenate([cp.lexical, cp.structural, cp.semantic])
                    for cp in all_points
                ])
                if len(features) >= 2:
                    # Center the data
                    mean = features.mean(axis=0)
                    centered = features - mean
                    # SVD for PCA (first 3 principal components)
                    U, S, Vt = np.linalg.svd(centered, full_matrices=False)
                    coords = centered @ Vt[:3].T
                else:
                    # Single point — place at origin
                    coords = np.zeros((len(features), 3))
                for i, cp in enumerate(all_points):
                    points_3d.append({
                        "id": cp.id,
                        "name": Path(cp.file_path).name,
                        "path": cp.file_path,
                        "x": float(coords[i, 0]),
                        "y": float(coords[i, 1]),
                        "z": float(coords[i, 2]),
                        "domain": cp.dominant_domain,
                        "lines": cp.line_count,
                    })
            return {
                "format": "3d",
                "description": "PCA projection of 63D feature space to 3D",
                "axes": {"x": "PC1", "y": "PC2", "z": "PC3"},
                "points": points_3d,
                "count": len(points_3d),
            }

        elif format == "csv":
            # Export as CSV-ready data
            rows = []
            headers = ["id", "name", "path", "domain", "lines", "lexical_mean", "structural_mean", "semantic_mean"]
            for cp in all_points:
                rows.append({
                    "id": cp.id,
                    "name": Path(cp.file_path).name,
                    "path": cp.file_path,
                    "domain": cp.dominant_domain,
                    "lines": cp.line_count,
                    "lexical_mean": float(np.mean(cp.lexical)),
                    "structural_mean": float(np.mean(cp.structural)),
                    "semantic_mean": float(np.mean(cp.semantic)),
                })
            return {
                "format": "csv",
                "headers": headers,
                "rows": rows,
                "count": len(rows),
            }

        else:  # json (default)
            points_json = []
            for cp in all_points:
                point_data = {
                    "id": cp.id,
                    "name": Path(cp.file_path).name,
                    "path": cp.file_path,
                    "domain": cp.dominant_domain,
                    "lines": cp.line_count,
                    "position": {
                        "lexical_mean": float(np.mean(cp.lexical)),
                        "structural_mean": float(np.mean(cp.structural)),
                        "semantic_mean": float(np.mean(cp.semantic)),
                    },
                }
                if include_features:
                    point_data["features"] = {
                        "lexical": cp.lexical.tolist(),
                        "structural": cp.structural.tolist(),
                        "semantic": cp.semantic.tolist(),
                    }
                points_json.append(point_data)

            return {
                "format": "json",
                "include_features": include_features,
                "points": points_json,
                "count": len(points_json),
            }

    def find_by_criteria(
        self,
        domain: str | None = None,
        min_lines: int | None = None,
        max_lines: int | None = None,
        similar_to: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Find files matching multiple criteria.

        Args:
            domain: Filter by domain ('auth', 'db', 'api', 'ui', 'util').
            min_lines: Minimum line count.
            max_lines: Maximum line count.
            similar_to: Path to file to find similar files to.
            limit: Maximum results.

        Returns:
            List of matching files.
        """
        all_points = self._get_all_code_points()
        results = []

        # Get reference point if similar_to specified
        reference = None
        if similar_to:
            reference = self.get_code_point(similar_to)

        for cp in all_points:
            # Apply filters
            if domain and cp.dominant_domain != domain:
                continue
            if min_lines and cp.line_count < min_lines:
                continue
            if max_lines and cp.line_count > max_lines:
                continue

            result = {
                "id": cp.id,
                "file_path": cp.file_path,
                "file_name": Path(cp.file_path).name,
                "domain": cp.dominant_domain,
                "lines": cp.line_count,
            }

            # Add similarity if reference provided
            if reference and cp.id != reference.id:
                result["distance"] = reference.distance_to(cp)
                result["similarity"] = reference.similarity_to(cp)

            results.append(result)

        # Sort by similarity if reference provided, otherwise by lines
        if reference:
            results.sort(key=lambda x: x.get("distance", float("inf")))
        else:
            results.sort(key=lambda x: x["lines"], reverse=True)

        return results[:limit]

    def search_by_domain(self, domain: str, limit: int = 10) -> list[dict[str, Any]]:
        """
        Find files by semantic domain.

        Args:
            domain: Domain name ('auth', 'db', 'api', 'ui', 'util').
            limit: Maximum results.

        Returns:
            List of files in the specified domain.
        """
        cursor = self.conn.execute(
            """
            SELECT * FROM code_points
            WHERE dominant_domain = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (domain, limit),
        )

        results = []
        for row in cursor.fetchall():
            results.append({
                "file_path": row["file_path"],
                "id": row["id"],
                "dominant_domain": row["dominant_domain"],
                "line_count": row["line_count"],
            })

        return results

    def get_stats(self) -> dict[str, Any]:
        """
        Get statistics about indexed code.

        Returns:
            Dictionary with cube statistics.
        """
        # Total code points
        cursor = self.conn.execute("SELECT COUNT(*) as count FROM code_points")
        total = cursor.fetchone()["count"]

        # By domain
        cursor = self.conn.execute(
            """
            SELECT dominant_domain, COUNT(*) as count
            FROM code_points
            GROUP BY dominant_domain
            """
        )
        by_domain = {row["dominant_domain"]: row["count"] for row in cursor.fetchall()}

        # Total lines
        cursor = self.conn.execute("SELECT SUM(line_count) as total FROM code_points")
        result = cursor.fetchone()
        total_lines = result["total"] or 0

        return {
            "total_files": total,
            "total_lines": total_lines,
            "by_domain": by_domain,
        }

    def list_code_points(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """
        List all indexed code points.

        Args:
            limit: Maximum results.
            offset: Offset for pagination.

        Returns:
            List of code point summaries.
        """
        cursor = self.conn.execute(
            """
            SELECT id, file_path, function_name, dominant_domain, line_count, created_at
            FROM code_points
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )

        return [dict(row) for row in cursor.fetchall()]

    # =========================================================================
    # Contract operations
    # =========================================================================

    def _detect_and_save_contracts(self, code_points: list[CodePoint]) -> list[Contract]:
        """
        Detect contracts between indexed files and save to database.

        Args:
            code_points: List of indexed CodePoints.

        Returns:
            List of detected Contracts.
        """
        # Build lookup dictionaries
        indexed_files = {cp.file_path: cp.id for cp in code_points}
        code_points_dict = {cp.id: cp for cp in code_points}

        # Detect contracts
        contracts = self.contract_detector.detect_all_contracts(
            indexed_files=indexed_files,
            code_points=code_points_dict,
        )

        # Save to database
        self.contract_detector.save_contracts(contracts)

        return contracts

    def get_contracts(
        self,
        file_path: str | None = None,
        direction: str = "both",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Get contracts, optionally filtered by file.

        Args:
            file_path: If provided, get contracts for this file.
            direction: 'incoming', 'outgoing', or 'both'.
            limit: Maximum results.

        Returns:
            List of contract dictionaries.
        """
        if file_path:
            path = str(Path(file_path).resolve())
            contracts = self.contract_detector.get_contracts_for_file(path, direction)
        else:
            contracts = self.contract_detector.get_all_contracts(limit)

        return [
            {
                "id": c.id,
                "caller_id": c.caller_id,
                "callee_id": c.callee_id,
                "caller_path": c.caller_path,
                "callee_path": c.callee_path,
                "caller_name": Path(c.caller_path).name,
                "callee_name": Path(c.callee_path).name,
                "contract_type": c.contract_type,
                "baseline_distance": c.baseline_distance,
                "created_at": c.created_at.isoformat(),
            }
            for c in contracts
        ]

    def get_contract_stats(self) -> dict[str, Any]:
        """Get statistics about contracts."""
        return self.contract_detector.get_contract_stats()

    # =========================================================================
    # Delta and Tension operations
    # =========================================================================

    def reindex_file(self, file_path: str) -> dict[str, Any]:
        """
        Re-index a file and detect deltas/tensions.

        This method should be called when a file changes. It:
        1. Gets the current CodePoint (before changes)
        2. Creates a new CodePoint from the updated file
        3. Creates a Delta recording the movement
        4. Detects any tensions with dependent files
        5. Updates the CodePoint in database

        Args:
            file_path: Path to the file that changed.

        Returns:
            Dictionary with delta and tensions information.
        """
        path = Path(file_path).resolve()

        # Get existing CodePoint
        old_code_point = self.get_code_point(str(path))

        if not old_code_point:
            # File not indexed yet, just index it
            new_cp = self.index_file(str(path))
            return {
                "status": "indexed",
                "message": "File was not previously indexed. Indexed now.",
                "code_point_id": new_cp.id,
                "delta": None,
                "tensions": [],
            }

        # Read new content
        content = path.read_text(encoding="utf-8")

        # Create new CodePoint
        new_code_point = create_code_point(str(path), content)
        new_code_point.created_at = old_code_point.created_at  # Preserve creation time

        # Create Delta
        delta = create_delta(old_code_point, new_code_point)

        # Only process if there's significant movement
        if delta.movement_magnitude < 0.01:
            return {
                "status": "unchanged",
                "message": "No significant changes detected.",
                "code_point_id": new_code_point.id,
                "delta": None,
                "tensions": [],
            }

        # Save delta
        self.delta_tracker.save_delta(delta)

        # Detect tensions
        code_points = {cp.id: cp for cp in self._get_all_code_points()}
        code_points[new_code_point.id] = new_code_point

        tensions = self.tension_detector.detect_tensions(
            delta=delta,
            new_code_point=new_code_point,
            code_points=code_points,
        )

        # Save tensions
        self.tension_detector.save_tensions(tensions)

        # Update CodePoint in database
        self._update_code_point(new_code_point)

        return {
            "status": "reindexed",
            "message": f"Detected {len(tensions)} tension(s).",
            "code_point_id": new_code_point.id,
            "delta": delta.to_dict(),
            "tensions": [t.to_dict() for t in tensions],
        }

    def analyze_impact(self, file_path: str) -> dict[str, Any]:
        """
        Analyze potential impact if a file were to change.

        Shows all files that depend on this file (incoming contracts)
        and their current distances.

        Args:
            file_path: Path to the file to analyze.

        Returns:
            Impact analysis with dependents and their distances.
        """
        path = str(Path(file_path).resolve())
        code_point = self.get_code_point(path)

        if not code_point:
            return {
                "status": "error",
                "message": "File not indexed.",
                "file_path": path,
                "dependents": [],
            }

        # Get incoming contracts (files that depend on this file)
        contracts = self.contract_detector.get_contracts_for_file(path, direction="incoming")

        dependents = []
        for contract in contracts:
            caller_cp = self._get_code_point_by_path(contract.caller_path)
            if caller_cp:
                current_distance = caller_cp.distance_to(code_point)
                dependents.append({
                    "file_path": contract.caller_path,
                    "file_name": Path(contract.caller_path).name,
                    "baseline_distance": contract.baseline_distance,
                    "current_distance": current_distance,
                    "distance_delta": current_distance - contract.baseline_distance,
                })

        return {
            "status": "ok",
            "file_path": path,
            "file_name": Path(path).name,
            "code_point_id": code_point.id,
            "dominant_domain": code_point.dominant_domain,
            "dependent_count": len(dependents),
            "dependents": dependents,
            "message": (
                f"{len(dependents)} file(s) depend on this file. "
                f"Changes may affect them."
            ),
        }

    def get_tensions(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Get detected tensions.

        Args:
            status: Filter by status ('detected', 'reviewed', 'resolved', 'ignored').
            limit: Maximum results.

        Returns:
            List of tension dictionaries.
        """
        tensions = self.tension_detector.get_tensions(status=status, limit=limit)
        return [t.to_dict() for t in tensions]

    def resolve_tension(self, tension_id: str, status: str = "resolved") -> bool:
        """
        Update the status of a tension.

        Args:
            tension_id: ID of the tension.
            status: New status ('reviewed', 'resolved', 'ignored').

        Returns:
            True if updated, False if not found.
        """
        return self.tension_detector.update_tension_status(tension_id, status)

    def get_tension_stats(self) -> dict[str, Any]:
        """Get statistics about tensions."""
        return self.tension_detector.get_tension_stats()

    def get_deltas(self, limit: int = 20) -> list[dict[str, Any]]:
        """
        Get recent deltas.

        Args:
            limit: Maximum results.

        Returns:
            List of delta dictionaries.
        """
        deltas = self.delta_tracker.get_recent_deltas(limit=limit)
        return [d.to_dict() for d in deltas]

    # =========================================================================
    # Suggestion operations
    # =========================================================================

    def get_suggestion_context(
        self,
        tension_id: str | None = None,
        file_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Generate rich context for fix suggestions.

        Provides detailed analysis and code snippets to help
        generate intelligent fix suggestions.

        Args:
            tension_id: ID of a specific tension to analyze.
            file_path: Path to file to analyze (uses latest delta).

        Returns:
            Rich context dictionary with analysis and snippets.
        """
        return self.suggestion_generator.generate_suggestion_context(
            tension_id=tension_id,
            file_path=file_path,
        )

    # =========================================================================
    # Database operations
    # =========================================================================

    def _insert_code_point(self, cp: CodePoint) -> None:
        """Insert a new CodePoint into database."""
        self.conn.execute(
            """
            INSERT INTO code_points (
                id, file_path, function_name,
                lexical_features, structural_features, semantic_features,
                content_hash, line_count, dominant_domain,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cp.id,
                cp.file_path,
                cp.function_name,
                json.dumps(cp.lexical.tolist()),
                json.dumps(cp.structural.tolist()),
                json.dumps(cp.semantic.tolist()),
                cp.content_hash,
                cp.line_count,
                cp.dominant_domain,
                cp.created_at.isoformat(),
                cp.updated_at.isoformat(),
            ),
        )
        self.conn.commit()

    def _update_code_point(self, cp: CodePoint) -> None:
        """Update an existing CodePoint in database."""
        self.conn.execute(
            """
            UPDATE code_points SET
                lexical_features = ?,
                structural_features = ?,
                semantic_features = ?,
                content_hash = ?,
                line_count = ?,
                dominant_domain = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                json.dumps(cp.lexical.tolist()),
                json.dumps(cp.structural.tolist()),
                json.dumps(cp.semantic.tolist()),
                cp.content_hash,
                cp.line_count,
                cp.dominant_domain,
                cp.updated_at.isoformat(),
                cp.id,
            ),
        )
        self.conn.commit()

    def prune_stale_files(self) -> list[str]:
        """Remove indexed files that no longer exist on disk.

        Returns:
            List of file paths that were pruned from the index.
        """
        all_points = self._get_all_code_points()
        pruned = []

        for cp in all_points:
            if not Path(cp.file_path).exists():
                self.conn.execute(
                    "DELETE FROM code_points WHERE id = ?",
                    (cp.id,),
                )
                # Also clean up contracts referencing this file
                self.conn.execute(
                    "DELETE FROM contracts WHERE file_a = ? OR file_b = ?",
                    (cp.file_path, cp.file_path),
                )
                pruned.append(cp.file_path)

        if pruned:
            self.conn.commit()
            logger.info(f"Pruned {len(pruned)} stale files from index")

        return pruned

    def _get_code_point_by_path(self, file_path: str) -> CodePoint | None:
        """Get CodePoint by file path."""
        cursor = self.conn.execute(
            "SELECT * FROM code_points WHERE file_path = ?",
            (file_path,),
        )
        row = cursor.fetchone()

        if not row:
            return None

        return self._row_to_code_point(row)

    def _get_all_code_points(self) -> list[CodePoint]:
        """Get all CodePoints from database."""
        cursor = self.conn.execute("SELECT * FROM code_points")
        return [self._row_to_code_point(row) for row in cursor.fetchall()]

    def _row_to_code_point(self, row: dict[str, Any]) -> CodePoint:
        """Convert database row to CodePoint."""
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
