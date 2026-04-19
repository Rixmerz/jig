"""
Structural feature extractor for code files.

Extracts 16 structural features using regex/heuristics (no AST required):

Basic metrics (8):
1. loc_normalized: Lines of code (normalized to 500)
2. num_functions: Number of function definitions
3. num_classes: Number of class definitions
4. num_imports: Number of import statements
5. avg_indent: Average indentation depth
6. comment_ratio: Ratio of comment lines
7. cyclomatic_estimate: Estimated cyclomatic complexity
8. export_count: Number of exports

Halstead metrics (5) - Classic software complexity metrics:
9. halstead_vocabulary: Unique operators + operands (normalized)
10. halstead_volume: Program volume (normalized)
11. halstead_difficulty: Program difficulty (normalized)
12. halstead_effort: Programming effort (normalized)
13. halstead_bugs: Estimated bugs (normalized)

Coupling metrics (3) - Estimated from code structure:
14. import_diversity: Variety of import sources (normalized)
15. export_ratio: Exports vs internal code ratio
16. coupling_estimate: Estimated coupling based on imports/exports
"""

import math
import re
from typing import Any

import numpy as np

# Feature dimension
STRUCTURAL_DIMS = 16

# Operators for Halstead metrics (common across languages)
OPERATORS = [
    # Arithmetic
    r'\+\+', r'--', r'\+', r'-', r'\*', r'/', r'%', r'\*\*',
    # Comparison
    r'===', r'!==', r'==', r'!=', r'>=', r'<=', r'>', r'<',
    # Logical
    r'&&', r'\|\|', r'!',
    # Bitwise
    r'&', r'\|', r'\^', r'~', r'<<', r'>>',
    # Assignment
    r'\+=', r'-=', r'\*=', r'/=', r'%=', r'=',
    # Other
    r'\?', r':', r'\.', r',', r';',
    r'\(', r'\)', r'\[', r'\]', r'\{', r'\}',
    # Keywords as operators
    r'\bif\b', r'\belse\b', r'\bfor\b', r'\bwhile\b', r'\breturn\b',
    r'\bfunction\b', r'\bdef\b', r'\bclass\b', r'\btry\b', r'\bcatch\b',
    r'\bthrow\b', r'\braise\b', r'\bimport\b', r'\bfrom\b', r'\bexport\b',
]


def extract_structural_features(content: str, extension: str = ".js") -> np.ndarray:
    """
    Extract structural features from code content.

    Args:
        content: Source code content as string.
        extension: File extension for language-specific patterns.

    Returns:
        NumPy array of 16 normalized features (8 basic + 5 Halstead + 3 coupling).
    """
    lines = content.split("\n")
    non_empty_lines = [line for line in lines if line.strip()]

    # Extract Halstead metrics
    halstead = _extract_halstead_metrics(content)

    features = {
        # Basic metrics (8)
        "loc_normalized": _extract_loc(lines),
        "num_functions": _extract_function_count(content, extension),
        "num_classes": _extract_class_count(content),
        "num_imports": _extract_import_count(content, extension),
        "avg_indent": _extract_avg_indent(non_empty_lines),
        "comment_ratio": _extract_comment_ratio(content, lines),
        "cyclomatic_estimate": _extract_cyclomatic(content, lines),
        "export_count": _extract_export_count(content, extension),
        # Halstead metrics (5)
        "halstead_vocabulary": halstead["vocabulary"],
        "halstead_volume": halstead["volume"],
        "halstead_difficulty": halstead["difficulty"],
        "halstead_effort": halstead["effort"],
        "halstead_bugs": halstead["bugs"],
    }

    # Extract coupling metrics
    coupling = _extract_coupling_metrics(content, extension)

    features.update({
        # Coupling metrics (3)
        "import_diversity": coupling["import_diversity"],
        "export_ratio": coupling["export_ratio"],
        "coupling_estimate": coupling["coupling_estimate"],
    })

    return np.array(list(features.values()), dtype=np.float64)


def _extract_loc(lines: list[str]) -> float:
    """Lines of code normalized to 500."""
    return min(len(lines) / 500.0, 1.0)


def _extract_function_count(content: str, extension: str) -> float:
    """Count function definitions, normalized to 20."""
    patterns = [
        r"\bfunction\s+\w+\s*\(",  # function name()
        r"\bfunction\s*\(",  # function()
        r"(?:const|let|var)\s+\w+\s*=\s*(?:async\s*)?\(",  # const fn = () or const fn = async (
        r"(?:const|let|var)\s+\w+\s*=\s*(?:async\s*)?function",  # const fn = function
        r"\bdef\s+\w+\s*\(",  # Python def
        r"\basync\s+def\s+\w+\s*\(",  # Python async def
        r"=>\s*{",  # Arrow functions with body
    ]

    count = 0
    for pattern in patterns:
        count += len(re.findall(pattern, content))

    return min(count / 20.0, 1.0)


def _extract_class_count(content: str) -> float:
    """Count class definitions, normalized to 10."""
    count = len(re.findall(r"\bclass\s+\w+", content))
    return min(count / 10.0, 1.0)


def _extract_import_count(content: str, extension: str) -> float:
    """Count import statements, normalized to 30."""
    patterns = [
        r"\bimport\s+",  # ES6 import / Python import
        r"\brequire\s*\(",  # CommonJS require
        r"\bfrom\s+['\"]",  # ES6 from 'x'
        r"\bfrom\s+\w+\s+import",  # Python from x import
    ]

    count = 0
    for pattern in patterns:
        count += len(re.findall(pattern, content))

    return min(count / 30.0, 1.0)


def _extract_avg_indent(non_empty_lines: list[str]) -> float:
    """Average indentation depth, normalized to 4 tabs."""
    if not non_empty_lines:
        return 0.0

    total_indent = 0
    for line in non_empty_lines:
        # Count leading whitespace
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        # Normalize to tabs (assuming 2 or 4 spaces = 1 tab)
        total_indent += indent / 4.0

    avg = total_indent / len(non_empty_lines)
    return min(avg / 4.0, 1.0)  # Normalize to max 4 levels


def _extract_comment_ratio(content: str, lines: list[str]) -> float:
    """Ratio of comment content to total content."""
    if not lines:
        return 0.0

    comment_patterns = [
        r"//.*$",  # Single line JS/C++
        r"#.*$",  # Python/Shell
        r"/\*[\s\S]*?\*/",  # Multi-line JS/C
        r'"""[\s\S]*?"""',  # Python docstring
        r"'''[\s\S]*?'''",  # Python docstring
    ]

    comment_chars = 0
    for pattern in comment_patterns:
        for match in re.finditer(pattern, content, re.MULTILINE):
            comment_chars += len(match.group())

    total_chars = len(content) or 1
    return min(comment_chars / total_chars, 1.0)


def _extract_cyclomatic(content: str, lines: list[str]) -> float:
    """
    Estimate cyclomatic complexity.

    Counts decision points: if, else, elif, for, while, switch, case, catch, &&, ||, ?:
    """
    if not lines:
        return 0.0

    patterns = [
        r"\bif\b",
        r"\belse\b",
        r"\belif\b",
        r"\bfor\b",
        r"\bwhile\b",
        r"\bswitch\b",
        r"\bcase\b",
        r"\bcatch\b",
        r"\btry\b",
        r"&&",
        r"\|\|",
        r"\?.*:",  # Ternary
    ]

    count = 0
    for pattern in patterns:
        count += len(re.findall(pattern, content))

    # Normalize: assume 100 decision points in 500 lines is high complexity
    loc = len(lines) or 1
    complexity_per_line = count / loc
    return min(complexity_per_line * 5, 1.0)


def _extract_export_count(content: str, extension: str) -> float:
    """Count exports, normalized to 15."""
    patterns = [
        r"\bexport\s+",  # ES6 export
        r"\bexports\.",  # CommonJS exports.x
        r"\bmodule\.exports",  # CommonJS module.exports
        r"__all__\s*=",  # Python __all__
    ]

    count = 0
    for pattern in patterns:
        count += len(re.findall(pattern, content))

    return min(count / 15.0, 1.0)


def _extract_halstead_metrics(content: str) -> dict[str, float]:
    """
    Extract Halstead complexity metrics.

    Halstead metrics measure program complexity based on operators and operands:
    - n1: Number of unique operators
    - n2: Number of unique operands
    - N1: Total number of operators
    - N2: Total number of operands

    Derived metrics:
    - Vocabulary (n) = n1 + n2
    - Length (N) = N1 + N2
    - Volume (V) = N * log2(n)
    - Difficulty (D) = (n1/2) * (N2/n2)
    - Effort (E) = D * V
    - Bugs (B) = V / 3000

    Returns:
        Dictionary with normalized Halstead metrics.
    """
    # Remove comments and strings to avoid counting them
    cleaned = _remove_comments_and_strings(content)

    # Count operators
    operator_counts: dict[str, int] = {}
    total_operators = 0

    for op_pattern in OPERATORS:
        matches = re.findall(op_pattern, cleaned)
        if matches:
            op_key = op_pattern.replace('\\b', '').replace('\\', '')
            operator_counts[op_key] = len(matches)
            total_operators += len(matches)

    # Count operands (identifiers and literals)
    # Identifiers: variable names, function names, etc.
    identifiers = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', cleaned)
    # Filter out keywords that are operators
    keywords = {'if', 'else', 'for', 'while', 'return', 'function', 'def',
                'class', 'try', 'catch', 'throw', 'raise', 'import', 'from',
                'export', 'const', 'let', 'var', 'in', 'of', 'and', 'or', 'not',
                'True', 'False', 'None', 'true', 'false', 'null', 'undefined'}
    operands = [i for i in identifiers if i not in keywords]

    # Also count numeric literals
    numbers = re.findall(r'\b\d+\.?\d*\b', cleaned)
    operands.extend(numbers)

    # Calculate Halstead metrics
    n1 = len(operator_counts)  # Unique operators
    n2 = len(set(operands))     # Unique operands
    N1 = total_operators        # Total operators
    N2 = len(operands)          # Total operands

    # Avoid division by zero
    if n1 == 0 or n2 == 0:
        return {
            "vocabulary": 0.0,
            "volume": 0.0,
            "difficulty": 0.0,
            "effort": 0.0,
            "bugs": 0.0,
        }

    vocabulary = n1 + n2
    length = N1 + N2
    volume = length * math.log2(vocabulary) if vocabulary > 1 else 0
    difficulty = (n1 / 2) * (N2 / n2) if n2 > 0 else 0
    effort = difficulty * volume
    bugs = volume / 3000

    # Normalize metrics (based on typical ranges)
    return {
        "vocabulary": min(vocabulary / 200, 1.0),       # 200 unique tokens is high
        "volume": min(volume / 10000, 1.0),             # 10000 is high volume
        "difficulty": min(difficulty / 50, 1.0),        # 50 is high difficulty
        "effort": min(effort / 500000, 1.0),            # 500000 is high effort
        "bugs": min(bugs / 5, 1.0),                     # 5 estimated bugs is high
    }


def _extract_coupling_metrics(content: str, extension: str) -> dict[str, float]:
    """
    Extract coupling metrics from code.

    Estimates coupling based on import/export patterns:
    - import_diversity: How many different sources are imported
    - export_ratio: Ratio of exports to total definitions
    - coupling_estimate: Overall coupling score

    Returns:
        Dictionary with normalized coupling metrics.
    """
    lines = content.split("\n")
    non_empty_lines = [line for line in lines if line.strip()]
    loc = len(non_empty_lines) or 1

    # Count unique import sources
    import_sources: set[str] = set()

    # ES6/CommonJS imports
    es6_imports = re.findall(r"from\s+['\"]([^'\"]+)['\"]", content)
    require_imports = re.findall(r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", content)

    # Python imports
    python_imports = re.findall(r"^\s*import\s+(\w+)", content, re.MULTILINE)
    python_from_imports = re.findall(r"^\s*from\s+(\w+)", content, re.MULTILINE)

    import_sources.update(es6_imports)
    import_sources.update(require_imports)
    import_sources.update(python_imports)
    import_sources.update(python_from_imports)

    # Categorize imports
    external_imports = 0
    relative_imports = 0

    for source in import_sources:
        if source.startswith(".") or source.startswith("./") or source.startswith("../"):
            relative_imports += 1
        else:
            external_imports += 1

    # Import diversity: unique sources normalized to 20
    import_diversity = min(len(import_sources) / 20.0, 1.0)

    # Count definitions (functions + classes)
    function_patterns = [
        r"\bfunction\s+\w+\s*\(",
        r"\bdef\s+\w+\s*\(",
        r"(?:const|let|var)\s+\w+\s*=\s*(?:async\s*)?\(",
    ]
    class_patterns = [r"\bclass\s+\w+"]

    total_definitions = 0
    for pattern in function_patterns + class_patterns:
        total_definitions += len(re.findall(pattern, content))

    # Count exports
    export_patterns = [
        r"\bexport\s+(?:default\s+)?(?:function|class|const|let|var)",
        r"\bexport\s*\{",
        r"\bexports\.\w+\s*=",
        r"\bmodule\.exports\s*=",
        r"__all__\s*=",
    ]

    total_exports = 0
    for pattern in export_patterns:
        total_exports += len(re.findall(pattern, content))

    # Export ratio: exports / definitions (normalized)
    if total_definitions > 0:
        export_ratio = min(total_exports / total_definitions, 1.0)
    else:
        export_ratio = 0.0 if total_exports == 0 else 1.0

    # Coupling estimate: combination of import diversity and external dependencies
    # Higher external imports = higher coupling
    if len(import_sources) > 0:
        external_ratio = external_imports / len(import_sources)
    else:
        external_ratio = 0.0

    # Coupling = weighted combination of import diversity and external dependency ratio
    coupling_estimate = (import_diversity * 0.6) + (external_ratio * 0.4)

    return {
        "import_diversity": import_diversity,
        "export_ratio": export_ratio,
        "coupling_estimate": coupling_estimate,
    }


def _remove_comments_and_strings(content: str) -> str:
    """Remove comments and string literals from code."""
    # Remove multi-line strings/comments
    content = re.sub(r'"""[\s\S]*?"""', '', content)
    content = re.sub(r"'''[\s\S]*?'''", '', content)
    content = re.sub(r'/\*[\s\S]*?\*/', '', content)

    # Remove single-line comments
    content = re.sub(r'//.*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'#.*$', '', content, flags=re.MULTILINE)

    # Remove string literals (simplified - doesn't handle all edge cases)
    content = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', '""', content)
    content = re.sub(r"'[^'\\]*(?:\\.[^'\\]*)*'", "''", content)
    content = re.sub(r'`[^`\\]*(?:\\.[^`\\]*)*`', '``', content)

    return content


def get_feature_names() -> list[str]:
    """Return names of structural features in order."""
    return [
        # Basic metrics (8)
        "loc_normalized",
        "num_functions",
        "num_classes",
        "num_imports",
        "avg_indent",
        "comment_ratio",
        "cyclomatic_estimate",
        "export_count",
        # Halstead metrics (5)
        "halstead_vocabulary",
        "halstead_volume",
        "halstead_difficulty",
        "halstead_effort",
        "halstead_bugs",
        # Coupling metrics (3)
        "import_diversity",
        "export_ratio",
        "coupling_estimate",
    ]
