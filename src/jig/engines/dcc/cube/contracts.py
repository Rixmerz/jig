"""
Contract - Dependency relationship between CodePoints.

A Contract represents a dependency (import/require) between two code files,
with a baseline distance that represents the "healthy" state of the relationship.

When code changes, if the distance between caller and callee changes significantly
from the baseline, a Tension is detected.
"""

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from jig.engines.dcc.utils.logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# Import Patterns (Multi-language regex)
# =============================================================================

IMPORT_PATTERNS = {
    # ES6: import X from './path' or import './path'
    "es6_from": re.compile(
        r"""import\s+(?:[\w{},\s*]+\s+from\s+)?['"]([^'"]+)['"]""",
        re.MULTILINE
    ),
    # CommonJS: require('./path')
    "commonjs": re.compile(
        r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""",
        re.MULTILINE
    ),
    # Python: from module import X or import module
    "python_from": re.compile(
        r"""from\s+([\w.]+)\s+import""",
        re.MULTILINE
    ),
    "python_import": re.compile(
        r"""^import\s+([\w.]+)""",
        re.MULTILINE
    ),
    # Dynamic imports: import('./path')
    "dynamic": re.compile(
        r"""import\s*\(\s*['"]([^'"]+)['"]\s*\)""",
        re.MULTILINE
    ),
}

# File extensions by language
EXTENSION_LANGUAGE = {
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".py": "python",
    ".go": "go",
    ".java": "java",
}


@dataclass
class Contract:
    """
    Represents a dependency relationship between two CodePoints.

    Attributes:
        id: Unique identifier for this contract.
        caller_id: ID of the CodePoint that imports/uses.
        callee_id: ID of the CodePoint that is imported/used.
        caller_path: File path of caller.
        callee_path: File path of callee.
        contract_type: Type of dependency ('import', 'call', 'inherit').
        baseline_distance: The "healthy" distance when contract was created.
        created_at: When the contract was detected.
    """

    id: str
    caller_id: str
    callee_id: str
    caller_path: str
    callee_path: str
    contract_type: str = "import"
    baseline_distance: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "caller_id": self.caller_id,
            "callee_id": self.callee_id,
            "caller_path": self.caller_path,
            "callee_path": self.callee_path,
            "contract_type": self.contract_type,
            "baseline_distance": self.baseline_distance,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Contract":
        """Create Contract from dictionary."""
        return cls(
            id=data["id"],
            caller_id=data["caller_id"],
            callee_id=data["callee_id"],
            caller_path=data["caller_path"],
            callee_path=data["callee_path"],
            contract_type=data.get("contract_type", "import"),
            baseline_distance=data.get("baseline_distance", 0.0),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if "created_at" in data
                else datetime.now()
            ),
        )

    def __repr__(self) -> str:
        caller_name = Path(self.caller_path).name
        callee_name = Path(self.callee_path).name
        return f"Contract({caller_name} → {callee_name}, dist={self.baseline_distance:.3f})"


# =============================================================================
# Import Parser
# =============================================================================


def parse_imports(content: str, file_path: str) -> list[str]:
    """
    Parse all imports from file content.

    Args:
        content: Source code content.
        file_path: Path to the file (used to determine language).

    Returns:
        List of imported module paths/names (unresolved).
    """
    extension = Path(file_path).suffix.lower()
    language = EXTENSION_LANGUAGE.get(extension, "unknown")

    imports = set()

    if language in ("javascript", "typescript"):
        # ES6 imports
        for match in IMPORT_PATTERNS["es6_from"].finditer(content):
            imports.add(match.group(1))

        # CommonJS requires
        for match in IMPORT_PATTERNS["commonjs"].finditer(content):
            imports.add(match.group(1))

        # Dynamic imports
        for match in IMPORT_PATTERNS["dynamic"].finditer(content):
            imports.add(match.group(1))

    elif language == "python":
        # from X import Y
        for match in IMPORT_PATTERNS["python_from"].finditer(content):
            imports.add(match.group(1))

        # import X
        for match in IMPORT_PATTERNS["python_import"].finditer(content):
            imports.add(match.group(1))

    else:
        # Try all patterns for unknown languages
        for pattern in IMPORT_PATTERNS.values():
            for match in pattern.finditer(content):
                imports.add(match.group(1))

    return list(imports)


# =============================================================================
# Path Resolver
# =============================================================================


def resolve_import_path(
    import_path: str,
    from_file: str,
    indexed_files: dict[str, str],
) -> str | None:
    """
    Resolve an import path to an absolute file path.

    Args:
        import_path: The import path (e.g., './utils', '../services/auth', 'mypackage.module').
        from_file: The file containing the import (absolute path).
        indexed_files: Dict of {absolute_path: code_point_id} for all indexed files.

    Returns:
        Resolved absolute path if found in indexed files, None otherwise.
    """
    from_dir = Path(from_file).parent
    from_ext = Path(from_file).suffix.lower()

    # Handle Python dotted imports (e.g., 'deltacodecube.cube.code_point')
    if from_ext == ".py" and "." in import_path and not import_path.startswith("."):
        # Convert dots to path separators
        module_path = import_path.replace(".", "/")

        # Search in indexed files for matching Python module
        for indexed_path in indexed_files:
            if indexed_path.endswith(".py"):
                # Check if the indexed path ends with our module path
                # e.g., '/path/to/deltacodecube/cube/code_point.py' matches 'deltacodecube.cube.code_point'
                normalized = indexed_path.replace("\\", "/")
                if normalized.endswith(f"{module_path}.py"):
                    return indexed_path
                # Also check for __init__.py in package
                if normalized.endswith(f"{module_path}/__init__.py"):
                    return indexed_path

        return None

    # Skip external packages (not relative paths) for non-Python
    if not import_path.startswith(".") and not import_path.startswith("/"):
        # Could be a package like 'express', 'react', etc.
        return None

    # Try to resolve relative path
    if import_path.startswith("."):
        base_path = (from_dir / import_path).resolve()
    else:
        base_path = Path(import_path).resolve()

    # Try different extensions
    extensions_to_try = [
        "",  # Exact path
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".mjs",
        ".cjs",
        ".py",
        "/index.js",
        "/index.ts",
        "/index.jsx",
        "/index.tsx",
        "/__init__.py",
    ]

    for ext in extensions_to_try:
        candidate = str(base_path) + ext
        if candidate in indexed_files:
            return candidate

        # Also try without extension if file has one
        if base_path.suffix and str(base_path) in indexed_files:
            return str(base_path)

    return None


# =============================================================================
# Contract Detector
# =============================================================================


class ContractDetector:
    """
    Detects and manages contracts between CodePoints.
    """

    def __init__(self, conn: sqlite3.Connection):
        """
        Initialize ContractDetector with database connection.

        Args:
            conn: SQLite connection (should have dict_factory row_factory).
        """
        self.conn = conn

    def detect_contracts_for_file(
        self,
        file_path: str,
        content: str,
        code_point_id: str,
        indexed_files: dict[str, str],
        code_points: dict[str, Any],
    ) -> list[Contract]:
        """
        Detect all contracts (imports) from a single file.

        Args:
            file_path: Absolute path to the file.
            content: File content.
            code_point_id: ID of the CodePoint for this file.
            indexed_files: Dict of {absolute_path: code_point_id}.
            code_points: Dict of {code_point_id: CodePoint} for distance calculation.

        Returns:
            List of detected Contracts.
        """
        contracts = []

        # Parse imports from content
        imports = parse_imports(content, file_path)

        for import_path in imports:
            # Resolve to absolute path
            resolved_path = resolve_import_path(import_path, file_path, indexed_files)

            if resolved_path and resolved_path != file_path:
                callee_id = indexed_files.get(resolved_path)

                if callee_id:
                    # Calculate baseline distance
                    baseline_distance = 0.0
                    if code_point_id in code_points and callee_id in code_points:
                        caller_cp = code_points[code_point_id]
                        callee_cp = code_points[callee_id]
                        baseline_distance = float(
                            np.linalg.norm(caller_cp.position - callee_cp.position)
                        )

                    # Generate contract ID
                    contract_id = _generate_contract_id(code_point_id, callee_id)

                    contract = Contract(
                        id=contract_id,
                        caller_id=code_point_id,
                        callee_id=callee_id,
                        caller_path=file_path,
                        callee_path=resolved_path,
                        contract_type="import",
                        baseline_distance=baseline_distance,
                        created_at=datetime.now(),
                    )
                    contracts.append(contract)

        return contracts

    def detect_all_contracts(
        self,
        indexed_files: dict[str, str],
        code_points: dict[str, Any],
    ) -> list[Contract]:
        """
        Detect contracts between all indexed files.

        Args:
            indexed_files: Dict of {absolute_path: code_point_id}.
            code_points: Dict of {code_point_id: CodePoint}.

        Returns:
            List of all detected Contracts.
        """
        all_contracts = []

        for file_path, code_point_id in indexed_files.items():
            try:
                content = Path(file_path).read_text(encoding="utf-8")
                contracts = self.detect_contracts_for_file(
                    file_path=file_path,
                    content=content,
                    code_point_id=code_point_id,
                    indexed_files=indexed_files,
                    code_points=code_points,
                )
                all_contracts.extend(contracts)
            except Exception as e:
                logger.warning(f"Failed to detect contracts for {file_path}: {e}")

        return all_contracts

    def save_contract(self, contract: Contract) -> None:
        """Save a contract to the database."""
        self.conn.execute(
            """
            INSERT OR REPLACE INTO contracts (
                id, caller_id, callee_id, contract_type, baseline_distance, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                contract.id,
                contract.caller_id,
                contract.callee_id,
                contract.contract_type,
                contract.baseline_distance,
                contract.created_at.isoformat(),
            ),
        )
        self.conn.commit()

    def save_contracts(self, contracts: list[Contract]) -> int:
        """
        Save multiple contracts to the database.

        Returns:
            Number of contracts saved.
        """
        saved = 0
        for contract in contracts:
            try:
                self.save_contract(contract)
                saved += 1
            except Exception as e:
                logger.warning(f"Failed to save contract {contract.id}: {e}")

        logger.info(f"Saved {saved} contracts to database")
        return saved

    def get_contracts_for_file(
        self,
        file_path: str,
        direction: str = "both",
    ) -> list[Contract]:
        """
        Get all contracts involving a file.

        Args:
            file_path: Absolute path to the file.
            direction: 'incoming' (where file is callee),
                      'outgoing' (where file is caller),
                      'both' (all).

        Returns:
            List of Contracts.
        """
        # First get the code_point_id for this file
        cursor = self.conn.execute(
            "SELECT id FROM code_points WHERE file_path = ?",
            (file_path,),
        )
        row = cursor.fetchone()
        if not row:
            return []

        code_point_id = row["id"]

        contracts = []

        if direction in ("outgoing", "both"):
            cursor = self.conn.execute(
                """
                SELECT c.*, cp1.file_path as caller_path, cp2.file_path as callee_path
                FROM contracts c
                JOIN code_points cp1 ON c.caller_id = cp1.id
                JOIN code_points cp2 ON c.callee_id = cp2.id
                WHERE c.caller_id = ?
                """,
                (code_point_id,),
            )
            for row in cursor.fetchall():
                contracts.append(self._row_to_contract(row))

        if direction in ("incoming", "both"):
            cursor = self.conn.execute(
                """
                SELECT c.*, cp1.file_path as caller_path, cp2.file_path as callee_path
                FROM contracts c
                JOIN code_points cp1 ON c.caller_id = cp1.id
                JOIN code_points cp2 ON c.callee_id = cp2.id
                WHERE c.callee_id = ?
                """,
                (code_point_id,),
            )
            for row in cursor.fetchall():
                # Avoid duplicates if direction is 'both'
                if not any(c.id == row["id"] for c in contracts):
                    contracts.append(self._row_to_contract(row))

        return contracts

    def get_all_contracts(self, limit: int = 100) -> list[Contract]:
        """Get all contracts from database."""
        cursor = self.conn.execute(
            """
            SELECT c.*, cp1.file_path as caller_path, cp2.file_path as callee_path
            FROM contracts c
            JOIN code_points cp1 ON c.caller_id = cp1.id
            JOIN code_points cp2 ON c.callee_id = cp2.id
            ORDER BY c.created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [self._row_to_contract(row) for row in cursor.fetchall()]

    def get_contract_stats(self) -> dict[str, Any]:
        """Get statistics about contracts."""
        cursor = self.conn.execute("SELECT COUNT(*) as count FROM contracts")
        total = cursor.fetchone()["count"]

        cursor = self.conn.execute(
            """
            SELECT contract_type, COUNT(*) as count
            FROM contracts
            GROUP BY contract_type
            """
        )
        by_type = {row["contract_type"]: row["count"] for row in cursor.fetchall()}

        cursor = self.conn.execute(
            """
            SELECT AVG(baseline_distance) as avg_dist,
                   MIN(baseline_distance) as min_dist,
                   MAX(baseline_distance) as max_dist
            FROM contracts
            """
        )
        row = cursor.fetchone()

        return {
            "total_contracts": total,
            "by_type": by_type,
            "avg_baseline_distance": row["avg_dist"] or 0,
            "min_baseline_distance": row["min_dist"] or 0,
            "max_baseline_distance": row["max_dist"] or 0,
        }

    def _row_to_contract(self, row: dict[str, Any]) -> Contract:
        """Convert database row to Contract."""
        return Contract(
            id=row["id"],
            caller_id=row["caller_id"],
            callee_id=row["callee_id"],
            caller_path=row["caller_path"],
            callee_path=row["callee_path"],
            contract_type=row["contract_type"],
            baseline_distance=row["baseline_distance"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )


def _generate_contract_id(caller_id: str, callee_id: str) -> str:
    """Generate unique ID for a contract."""
    combined = f"{caller_id}:{callee_id}"
    return hashlib.md5(combined.encode("utf-8")).hexdigest()[:12]
