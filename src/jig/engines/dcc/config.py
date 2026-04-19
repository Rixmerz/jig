"""Configuration for DeltaCodeCube MCP."""

import os
from pathlib import Path

# Data directory for SQLite database
DATA_DIR = Path(os.environ.get("DCC_DATA_DIR", Path.home() / ".deltacodecube"))
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
