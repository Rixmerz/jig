"""Configuration for DeltaCodeCube (vendored inside jig)."""

import os
from pathlib import Path

# Unify DCC state under jig's XDG data dir. Override with DCC_DATA_DIR env
# if you need a separate location (e.g. a shared team DB).
_DEFAULT_DATA_DIR = Path.home() / ".local" / "share" / "jig"
DATA_DIR = Path(os.environ.get("DCC_DATA_DIR", _DEFAULT_DATA_DIR))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Database path
DB_PATH = DATA_DIR / "dcc.db"

# Default chunk settings
DEFAULT_CHUNK_SIZE = 2000  # words
DEFAULT_OVERLAP = 100  # words

# Supported formats
SUPPORTED_FORMATS = {"txt", "md", "pdf", "epub", "html", "code"}

# Logging
LOG_LEVEL = os.environ.get("BIGCONTEXT_LOG_LEVEL", "INFO")
