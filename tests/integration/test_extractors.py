"""Integration tests for book extractors."""

from __future__ import annotations

from pathlib import Path

import pytest

from book_to_skills.config import PipelineConfig
from book_to_skills.extractors.extractor_factory import get_extractor


@pytest.mark.integration
class TestPDFExtractor:
    """Test PDF extraction (with real book files)."""

    @pytest.fixture
    def config(self):
        return PipelineConfig(
            debug=True,
            extractor__use_ocr_fallback=False,
            extractor__ocr_languages="ara+eng",
            cache__enabled=False,
            monitoring__enable_progress_bars=False,
        )

    @pytest.fixture
    def sample_pdf(self):
        """Path to a real PDF book in the repo."""
        p = Path("books/Dot_Com_Secrets.pdf")
        if p.exists():
            return str(p)
        pytest.skip("Sample PDF not found")

    @pytest.mark.skipif(not Path("books/Dot_Com_Secrets.pdf").exists(), reason="No PDF available")
    @pytest.mark.asyncio
    async def test_extract_pdf_text(self, config, sample_pdf):
        extractor = await get_extractor(sample_pdf, config)
        assert extractor is not None

        result = await extractor.extract(sample_pdf)
        assert result is not None
        assert len(result.text) > 100  # at least some text extracted
        assert result.book_id is not None
        assert result.method.value in ("direct", "hybrid", "ocr")

    @pytest.mark.skipif(not Path("books/Dot_Com_Secrets.pdf").exists(), reason="No PDF available")
    @pytest.mark.asyncio
    async def test_extract_pdf_pages(self, config, sample_pdf):
        extractor = await get_extractor(sample_pdf, config)
        pages = await extractor.extract_pages(sample_pdf)
        assert isinstance(pages, dict)
        assert len(pages) > 0


@pytest.mark.integration
class TestDOCXExtractor:
    """Test DOCX extraction."""

    @pytest.fixture
    def config(self):
        return PipelineConfig(
            debug=True,
            extractor__use_ocr_fallback=False,
            cache__enabled=False,
            monitoring__enable_progress_bars=False,
        )

    @pytest.fixture
    def sample_docx(self):
        p = Path("books/100m-leads-2-bonus-chapters.docx")
        if p.exists():
            return str(p)
        pytest.skip("Sample DOCX not found")

    @pytest.mark.skipif(
        not Path("books/100m-leads-2-bonus-chapters.docx").exists(), reason="No DOCX available"
    )
    @pytest.mark.asyncio
    async def test_extract_docx_text(self, config, sample_docx):
        extractor = await get_extractor(sample_docx, config)
        result = await extractor.extract(sample_docx)
        assert result is not None
        assert len(result.text) > 100

    @pytest.mark.skipif(
        not Path("books/100m-leads-2-bonus-chapters.docx").exists(), reason="No DOCX available"
    )
    @pytest.mark.asyncio
    async def test_extract_docx_pages(self, config, sample_docx):
        extractor = await get_extractor(sample_docx, config)
        pages = await extractor.extract_pages(sample_docx)
        assert isinstance(pages, dict)
