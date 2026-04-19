"""python -m jig entry point — delegates to cli.main."""
from __future__ import annotations

from jig.cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
