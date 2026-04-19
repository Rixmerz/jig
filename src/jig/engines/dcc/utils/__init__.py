"""Utility functions for BigContext MCP."""

from jig.engines.dcc.utils.errors import BigContextError, DocumentNotFoundError, ParseError
from jig.engines.dcc.utils.logger import get_logger


def convert_numpy_types(obj):
    """Recursively convert numpy types to Python natives for JSON serialization."""
    import numpy as np

    if isinstance(obj, dict):
        return {k: convert_numpy_types(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return type(obj)(convert_numpy_types(v) for v in obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


__all__ = ["get_logger", "BigContextError", "DocumentNotFoundError", "ParseError", "convert_numpy_types"]
