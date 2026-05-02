"""Provider registry for CodeAnalysisProvider backends.

Discovery order:
1. Environment variable ``JIG_PROVIDER`` — overrides everything.
2. Entry-points group ``jig.providers`` — first registered entry-point wins.
3. NullProvider — silent fallback (satisfies RF-004).

Usage::

    from jig.engines.provider_registry import get_provider

    provider = get_provider()
    if provider.is_available():
        report = await provider.detect_smells(project_dir)
"""
from __future__ import annotations

import importlib
import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jig.contracts.code_analysis import CodeAnalysisProvider

_cached_provider: CodeAnalysisProvider | None = None
_ENTRY_POINT_GROUP = "jig.providers"


def _load_entry_point_provider() -> CodeAnalysisProvider | None:
    """Try to load the first provider registered via entry-points."""
    try:
        # importlib.metadata available from Python 3.9+
        from importlib.metadata import entry_points

        eps = entry_points(group=_ENTRY_POINT_GROUP)
        for ep in eps:
            try:
                cls = ep.load()
                return cls()
            except Exception as exc:
                print(
                    f"[jig] Warning: failed to load provider '{ep.name}': {exc}",
                    file=sys.stderr,
                )
    except Exception:
        pass
    return None


def _load_env_provider() -> CodeAnalysisProvider | None:
    """Load a provider specified via JIG_PROVIDER env var (dotted import path)."""
    dotted = os.environ.get("JIG_PROVIDER", "").strip()
    if not dotted:
        return None
    try:
        module_path, cls_name = dotted.rsplit(".", 1)
        module = importlib.import_module(module_path)
        cls = getattr(module, cls_name)
        return cls()
    except Exception as exc:
        print(
            f"[jig] Warning: JIG_PROVIDER='{dotted}' could not be loaded: {exc}",
            file=sys.stderr,
        )
        return None


def get_provider(*, force_reload: bool = False) -> CodeAnalysisProvider:
    """Return the active CodeAnalysisProvider, instantiating it on first call.

    Thread-safe reads via Python's GIL; the function is idempotent.

    Args:
        force_reload: If True, discard the cached instance and re-discover.

    Returns:
        A concrete CodeAnalysisProvider implementation, guaranteed non-None.
        Falls back to NullProvider when no backend is configured.
    """
    global _cached_provider

    if _cached_provider is not None and not force_reload:
        return _cached_provider

    # 1. Explicit env override
    provider = _load_env_provider()

    # 2. Entry-point discovery
    if provider is None:
        provider = _load_entry_point_provider()

    # 3. Fallback to NullProvider
    if provider is None:
        from jig.contracts.code_analysis import NullProvider
        provider = NullProvider()

    _cached_provider = provider
    return provider


def reset_provider() -> None:
    """Clear the cached provider (useful for tests and hot-reloading)."""
    global _cached_provider
    _cached_provider = None
