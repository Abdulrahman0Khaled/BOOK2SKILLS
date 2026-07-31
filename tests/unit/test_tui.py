"""Unit tests for the interactive TUI (non-interactive parts)."""

from __future__ import annotations

from pathlib import Path

import pytest

from book_to_skills.tui import (
    _get_orchestrator,
    export_markdown,
    show_stats,
)


class TestTUIComponents:
    """Test TUI building blocks that don't require interaction."""

    def test_orchestrator_created(self):
        orch = _get_orchestrator()
        assert orch is not None

    def test_banner_exists(self):
        from book_to_skills.tui import BANNER

        assert "BOOK-TO-SKILLS" in BANNER
        assert "Hermes Skills" in BANNER
        assert "NexMind" not in BANNER  # branding removed

    def test_books_discovered(self):
        orch = _get_orchestrator()
        books = orch.list_books()
        # At least the books/ dir books should be found
        assert len(books) >= 1
        assert all(b["file_name"] for b in books)

    def test_skills_listable(self):
        import asyncio

        orch = _get_orchestrator()
        skills = asyncio.run(orch.list_skills())
        assert isinstance(skills, list)

    def test_export_markdown_creates_files(self, tmp_path, monkeypatch):
        """export_markdown writes .md files for existing skills."""
        import asyncio

        # Point the working dir at tmp so exports land there
        monkeypatch.chdir(tmp_path)
        orch = _get_orchestrator()
        skills = asyncio.run(orch.list_skills())
        if not skills:
            pytest.skip("No skills available to export")

        (tmp_path / "outputs" / "skills" / "markdown").mkdir(parents=True)

        # Redirect the TUI console so we don't spam the test output
        from book_to_skills import tui

        with Path(tmp_path / "out.txt").open("w", encoding="utf-8") as out_handle:
            monkeypatch.setattr(
                tui,
                "console",
                pytest.importorskip("rich").console.Console(file=out_handle),
            )
            export_markdown(orch)

        md_dir = tmp_path / "outputs" / "skills" / "markdown"
        files = list(md_dir.glob("*.md"))
        assert len(files) >= 1
        content = files[0].read_text(encoding="utf-8")
        assert "---" in content  # frontmatter present

    def test_stats_panel(self):
        orch = _get_orchestrator()
        # Just ensure it doesn't crash on current state
        show_stats(orch)

    def test_progress_runner(self):
        """run_pipeline_with_progress handles empty list gracefully."""
        from book_to_skills.tui import run_pipeline_with_progress

        orch = _get_orchestrator()
        results = run_pipeline_with_progress(orch, [])
        assert results == []
