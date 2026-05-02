"""Smoke tests — package imports and CLI entry point respond."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import jig
from jig.cli.main import main


def test_version_constant() -> None:
    assert isinstance(jig.__version__, str)
    assert jig.__version__.count(".") >= 2


def test_cli_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert jig.__version__ in out


def test_cli_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "jig" in out.lower()
    assert "init" in out


def test_python_dash_m_invocation() -> None:
    """python -m jig --version must work from a subprocess (wheel sanity)."""
    env = os.environ.copy()
    # Editable-install-free pytest: subprocess needs ``src`` on PYTHONPATH.
    here = Path(__file__).resolve()
    src_root = here.parents[2]
    if (src_root / "jig").is_dir():
        prev = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(src_root) + (os.pathsep + prev if prev else "")
    result = subprocess.run(
        [sys.executable, "-m", "jig", "--version"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert jig.__version__ in result.stdout


def test_paths_module() -> None:
    from jig.core import paths

    assert paths.config_dir().name == "jig"
    assert paths.data_dir().name == "jig"
    assert paths.cache_dir().name == "jig"
