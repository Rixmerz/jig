"""
Visualization modules for DeltaCodeCube.

Generates HTML visualizations for code analysis:
- Timeline: Evolution of code over time
- Dependency Matrix: Interactive dependency grid
- Heat Map: Activity and hotspot visualization
- Architecture: Module architecture diagram
"""

from jig.engines.dcc.cube.visualizations.timeline import generate_timeline
from jig.engines.dcc.cube.visualizations.matrix import generate_dependency_matrix
from jig.engines.dcc.cube.visualizations.heatmap import generate_heatmap
from jig.engines.dcc.cube.visualizations.architecture import generate_architecture

__all__ = [
    "generate_timeline",
    "generate_dependency_matrix",
    "generate_heatmap",
    "generate_architecture",
]
