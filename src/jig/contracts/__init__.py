"""jig public contracts — stable, semver'd interfaces.

This package defines the data types and protocols that decouple jig's graph
engine from any specific code-analysis backend (e.g. delta-cube).

Public symbols:
    CodeAnalysisProvider   — Protocol any backend must implement
    NullProvider           — No-op implementation used when no backend is registered
    Tension                — A structural dependency tension
    Smell                  — A code smell finding
    SmellSummary           — Aggregate smell report
    DebtReport             — Codebase debt grade and score
    ImpactReport           — Wave/impact simulation result
    SecurityReport         — Security findings summary
    StatsReport            — High-level codebase statistics
"""

from .code_analysis import (
    CodeAnalysisProvider,
    DebtReport,
    ImpactReport,
    NullProvider,
    SecurityReport,
    Smell,
    SmellSummary,
    StatsReport,
    Tension,
)

__all__ = [
    "CodeAnalysisProvider",
    "DebtReport",
    "ImpactReport",
    "NullProvider",
    "SecurityReport",
    "Smell",
    "SmellSummary",
    "StatsReport",
    "Tension",
]
