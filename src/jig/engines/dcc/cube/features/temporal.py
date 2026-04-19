"""
Temporal feature extractor for code files using Git history.

Extracts 5 temporal features from git history (no external API costs):

1. file_age: Days since first commit (normalized to 365 days)
2. change_frequency: Commits in last 90 days (normalized to 30)
3. author_diversity: Unique authors (normalized to 10)
4. days_since_change: Days since last modification (normalized to 90)
5. stability_score: Inverse of change frequency (stable files score higher)

These features help identify:
- Hot spots (frequently changed files)
- Stale code (old, unchanged files)
- Ownership patterns (single vs shared ownership)
"""

import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from jig.engines.dcc.utils.logger import get_logger

logger = get_logger(__name__)

# Feature dimension
TEMPORAL_DIMS = 5


def extract_temporal_features(file_path: str) -> np.ndarray:
    """
    Extract temporal features from git history.

    Args:
        file_path: Absolute path to the code file.

    Returns:
        NumPy array of 5 normalized temporal features.
    """
    features = {
        "file_age": 0.0,
        "change_frequency": 0.0,
        "author_diversity": 0.0,
        "days_since_change": 0.0,
        "stability_score": 1.0,  # Default to stable if no git history
    }

    path = Path(file_path)
    if not path.exists():
        return np.array(list(features.values()), dtype=np.float64)

    # Find git repository root
    repo_root = _find_git_root(path)
    if not repo_root:
        logger.debug(f"No git repository found for {file_path}")
        return np.array(list(features.values()), dtype=np.float64)

    # Get relative path from repo root
    try:
        relative_path = path.relative_to(repo_root)
    except ValueError:
        return np.array(list(features.values()), dtype=np.float64)

    # Extract git history
    history = _get_git_history(repo_root, str(relative_path))

    if not history["commits"]:
        return np.array(list(features.values()), dtype=np.float64)

    now = datetime.now()

    # 1. File age (days since first commit, normalized to 365 days)
    if history["first_commit_date"]:
        age_days = (now - history["first_commit_date"]).days
        features["file_age"] = min(age_days / 365.0, 1.0)

    # 2. Change frequency (commits in last 90 days, normalized to 30)
    recent_commits = sum(
        1 for date in history["commit_dates"]
        if (now - date).days <= 90
    )
    features["change_frequency"] = min(recent_commits / 30.0, 1.0)

    # 3. Author diversity (unique authors, normalized to 10)
    features["author_diversity"] = min(len(history["authors"]) / 10.0, 1.0)

    # 4. Days since last change (normalized to 90 days - older = lower score)
    if history["last_commit_date"]:
        days_since = (now - history["last_commit_date"]).days
        # Invert so recent changes score higher
        features["days_since_change"] = max(0, 1.0 - (days_since / 90.0))

    # 5. Stability score (inverse of change frequency)
    # Files that change rarely are more stable
    features["stability_score"] = 1.0 - features["change_frequency"]

    return np.array(list(features.values()), dtype=np.float64)


def _find_git_root(path: Path) -> Path | None:
    """Find the git repository root for a given path."""
    current = path if path.is_dir() else path.parent

    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent

    return None


def _get_git_history(repo_root: Path, relative_path: str) -> dict[str, Any]:
    """
    Get git history for a file.

    Returns:
        Dictionary with commits, dates, and authors.
    """
    result = {
        "commits": [],
        "commit_dates": [],
        "authors": set(),
        "first_commit_date": None,
        "last_commit_date": None,
    }

    try:
        # Get commit history with dates and authors
        # Format: hash|date|author
        cmd = [
            "git", "-C", str(repo_root),
            "log", "--follow", "--format=%H|%aI|%an",
            "--", relative_path
        ]

        output = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if output.returncode != 0:
            return result

        lines = output.stdout.strip().split("\n")

        for line in lines:
            if not line or "|" not in line:
                continue

            parts = line.split("|")
            if len(parts) >= 3:
                commit_hash = parts[0]
                date_str = parts[1]
                author = parts[2]

                result["commits"].append(commit_hash)
                result["authors"].add(author)

                # Parse ISO date
                try:
                    # Handle ISO format with timezone
                    date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    # Convert to naive datetime for comparison
                    date = date.replace(tzinfo=None)
                    result["commit_dates"].append(date)
                except ValueError:
                    pass

        # Set first and last commit dates
        if result["commit_dates"]:
            result["commit_dates"].sort()
            result["first_commit_date"] = result["commit_dates"][0]
            result["last_commit_date"] = result["commit_dates"][-1]

    except subprocess.TimeoutExpired:
        logger.warning(f"Git history timeout for {relative_path}")
    except Exception as e:
        logger.debug(f"Error getting git history for {relative_path}: {e}")

    return result


def get_feature_names() -> list[str]:
    """Return names of temporal features in order."""
    return [
        "file_age",
        "change_frequency",
        "author_diversity",
        "days_since_change",
        "stability_score",
    ]


def get_hot_files(features_by_path: dict[str, np.ndarray], threshold: float = 0.5) -> list[str]:
    """
    Get files with high change frequency (hot spots).

    Args:
        features_by_path: Dictionary mapping file paths to temporal features.
        threshold: Minimum change_frequency to be considered "hot".

    Returns:
        List of file paths sorted by change frequency.
    """
    hot_files = []

    for path, features in features_by_path.items():
        change_freq = features[1]  # change_frequency index
        if change_freq >= threshold:
            hot_files.append((path, change_freq))

    hot_files.sort(key=lambda x: x[1], reverse=True)
    return [path for path, _ in hot_files]


def get_stale_files(features_by_path: dict[str, np.ndarray], threshold: float = 0.2) -> list[str]:
    """
    Get files that haven't been changed recently (stale code).

    Args:
        features_by_path: Dictionary mapping file paths to temporal features.
        threshold: Maximum days_since_change to NOT be considered stale.

    Returns:
        List of stale file paths sorted by staleness.
    """
    stale_files = []

    for path, features in features_by_path.items():
        days_score = features[3]  # days_since_change index (inverted, so low = stale)
        if days_score <= threshold:
            stale_files.append((path, days_score))

    stale_files.sort(key=lambda x: x[1])
    return [path for path, _ in stale_files]
