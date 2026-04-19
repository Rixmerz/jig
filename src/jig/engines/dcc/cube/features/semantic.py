"""
Semantic feature extractor for code files.

Classifies code by functional domain using keyword presence.
Supports custom domains via .deltacodecube.json configuration.

Default domains (5 dimensions):
1. auth: Authentication, authorization, security
2. db: Database, queries, models
3. api: Routes, endpoints, HTTP
4. ui: Components, rendering, styles
5. util: Helpers, utilities, transformations

Custom domains can be configured in .deltacodecube.json:
{
  "domains": {
    "payments": ["stripe", "payment", "invoice"],
    "ml": ["model", "train", "predict"]
  }
}
"""

import json
import os
import re
from pathlib import Path
from typing import Any

import numpy as np

# Default feature dimension (can change with custom domains)
SEMANTIC_DIMS = 5

# Cache for loaded config
_config_cache: dict[str, Any] = {}
_config_path_cache: str | None = None

# Default domain keywords for classification
DEFAULT_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "auth": [
        "login",
        "logout",
        "password",
        "token",
        "session",
        "auth",
        "authenticate",
        "authorize",
        "jwt",
        "credential",
        "user",
        "permission",
        "role",
        "access",
        "security",
        "encrypt",
        "decrypt",
        "hash",
        "salt",
        "oauth",
        "sso",
        "2fa",
        "mfa",
        "verify",
        "signin",
        "signup",
    ],
    "db": [
        "query",
        "select",
        "insert",
        "update",
        "delete",
        "database",
        "model",
        "schema",
        "table",
        "column",
        "row",
        "migration",
        "seed",
        "sql",
        "nosql",
        "mongo",
        "postgres",
        "mysql",
        "redis",
        "orm",
        "repository",
        "entity",
        "transaction",
        "commit",
        "rollback",
        "index",
        "foreign",
        "primary",
        "constraint",
    ],
    "api": [
        "route",
        "router",
        "endpoint",
        "request",
        "response",
        "http",
        "rest",
        "graphql",
        "controller",
        "handler",
        "middleware",
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "api",
        "fetch",
        "axios",
        "cors",
        "header",
        "body",
        "param",
        "query",
        "status",
        "json",
        "webhook",
        "socket",
        "websocket",
    ],
    "ui": [
        "render",
        "component",
        "view",
        "style",
        "css",
        "scss",
        "click",
        "button",
        "form",
        "input",
        "modal",
        "dialog",
        "menu",
        "nav",
        "layout",
        "page",
        "screen",
        "widget",
        "element",
        "dom",
        "html",
        "jsx",
        "tsx",
        "template",
        "props",
        "state",
        "hook",
        "effect",
        "ref",
        "context",
        "redux",
        "store",
    ],
    "util": [
        "helper",
        "util",
        "utils",
        "format",
        "parse",
        "convert",
        "transform",
        "validate",
        "sanitize",
        "escape",
        "encode",
        "decode",
        "serialize",
        "deserialize",
        "stringify",
        "clone",
        "merge",
        "deep",
        "flatten",
        "chunk",
        "debounce",
        "throttle",
        "memoize",
        "cache",
        "logger",
        "log",
        "error",
        "config",
        "constant",
        "enum",
    ],
}

# Default ordered list of domains (matches feature vector order)
DEFAULT_DOMAIN_ORDER = ["auth", "db", "api", "ui", "util"]


def load_config(project_path: str | None = None) -> dict[str, Any]:
    """
    Load configuration from .deltacodecube.json if it exists.

    Args:
        project_path: Path to project root. If None, uses current directory.

    Returns:
        Configuration dictionary with domains and other settings.
    """
    global _config_cache, _config_path_cache

    # Determine search path
    if project_path:
        search_path = Path(project_path)
    else:
        search_path = Path.cwd()

    # Look for config file in current dir and parents
    config_file = None
    for parent in [search_path] + list(search_path.parents):
        candidate = parent / ".deltacodecube.json"
        if candidate.exists():
            config_file = candidate
            break

    # Return cached if same path
    if config_file and str(config_file) == _config_path_cache:
        return _config_cache

    # No config file, return defaults
    if not config_file:
        return {
            "domains": DEFAULT_DOMAIN_KEYWORDS,
            "domain_order": DEFAULT_DOMAIN_ORDER,
        }

    # Load config
    try:
        with open(config_file, "r") as f:
            user_config = json.load(f)

        # Merge with defaults
        if "domains" in user_config:
            # User provided custom domains
            custom_domains = user_config["domains"]
            domain_order = list(custom_domains.keys())

            config = {
                "domains": custom_domains,
                "domain_order": domain_order,
                "custom": True,
            }
        else:
            # No custom domains, use defaults
            config = {
                "domains": DEFAULT_DOMAIN_KEYWORDS,
                "domain_order": DEFAULT_DOMAIN_ORDER,
            }

        # Cache it
        _config_cache = config
        _config_path_cache = str(config_file)

        return config

    except (json.JSONDecodeError, IOError):
        return {
            "domains": DEFAULT_DOMAIN_KEYWORDS,
            "domain_order": DEFAULT_DOMAIN_ORDER,
        }


def get_semantic_dims(project_path: str | None = None) -> int:
    """Get number of semantic dimensions based on config."""
    config = load_config(project_path)
    return len(config["domain_order"])


def extract_semantic_features(content: str, project_path: str | None = None) -> np.ndarray:
    """
    Extract semantic features from code content.

    Classifies code by domain based on keyword presence.
    Uses custom domains from .deltacodecube.json if available.

    Args:
        content: Source code content as string.
        project_path: Optional path to project root for config lookup.

    Returns:
        NumPy array of features (sum approximately 1.0).
    """
    # Load config (uses cache)
    config = load_config(project_path)
    domain_keywords = config["domains"]
    domain_order = config["domain_order"]

    content_lower = content.lower()

    # Count keyword hits per domain
    domain_scores: dict[str, int] = {}

    for domain in domain_order:
        keywords = domain_keywords[domain]
        score = 0

        for keyword in keywords:
            # Use word boundary to avoid partial matches
            pattern = r"\b" + re.escape(keyword) + r"\b"
            matches = len(re.findall(pattern, content_lower))
            score += matches

        domain_scores[domain] = score

    # Convert to probability distribution
    total = sum(domain_scores.values())
    num_domains = len(domain_order)

    if total == 0:
        # No keywords found, return uniform distribution
        return np.ones(num_domains, dtype=np.float64) / num_domains

    # Normalize to sum = 1.0
    features = np.array(
        [domain_scores[domain] / total for domain in domain_order],
        dtype=np.float64,
    )

    return features


def get_domain_names(project_path: str | None = None) -> list[str]:
    """Return names of semantic domains in order."""
    config = load_config(project_path)
    return config["domain_order"].copy()


def get_dominant_domain(features: np.ndarray, project_path: str | None = None) -> str:
    """
    Get the dominant domain from semantic features.

    Args:
        features: Semantic feature vector.
        project_path: Optional path to project root for config lookup.

    Returns:
        Name of the domain with highest score.
    """
    config = load_config(project_path)
    domain_order = config["domain_order"]

    idx = int(np.argmax(features))

    # Handle case where features might have different length than config
    if idx < len(domain_order):
        return domain_order[idx]
    else:
        return DEFAULT_DOMAIN_ORDER[idx] if idx < len(DEFAULT_DOMAIN_ORDER) else "unknown"


def get_domain_distribution(features: np.ndarray, project_path: str | None = None) -> dict[str, float]:
    """
    Get domain distribution as dictionary.

    Args:
        features: Semantic feature vector.
        project_path: Optional path to project root for config lookup.

    Returns:
        Dictionary mapping domain names to scores.
    """
    config = load_config(project_path)
    domain_order = config["domain_order"]

    return {domain: float(features[i]) for i, domain in enumerate(domain_order) if i < len(features)}


def clear_config_cache() -> None:
    """Clear the configuration cache. Useful when config file changes."""
    global _config_cache, _config_path_cache
    _config_cache = {}
    _config_path_cache = None
