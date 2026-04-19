"""
API Surface Analysis for DeltaCodeCube.

Analyzes the public API surface of each module:
- What functions/classes are exported
- What is imported by other files
- API stability metrics
- Breaking change detection

Helps understand:
- Which functions are public vs private
- API surface area (attack surface for changes)
- Modules with large vs small APIs
"""

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jig.engines.dcc.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ExportedSymbol:
    """A symbol exported from a module."""
    name: str
    symbol_type: str  # "function", "class", "constant", "default"
    file_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.symbol_type,
        }


@dataclass
class ModuleSurface:
    """API surface for a module."""
    file_path: str
    file_name: str
    exports: list[ExportedSymbol]
    export_count: int
    imported_by: list[str]  # Files that import this module
    import_count: int
    surface_area: float  # Normalized 0-1
    is_public: bool  # Has exports
    stability_risk: str  # "low", "medium", "high"

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "file_name": self.file_name,
            "export_count": self.export_count,
            "exports": [e.to_dict() for e in self.exports],
            "import_count": self.import_count,
            "imported_by": [Path(p).name for p in self.imported_by],
            "surface_area": round(self.surface_area, 3),
            "is_public": self.is_public,
            "stability_risk": self.stability_risk,
        }


class APISurfaceAnalyzer:
    """
    Analyzes API surface of modules.
    """

    def __init__(self, conn: sqlite3.Connection):
        """Initialize with database connection."""
        self.conn = conn

    def analyze(self) -> dict[str, Any]:
        """
        Analyze API surface of all modules.

        Returns:
            Complete surface analysis.
        """
        surfaces = []
        max_exports = 0
        max_imports = 0

        # First pass: extract exports and count dependencies
        cursor = self.conn.execute("SELECT file_path FROM code_points")
        file_paths = [row["file_path"] for row in cursor.fetchall()]

        export_data = {}
        for file_path in file_paths:
            try:
                content = Path(file_path).read_text(encoding="utf-8")
                exports = self._extract_exports(content, file_path)
                export_data[file_path] = exports
                max_exports = max(max_exports, len(exports))
            except Exception as e:
                logger.debug(f"Could not analyze {file_path}: {e}")
                export_data[file_path] = []

        # Get import relationships from contracts
        import_counts = {}
        imported_by = {}

        cursor = self.conn.execute("""
            SELECT cp1.file_path as caller, cp2.file_path as callee
            FROM contracts c
            JOIN code_points cp1 ON c.caller_id = cp1.id
            JOIN code_points cp2 ON c.callee_id = cp2.id
        """)

        for row in cursor.fetchall():
            callee = row["callee"]
            caller = row["caller"]

            import_counts[callee] = import_counts.get(callee, 0) + 1
            max_imports = max(max_imports, import_counts[callee])

            if callee not in imported_by:
                imported_by[callee] = []
            imported_by[callee].append(caller)

        # Build surface objects
        for file_path in file_paths:
            exports = export_data.get(file_path, [])
            imp_count = import_counts.get(file_path, 0)
            imp_by = imported_by.get(file_path, [])

            # Calculate surface area (normalized)
            export_norm = len(exports) / max_exports if max_exports > 0 else 0
            import_norm = imp_count / max_imports if max_imports > 0 else 0
            surface_area = (export_norm + import_norm) / 2

            # Determine stability risk
            if imp_count > 5 and len(exports) > 5:
                stability_risk = "high"
            elif imp_count > 2 or len(exports) > 3:
                stability_risk = "medium"
            else:
                stability_risk = "low"

            surfaces.append(ModuleSurface(
                file_path=file_path,
                file_name=Path(file_path).name,
                exports=exports,
                export_count=len(exports),
                imported_by=imp_by,
                import_count=imp_count,
                surface_area=surface_area,
                is_public=len(exports) > 0,
                stability_risk=stability_risk,
            ))

        # Sort by surface area
        surfaces.sort(key=lambda s: s.surface_area, reverse=True)

        # Summary
        total_exports = sum(s.export_count for s in surfaces)
        public_modules = sum(1 for s in surfaces if s.is_public)
        high_risk = [s for s in surfaces if s.stability_risk == "high"]

        return {
            "total_modules": len(surfaces),
            "public_modules": public_modules,
            "private_modules": len(surfaces) - public_modules,
            "total_exports": total_exports,
            "avg_exports": round(total_exports / len(surfaces), 1) if surfaces else 0,
            "high_risk_modules": len(high_risk),
            "high_risk": [s.to_dict() for s in high_risk],
            "top_surface": [s.to_dict() for s in surfaces[:10]],
            "all_modules": [s.to_dict() for s in surfaces],
        }

    def _extract_exports(self, content: str, file_path: str) -> list[ExportedSymbol]:
        """Extract exported symbols from code."""
        exports = []
        extension = Path(file_path).suffix

        if extension in [".js", ".ts", ".jsx", ".tsx", ".mjs"]:
            exports.extend(self._extract_js_exports(content, file_path))
        elif extension in [".py"]:
            exports.extend(self._extract_python_exports(content, file_path))

        return exports

    def _extract_js_exports(self, content: str, file_path: str) -> list[ExportedSymbol]:
        """Extract JavaScript/TypeScript exports."""
        exports = []

        # export function name
        for match in re.finditer(r'export\s+(?:async\s+)?function\s+(\w+)', content):
            exports.append(ExportedSymbol(
                name=match.group(1),
                symbol_type="function",
                file_path=file_path,
            ))

        # export class name
        for match in re.finditer(r'export\s+class\s+(\w+)', content):
            exports.append(ExportedSymbol(
                name=match.group(1),
                symbol_type="class",
                file_path=file_path,
            ))

        # export const/let/var name
        for match in re.finditer(r'export\s+(?:const|let|var)\s+(\w+)', content):
            exports.append(ExportedSymbol(
                name=match.group(1),
                symbol_type="constant",
                file_path=file_path,
            ))

        # export default
        if re.search(r'export\s+default', content):
            exports.append(ExportedSymbol(
                name="default",
                symbol_type="default",
                file_path=file_path,
            ))

        # export { name1, name2 }
        for match in re.finditer(r'export\s*\{([^}]+)\}', content):
            names = re.findall(r'(\w+)(?:\s+as\s+\w+)?', match.group(1))
            for name in names:
                exports.append(ExportedSymbol(
                    name=name,
                    symbol_type="re-export",
                    file_path=file_path,
                ))

        # module.exports
        if re.search(r'module\.exports\s*=', content):
            exports.append(ExportedSymbol(
                name="module.exports",
                symbol_type="commonjs",
                file_path=file_path,
            ))

        # exports.name
        for match in re.finditer(r'exports\.(\w+)\s*=', content):
            exports.append(ExportedSymbol(
                name=match.group(1),
                symbol_type="commonjs",
                file_path=file_path,
            ))

        return exports

    def _extract_python_exports(self, content: str, file_path: str) -> list[ExportedSymbol]:
        """Extract Python exports (__all__ and public definitions)."""
        exports = []

        # Check for __all__
        all_match = re.search(r'__all__\s*=\s*\[(.*?)\]', content, re.DOTALL)
        if all_match:
            names = re.findall(r'["\'](\w+)["\']', all_match.group(1))
            for name in names:
                exports.append(ExportedSymbol(
                    name=name,
                    symbol_type="explicit",
                    file_path=file_path,
                ))
            return exports  # __all__ is definitive

        # Otherwise, public definitions (no leading underscore)
        for match in re.finditer(r'^def\s+([a-zA-Z]\w*)\s*\(', content, re.MULTILINE):
            exports.append(ExportedSymbol(
                name=match.group(1),
                symbol_type="function",
                file_path=file_path,
            ))

        for match in re.finditer(r'^class\s+([a-zA-Z]\w*)', content, re.MULTILINE):
            exports.append(ExportedSymbol(
                name=match.group(1),
                symbol_type="class",
                file_path=file_path,
            ))

        return exports

    def get_module_surface(self, file_path: str) -> dict[str, Any] | None:
        """Get surface analysis for a specific module."""
        result = self.analyze()

        for module in result["all_modules"]:
            if module["file_path"] == file_path or module["file_path"].endswith(file_path):
                return module

        return None


def analyze_api_surface(conn: sqlite3.Connection) -> dict[str, Any]:
    """
    Analyze API surface of the codebase.

    Args:
        conn: Database connection.

    Returns:
        Surface analysis results.
    """
    analyzer = APISurfaceAnalyzer(conn)
    return analyzer.analyze()
