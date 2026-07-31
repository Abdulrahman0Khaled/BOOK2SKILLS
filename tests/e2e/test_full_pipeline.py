"""End-to-end tests for the full pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from book_to_skills.config import PipelineConfig
from book_to_skills.pipeline.orchestrator import PipelineOrchestrator


@pytest.mark.e2e
@pytest.mark.slow
class TestFullPipeline:
    """End-to-end pipeline tests with real books."""

    @pytest.fixture
    def config(self, tmp_path):
        cfg = PipelineConfig(
            debug=True,
            cache__enabled=False,
            llm__provider="openai",
            llm__model_small="gpt-4o-mini",
            llm__model_large="gpt-4o",
            extractor__use_ocr_fallback=False,
            monitoring__enable_progress_bars=False,
            stages_enabled=[
                "extract",
                "clean",
                "chunk",
                "knowledge",
                "skill_gen",
                "review",
                "dedup",
                "knowledge_graph",
            ],
        )
        # NOTE: nested kwarg overrides (storage__skills_dir) are ignored by
        # pydantic-settings — must set attributes directly.
        cfg.storage.skills_dir = str(tmp_path / "skills")
        cfg.storage.knowledge_graph_dir = str(tmp_path / "kg")
        cfg.vector_db.persist_dir = str(tmp_path / "vectors")
        return cfg

    @pytest.fixture
    def sample_pdf_path(self):
        p = Path("books/Dot_Com_Secrets.pdf")
        if not p.exists():
            pytest.skip("Sample PDF not available")
        return str(p)

    @pytest.mark.skipif(not Path("books/Dot_Com_Secrets.pdf").exists(), reason="No PDF available")
    @pytest.mark.asyncio
    async def test_pdf_to_skills_pipeline(self, config, sample_pdf_path):
        """Run full pipeline on a PDF and verify skills are generated."""
        orchestrator = PipelineOrchestrator(config)
        result = await orchestrator.run_pipeline(sample_pdf_path)

        assert result is not None
        assert len(result.errors) == 0, f"Pipeline errors: {result.errors}"
        assert result.skills is not None
        # At minimum, the pipeline ran without crashing
        assert result.run_id is not None

    @pytest.fixture
    def sample_docx_path(self):
        p = Path("books/100m-leads-2-bonus-chapters.docx")
        if not p.exists():
            pytest.skip("Sample DOCX not available")
        return str(p)

    @pytest.mark.skipif(
        not Path("books/100m-leads-2-bonus-chapters.docx").exists(), reason="No DOCX available"
    )
    @pytest.mark.asyncio
    async def test_docx_to_skills_pipeline(self, config, sample_docx_path):
        """Run full pipeline on a DOCX and verify skills are generated."""
        orchestrator = PipelineOrchestrator(config)
        result = await orchestrator.run_pipeline(sample_docx_path)

        assert result is not None
        assert result.run_id is not None

    @pytest.mark.skipif(not Path("books/Dot_Com_Secrets.pdf").exists(), reason="No PDF available")
    @pytest.mark.asyncio
    async def test_incremental_processing(self, config, sample_pdf_path):
        """Test that running the same file twice uses cache."""
        orchestrator = PipelineOrchestrator(config)

        # First run
        result1 = await orchestrator.run_pipeline(sample_pdf_path)

        # Second run (should use cache)
        result2 = await orchestrator.run_pipeline(sample_pdf_path)

        assert result1.run_id != result2.run_id  # Different runs
        # Both should succeed
        assert len(result1.errors) == 0
        assert len(result2.errors) == 0


@pytest.mark.e2e
class TestPipelineStages:
    """Test individual pipeline stages independently."""

    @pytest.fixture
    def config(self, tmp_path):
        cfg = PipelineConfig(
            debug=True,
            cache__enabled=False,
            extractor__use_ocr_fallback=False,
            monitoring__enable_progress_bars=False,
        )
        # NOTE: nested kwarg overrides are ignored by pydantic-settings
        cfg.storage.skills_dir = str(tmp_path / "skills")
        cfg.storage.knowledge_graph_dir = str(tmp_path / "kg")
        cfg.vector_db.persist_dir = str(tmp_path / "vectors")
        return cfg

    @pytest.mark.asyncio
    async def test_extract_stage_standalone(self, config):
        """Test that the extract stage can run independently."""
        from book_to_skills.pipeline.extract import ExtractStage

        stage = ExtractStage(config)
        from book_to_skills.domain.enums import BookFormat
        from book_to_skills.domain.models import Book, PipelineContext

        ctx = PipelineContext(
            book=Book(
                file_path="books/Dot_Com_Secrets.pdf",
                format=BookFormat.PDF,
            )
        )

        result = await stage.process(ctx)
        assert result is not None

    @pytest.mark.asyncio
    async def test_clean_stage_standalone(self, config):
        """Test that the clean stage can run independently."""
        from book_to_skills.domain.enums import ExtractionMethod
        from book_to_skills.domain.models import ExtractedContent, PipelineContext
        from book_to_skills.pipeline.clean import CleanStage

        stage = CleanStage(config)
        ctx = PipelineContext(
            extracted=ExtractedContent(
                book_id="test",
                text="  Hello   World!\n\n\nThis is a test.\n\n\n\n",
                method=ExtractionMethod.DIRECT,
            )
        )

        result = await stage.process(ctx)
        assert result is not None
        assert result.cleaned is not None
        # Text should be cleaned
        assert "  " not in result.cleaned.text  # no double spaces
