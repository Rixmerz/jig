"""
Suggestions - Generate fix suggestions for detected tensions.

This module provides context and analysis to help LLMs (like Claude)
generate intelligent fix suggestions when code changes cause tensions.
"""

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from jig.engines.dcc.cube.delta import Delta
from jig.engines.dcc.cube.tension import Tension
from jig.engines.dcc.utils.logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# Change Type Analysis
# =============================================================================

@dataclass
class ChangeAnalysis:
    """Analysis of what type of change occurred."""

    change_type: str  # 'structural', 'lexical', 'semantic', 'mixed'
    severity: str  # 'low', 'medium', 'high'
    description: str
    likely_causes: list[str]
    suggested_actions: list[str]


def analyze_change_type(delta: dict[str, Any]) -> ChangeAnalysis:
    """
    Analyze what type of change occurred based on delta.

    Args:
        delta: Delta dictionary from cube.get_deltas() or reindex result.

    Returns:
        ChangeAnalysis with type, severity, and suggestions.
    """
    lexical = delta.get("lexical_change", 0)
    structural = delta.get("structural_change", 0)
    semantic = delta.get("semantic_change", 0)
    dominant = delta.get("dominant_change", "unknown")
    magnitude = delta.get("movement_magnitude", 0)

    # Determine severity based on magnitude
    if magnitude > 1.0:
        severity = "high"
    elif magnitude > 0.5:
        severity = "medium"
    else:
        severity = "low"

    # Analyze based on dominant change
    if dominant == "structural":
        return ChangeAnalysis(
            change_type="structural",
            severity=severity,
            description=(
                f"Structural change detected (magnitude: {structural:.3f}). "
                "The code structure has changed significantly."
            ),
            likely_causes=[
                "Added or removed functions/methods",
                "Changed function signatures (parameters, return types)",
                "Modified class structure",
                "Changed import/export patterns",
                "Increased/decreased code complexity",
            ],
            suggested_actions=[
                "Review all callers for signature compatibility",
                "Check if new parameters have default values",
                "Verify export names haven't changed",
                "Update type definitions if using TypeScript",
                "Run tests to catch breaking changes",
            ],
        )

    elif dominant == "lexical":
        return ChangeAnalysis(
            change_type="lexical",
            severity=severity,
            description=(
                f"Lexical change detected (magnitude: {lexical:.3f}). "
                "Terminology and naming conventions have changed."
            ),
            likely_causes=[
                "Renamed variables, functions, or classes",
                "Changed string literals or constants",
                "Modified comments or documentation",
                "Added new domain-specific terms",
                "Refactored naming conventions",
            ],
            suggested_actions=[
                "Search for old names in dependent files",
                "Update imports if exports were renamed",
                "Check for hardcoded references to old names",
                "Update documentation to reflect new names",
                "Consider using find-and-replace across codebase",
            ],
        )

    elif dominant == "semantic":
        return ChangeAnalysis(
            change_type="semantic",
            severity=severity,
            description=(
                f"Semantic change detected (magnitude: {semantic:.3f}). "
                "The functional domain/purpose of the code may have shifted."
            ),
            likely_causes=[
                "Code now serves a different purpose",
                "Added functionality from a different domain",
                "Major refactoring changed code's responsibility",
                "Merged functionality from multiple domains",
            ],
            suggested_actions=[
                "Review if file should be split into multiple files",
                "Check if dependent files expect the old behavior",
                "Consider if this file is still the right dependency",
                "Update architectural documentation",
                "Evaluate if domain boundaries are violated",
            ],
        )

    else:
        return ChangeAnalysis(
            change_type="mixed",
            severity=severity,
            description=(
                f"Mixed change detected (total magnitude: {magnitude:.3f}). "
                "Multiple aspects of the code have changed."
            ),
            likely_causes=[
                "Major refactoring or rewrite",
                "Feature addition with new patterns",
                "Migration to different coding style",
            ],
            suggested_actions=[
                "Carefully review all dependent files",
                "Consider incremental migration strategy",
                "Run full test suite",
                "Document the changes thoroughly",
            ],
        )


# =============================================================================
# Code Snippet Extraction
# =============================================================================


def extract_relevant_snippets(
    file_path: str,
    max_lines: int = 50,
) -> dict[str, Any]:
    """
    Extract relevant code snippets from a file.

    Extracts:
    - Imports/requires
    - Exports
    - Function signatures
    - Class definitions

    Args:
        file_path: Path to the file.
        max_lines: Maximum lines to include in full content.

    Returns:
        Dictionary with extracted snippets.
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return {"error": f"File not found: {file_path}"}

        content = path.read_text(encoding="utf-8")
        lines = content.split("\n")
        extension = path.suffix.lower()

    except Exception as e:
        return {"error": str(e)}

    snippets = {
        "file_name": path.name,
        "total_lines": len(lines),
        "imports": [],
        "exports": [],
        "functions": [],
        "classes": [],
    }

    # Extract imports
    import_patterns = [
        r"^import\s+.+",  # ES6 import
        r"^const\s+\w+\s*=\s*require\(.+\)",  # CommonJS
        r"^from\s+\S+\s+import",  # Python
        r"^import\s+\w+",  # Python simple
    ]
    for i, line in enumerate(lines):
        for pattern in import_patterns:
            if re.match(pattern, line.strip()):
                snippets["imports"].append({
                    "line": i + 1,
                    "code": line.strip(),
                })
                break

    # Extract exports
    export_patterns = [
        r"^export\s+(default\s+)?(function|class|const|let|var)",
        r"^export\s+\{",
        r"^module\.exports\s*=",
        r"^exports\.\w+\s*=",
    ]
    for i, line in enumerate(lines):
        for pattern in export_patterns:
            if re.match(pattern, line.strip()):
                snippets["exports"].append({
                    "line": i + 1,
                    "code": line.strip()[:100],  # Truncate long lines
                })
                break

    # Extract function signatures
    function_patterns = [
        r"^(async\s+)?function\s+(\w+)\s*\([^)]*\)",  # JS function
        r"^(export\s+)?(async\s+)?function\s+(\w+)",  # exported function
        r"^const\s+(\w+)\s*=\s*(async\s+)?\([^)]*\)\s*=>",  # arrow function
        r"^def\s+(\w+)\s*\([^)]*\)",  # Python def
        r"^\s*(async\s+)?(\w+)\s*\([^)]*\)\s*\{",  # method in class
    ]
    for i, line in enumerate(lines):
        for pattern in function_patterns:
            match = re.match(pattern, line.strip())
            if match:
                snippets["functions"].append({
                    "line": i + 1,
                    "code": line.strip()[:100],
                })
                break

    # Extract class definitions
    class_patterns = [
        r"^(export\s+)?class\s+(\w+)",
        r"^class\s+(\w+)",
    ]
    for i, line in enumerate(lines):
        for pattern in class_patterns:
            match = re.match(pattern, line.strip())
            if match:
                snippets["classes"].append({
                    "line": i + 1,
                    "code": line.strip()[:100],
                })
                break

    # Include truncated content if small enough
    if len(lines) <= max_lines:
        snippets["full_content"] = content
    else:
        snippets["content_preview"] = "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines)"

    return snippets


# =============================================================================
# Suggestion Generator
# =============================================================================


class SuggestionGenerator:
    """
    Generates fix suggestions for tensions.
    """

    def __init__(self, conn: sqlite3.Connection):
        """
        Initialize SuggestionGenerator.

        Args:
            conn: SQLite connection.
        """
        self.conn = conn

    def generate_suggestion_context(
        self,
        tension_id: str | None = None,
        file_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Generate rich context for LLM to provide fix suggestions.

        Can be called with either a tension_id (to analyze specific tension)
        or a file_path (to analyze latest delta for that file).

        Args:
            tension_id: ID of a specific tension.
            file_path: Path to file to analyze.

        Returns:
            Rich context dictionary for LLM suggestion generation.
        """
        context = {
            "generated_at": datetime.now().isoformat(),
            "type": "fix_suggestion_context",
        }

        if tension_id:
            # Get tension details
            cursor = self.conn.execute(
                """
                SELECT t.*, c.baseline_distance, c.caller_id, c.callee_id,
                       d.movement_magnitude, d.lexical_change, d.structural_change,
                       d.semantic_change, d.dominant_change,
                       cp1.file_path as caller_path, cp2.file_path as callee_path
                FROM tensions t
                JOIN contracts c ON t.contract_id = c.id
                JOIN deltas d ON t.delta_id = d.id
                JOIN code_points cp1 ON c.caller_id = cp1.id
                JOIN code_points cp2 ON c.callee_id = cp2.id
                WHERE t.id = ?
                """,
                (tension_id,),
            )
            row = cursor.fetchone()

            if not row:
                return {"error": f"Tension not found: {tension_id}"}

            # Build delta dict for analysis
            delta_dict = {
                "movement_magnitude": row["movement_magnitude"],
                "lexical_change": row["lexical_change"],
                "structural_change": row["structural_change"],
                "semantic_change": row["semantic_change"],
                "dominant_change": row["dominant_change"],
            }

            # Analyze change type
            change_analysis = analyze_change_type(delta_dict)

            # Extract code snippets
            caller_snippets = extract_relevant_snippets(row["caller_path"])
            callee_snippets = extract_relevant_snippets(row["callee_path"])

            context["tension"] = {
                "id": tension_id,
                "status": row["status"],
                "baseline_distance": row["baseline_distance"],
                "tension_magnitude": row["tension_magnitude"],
                "suggested_action": row["suggested_action"],
            }

            context["delta"] = delta_dict

            context["change_analysis"] = {
                "type": change_analysis.change_type,
                "severity": change_analysis.severity,
                "description": change_analysis.description,
                "likely_causes": change_analysis.likely_causes,
                "suggested_actions": change_analysis.suggested_actions,
            }

            context["affected_files"] = {
                "caller": {
                    "path": row["caller_path"],
                    "name": Path(row["caller_path"]).name,
                    "role": "depends_on_changed_file",
                    "snippets": caller_snippets,
                },
                "callee": {
                    "path": row["callee_path"],
                    "name": Path(row["callee_path"]).name,
                    "role": "changed_file",
                    "snippets": callee_snippets,
                },
            }

            context["fix_guidance"] = self._generate_fix_guidance(
                change_analysis, row["caller_path"], row["callee_path"]
            )

        elif file_path:
            # Get latest delta for file
            resolved_path = str(Path(file_path).resolve())

            cursor = self.conn.execute(
                """
                SELECT d.*, cp.file_path
                FROM deltas d
                JOIN code_points cp ON d.code_point_id = cp.id
                WHERE cp.file_path = ?
                ORDER BY d.created_at DESC
                LIMIT 1
                """,
                (resolved_path,),
            )
            row = cursor.fetchone()

            if not row:
                return {"error": f"No deltas found for file: {file_path}"}

            delta_dict = {
                "movement_magnitude": row["movement_magnitude"],
                "lexical_change": row["lexical_change"],
                "structural_change": row["structural_change"],
                "semantic_change": row["semantic_change"],
                "dominant_change": row["dominant_change"],
            }

            change_analysis = analyze_change_type(delta_dict)
            file_snippets = extract_relevant_snippets(resolved_path)

            context["file"] = {
                "path": resolved_path,
                "name": Path(resolved_path).name,
                "snippets": file_snippets,
            }

            context["delta"] = delta_dict

            context["change_analysis"] = {
                "type": change_analysis.change_type,
                "severity": change_analysis.severity,
                "description": change_analysis.description,
                "likely_causes": change_analysis.likely_causes,
                "suggested_actions": change_analysis.suggested_actions,
            }

            # Get dependent files
            cursor = self.conn.execute(
                """
                SELECT cp.file_path, c.baseline_distance
                FROM contracts c
                JOIN code_points cp ON c.caller_id = cp.id
                WHERE c.callee_id = (SELECT id FROM code_points WHERE file_path = ?)
                """,
                (resolved_path,),
            )

            dependents = []
            for dep_row in cursor.fetchall():
                dependents.append({
                    "path": dep_row["file_path"],
                    "name": Path(dep_row["file_path"]).name,
                    "baseline_distance": dep_row["baseline_distance"],
                })

            context["dependent_files"] = dependents
            context["dependent_count"] = len(dependents)

        else:
            return {"error": "Either tension_id or file_path must be provided"}

        return context

    def _generate_fix_guidance(
        self,
        analysis: ChangeAnalysis,
        caller_path: str,
        callee_path: str,
    ) -> dict[str, Any]:
        """Generate specific fix guidance based on analysis."""
        caller_name = Path(caller_path).name
        callee_name = Path(callee_path).name

        guidance = {
            "summary": (
                f"The file '{callee_name}' has changed ({analysis.change_type} change, "
                f"{analysis.severity} severity). This may affect '{caller_name}' which depends on it."
            ),
            "steps": [],
            "warnings": [],
        }

        if analysis.change_type == "structural":
            guidance["steps"] = [
                f"1. Open {caller_name} and locate imports from {callee_name}",
                f"2. Check if any imported functions/classes have changed signatures",
                f"3. Look for TypeScript/JSDoc errors that indicate type mismatches",
                f"4. Update function calls to match new signatures",
                f"5. Run tests to verify the integration still works",
            ]
            guidance["warnings"] = [
                "Function parameters may have changed",
                "Return types may be different",
                "Some exports may have been removed or renamed",
            ]

        elif analysis.change_type == "lexical":
            guidance["steps"] = [
                f"1. Check if any exports from {callee_name} were renamed",
                f"2. Search {caller_name} for references to old names",
                f"3. Update import statements if needed",
                f"4. Update any string references to renamed items",
            ]
            guidance["warnings"] = [
                "Variable or function names may have changed",
                "String constants may be different",
            ]

        elif analysis.change_type == "semantic":
            guidance["steps"] = [
                f"1. Review the purpose of {callee_name} - it may have changed",
                f"2. Determine if {caller_name} should still depend on it",
                f"3. Consider if a different module better serves the need",
                f"4. Update the integration approach if the domain shifted",
            ]
            guidance["warnings"] = [
                "The file's purpose may have fundamentally changed",
                "Consider architectural implications",
            ]

        return guidance
