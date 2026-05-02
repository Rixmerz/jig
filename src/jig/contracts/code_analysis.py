"""CodeAnalysisProvider Protocol — public, semver'd API.

This module defines the stable contract between jig's graph engine and any
code-analysis backend. The interface is intentionally narrow: it covers only
the operations that jig's workflow engine actually needs, not every feature a
backend might expose.

Versioning: this file follows the same semver as jig-mcp. Breaking changes
require a major bump. Additive changes (new optional methods, new fields with
defaults) require a minor bump.

Adapter packages (e.g. jig-delta-cube) implement ``CodeAnalysisProvider``
and register themselves via the ``jig.providers`` entry-point group so that
``provider_registry.get_provider()`` can discover them at runtime.

When no adapter is installed, jig automatically falls back to
``NullProvider``, which returns empty/safe results for every method.
This satisfies RF-004 (graceful degrade without a provider).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Tension:
    """A structural tension between two code locations.

    A tension represents a problematic dependency, coupling, or architectural
    drift detected between ``source`` and ``target``.
    """
    type: str                      # e.g. "circular_dependency", "high_coupling"
    severity: str                  # "low" | "medium" | "high" | "critical"
    source: str                    # Source file or module path
    target: str = ""               # Target file or module (may be empty)
    description: str = ""
    status: str = "detected"       # "detected" | "resolved" | "suppressed"


@dataclass(frozen=True)
class Smell:
    """A single code smell finding."""
    type: str                      # e.g. "god_file", "dead_code_candidate"
    severity: str                  # "low" | "medium" | "high" | "critical"
    file: str                      # Affected file path
    description: str = ""


@dataclass(frozen=True)
class SmellSummary:
    """Aggregate smell report for a codebase (or a set of files)."""
    total: int = 0
    by_severity: dict[str, int] = field(default_factory=dict)
    by_type: dict[str, int] = field(default_factory=dict)
    smells: list[Smell] = field(default_factory=list)


@dataclass(frozen=True)
class DebtReport:
    """Technical debt grade and score for the codebase."""
    grade: str = "?"               # "A" | "B" | "C" | "D" | "F"
    score: float = 0.0             # 0-100
    hotspot_count: int = 0         # Files with score > 60


@dataclass(frozen=True)
class SecurityReport:
    """Summary of open security findings."""
    total: int = 0
    open_count: int = 0
    by_severity: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class StatsReport:
    """High-level codebase statistics."""
    total_files: int = 0
    grade: str = "?"
    score: float = 0.0


@dataclass(frozen=True)
class ImpactReport:
    """Impact simulation result (wave analysis)."""
    files_at_risk: int = 0
    risk_threshold: str = "medium"
    changed_files_analyzed: int = 0
    details: list[dict] = field(default_factory=list)   # [{file, risk, reason, from}]
    review_order: list[str] = field(default_factory=list)
    message: str = ""


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class CodeAnalysisProvider(Protocol):
    """Protocol for code-analysis backends used by jig's graph engine.

    Implementations must be importable Python objects registered via the
    ``jig.providers`` entry-point group.  The registry instantiates the class
    with no arguments.

    All methods are async and return typed dataclass instances (never raw
    dicts) so that callers are insulated from MCP response shapes.

    Methods that accept ``project_dir`` receive the absolute path to the
    project root as a string.
    """

    # ------------------------------------------------------------------
    # Availability / lifecycle
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """Return True if this backend is reachable (e.g. MCP proxy connected).

        Called synchronously from non-async contexts such as config rendering.
        Implementations should be fast (no network I/O).
        """
        ...

    # ------------------------------------------------------------------
    # Codebase-level queries
    # ------------------------------------------------------------------

    async def get_stats(self, project_dir: str) -> StatsReport:
        """Return high-level statistics for the indexed codebase."""
        ...

    async def detect_smells(
        self,
        project_dir: str,
        *,
        summary_only: bool = True,
        min_severity: str | None = None,
    ) -> SmellSummary:
        """Return detected code smells.

        Args:
            project_dir: Project root.
            summary_only: When True, only aggregate counts are populated
                (``smells`` list will be empty). Faster and cheaper.
            min_severity: Optional lower bound filter ("low" | "medium" |
                "high" | "critical"). Applies server-side when supported.
        """
        ...

    async def get_tensions(
        self,
        project_dir: str,
        *,
        limit: int = 20,
        status: str = "detected",
    ) -> list[Tension]:
        """Return structural tensions in the codebase."""
        ...

    async def get_debt(self, project_dir: str) -> DebtReport:
        """Return the technical debt report."""
        ...

    async def get_security_report(self, project_dir: str) -> SecurityReport:
        """Return a summary of open security findings."""
        ...

    # ------------------------------------------------------------------
    # Impact simulation
    # ------------------------------------------------------------------

    async def simulate_wave(
        self,
        project_dir: str,
        file_path: str,
        *,
        max_hops: int = 3,
    ) -> ImpactReport:
        """Simulate the impact propagation from a single changed file.

        Returns an ImpactReport describing which other files are at risk.
        """
        ...

    async def suggest_fix(self, project_dir: str, file_path: str) -> str:
        """Return a human-readable fix suggestion for the top issue in ``file_path``.

        Returns an empty string if no suggestion is available.
        """
        ...

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    async def index_file(self, project_dir: str, file_path: str) -> bool:
        """Index a single file. Returns True on success."""
        ...

    async def index_directory(
        self,
        project_dir: str,
        *,
        patterns: list[str] | None = None,
    ) -> bool:
        """Index an entire directory. Returns True on success."""
        ...

    async def list_indexed_files(self, project_dir: str) -> list[str]:
        """Return a list of absolute file paths currently indexed."""
        ...


# ---------------------------------------------------------------------------
# NullProvider — graceful degrade (RF-004)
# ---------------------------------------------------------------------------

class NullProvider:
    """No-op CodeAnalysisProvider used when no real backend is configured.

    Every method returns an empty/safe result so the rest of jig can operate
    without branching on whether a provider exists.
    """

    def is_available(self) -> bool:
        return False

    async def get_stats(self, project_dir: str) -> StatsReport:
        return StatsReport()

    async def detect_smells(
        self,
        project_dir: str,
        *,
        summary_only: bool = True,
        min_severity: str | None = None,
    ) -> SmellSummary:
        return SmellSummary()

    async def get_tensions(
        self,
        project_dir: str,
        *,
        limit: int = 20,
        status: str = "detected",
    ) -> list[Tension]:
        return []

    async def get_debt(self, project_dir: str) -> DebtReport:
        return DebtReport()

    async def get_security_report(self, project_dir: str) -> SecurityReport:
        return SecurityReport()

    async def simulate_wave(
        self,
        project_dir: str,
        file_path: str,
        *,
        max_hops: int = 3,
    ) -> ImpactReport:
        return ImpactReport()

    async def suggest_fix(self, project_dir: str, file_path: str) -> str:
        return ""

    async def index_file(self, project_dir: str, file_path: str) -> bool:
        return False

    async def index_directory(
        self,
        project_dir: str,
        *,
        patterns: list[str] | None = None,
    ) -> bool:
        return False

    async def list_indexed_files(self, project_dir: str) -> list[str]:
        return []
