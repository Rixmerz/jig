"""
DeltaCodeCube - Sistema de indexación multidimensional para código.

Representa código como puntos en espacio 3D (Lexical, Structural, Semantic)
para búsqueda multidimensional y detección de impacto de cambios.
"""

from jig.engines.dcc.cube.code_point import CodePoint
from jig.engines.dcc.cube.contracts import Contract, ContractDetector
from jig.engines.dcc.cube.cube import DeltaCodeCube
from jig.engines.dcc.cube.delta import Delta, DeltaTracker, create_delta
from jig.engines.dcc.cube.tension import Tension, TensionDetector
from jig.engines.dcc.cube.suggestions import (
    ChangeAnalysis,
    SuggestionGenerator,
    analyze_change_type,
    extract_relevant_snippets,
)

__all__ = [
    "ChangeAnalysis",
    "CodePoint",
    "Contract",
    "ContractDetector",
    "Delta",
    "DeltaCodeCube",
    "DeltaTracker",
    "SuggestionGenerator",
    "Tension",
    "TensionDetector",
    "analyze_change_type",
    "create_delta",
    "extract_relevant_snippets",
]
