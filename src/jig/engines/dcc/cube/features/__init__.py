"""
Feature extractors for DeltaCodeCube.

Core features (86D total):
- Lexical: TF-IDF unigrams + bigrams (65 dimensions)
- Structural: Basic + Halstead + Coupling (16 dimensions)
- Semantic: Domain classification (5 dimensions, configurable)

Optional features:
- Temporal: Git history metrics (5 dimensions) - requires git
"""

from jig.engines.dcc.cube.features.lexical import extract_lexical_features
from jig.engines.dcc.cube.features.structural import extract_structural_features
from jig.engines.dcc.cube.features.semantic import extract_semantic_features
from jig.engines.dcc.cube.features.temporal import extract_temporal_features

__all__ = [
    "extract_lexical_features",
    "extract_structural_features",
    "extract_semantic_features",
    "extract_temporal_features",
]
