"""Tests for next_task continuity hand-off engine + tools."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jig.engines import next_task as engine


@pytest.fixture
def isolated_xdg(tmp_path: Path, monkeypatch):
    """Redirect XDG so writes don't leak into the user's hub."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    return tmp_path


@pytest.fixture
def fake_project(tmp_path: Path) -> str:
    p = tmp_path / "myproj"
    p.mkdir()
    return str(p)


def test_record_then_get_roundtrip(isolated_xdg, fake_project):
    saved = engine.record(
        project_dir=fake_project,
        summary="Migrated all hex colors to design tokens.",
        task_description="centralize Tailwind colors",
        files_changed=["assets/styles.css", "islands/Sidebar.tsx"],
    )
    assert saved.summary.startswith("Migrated")
    assert saved.saved_at  # non-empty ISO timestamp

    loaded = engine.get(fake_project)
    assert loaded is not None
    assert loaded.summary == saved.summary
    assert loaded.task_description == "centralize Tailwind colors"
    assert loaded.files_changed == ["assets/styles.css", "islands/Sidebar.tsx"]


def test_get_returns_none_when_no_save(isolated_xdg, fake_project):
    assert engine.get(fake_project) is None


def test_record_overwrites_previous(isolated_xdg, fake_project):
    engine.record(project_dir=fake_project, summary="first")
    engine.record(project_dir=fake_project, summary="second")
    loaded = engine.get(fake_project)
    assert loaded is not None
    assert loaded.summary == "second"


def test_clear_removes_blob(isolated_xdg, fake_project):
    engine.record(project_dir=fake_project, summary="x")
    assert engine.get(fake_project) is not None

    removed = engine.clear(fake_project)
    assert removed is True
    assert engine.get(fake_project) is None


def test_clear_when_empty_is_noop(isolated_xdg, fake_project):
    removed = engine.clear(fake_project)
    assert removed is False


def test_per_project_isolation(isolated_xdg, tmp_path):
    p1 = tmp_path / "alpha"
    p2 = tmp_path / "beta"
    p1.mkdir()
    p2.mkdir()
    engine.record(project_dir=str(p1), summary="alpha-summary")
    engine.record(project_dir=str(p2), summary="beta-summary")

    assert engine.get(str(p1)).summary == "alpha-summary"
    assert engine.get(str(p2)).summary == "beta-summary"

    engine.clear(str(p1))
    assert engine.get(str(p1)) is None
    assert engine.get(str(p2)).summary == "beta-summary"  # unaffected


def test_format_for_injection_includes_all_fields(isolated_xdg, fake_project):
    entry = engine.record(
        project_dir=fake_project,
        summary="Fixed login redirect loop.",
        task_description="login bug investigation",
        files_changed=["a.ts", "b.ts", "c.ts"],
    )
    out = engine.format_for_injection(entry)
    assert "Previous task summary" in out
    assert "login bug investigation" in out
    assert "Fixed login redirect loop." in out
    assert "`a.ts`" in out


def test_format_for_injection_truncates_long_file_lists(
    isolated_xdg, fake_project
):
    entry = engine.record(
        project_dir=fake_project,
        summary="big refactor",
        files_changed=[f"f{i}.ts" for i in range(25)],
    )
    out = engine.format_for_injection(entry)
    assert "(+15 more)" in out  # 25 - 10 shown


def test_format_for_injection_handles_empty_summary():
    entry = engine.NextTaskEntry(summary="")
    assert engine.format_for_injection(entry) == ""


def test_storage_uses_project_basename(isolated_xdg, tmp_path):
    project = tmp_path / "deeply" / "nested" / "myproj"
    project.mkdir(parents=True)
    engine.record(project_dir=str(project), summary="hello")

    # The blob should be named after the project's basename.
    expected = (
        Path(isolated_xdg) / "xdg" / "jig" / "next_task" / "myproj.json"
    )
    assert expected.exists()
    data = json.loads(expected.read_text())
    assert data["summary"] == "hello"
