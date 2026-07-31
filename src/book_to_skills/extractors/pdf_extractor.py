"""PDF extractor — extract text from PDF files.

Uses ``pypdf`` for direct extraction (fast, layout-preserving).
Falls back to OCR via :mod:`~book_to_skills.extractors.ocr_extractor`
when ``config.extractor.use_ocr_fallback`` is set.
"""

from __future__ import annotations

import time
from pathlib import Path

from pypdf import PdfReader

from ..config import PipelineConfig
from ..domain.enums import ExtractionMethod
from ..domain.models import ExtractedContent
from ..utils.file_utils import compute_file_hash
from .base import BaseExtractor


class PDFExtractor(BaseExtractor):
    """Extract text from PDF documents using ``pypdf``.

    Parameters
    ----------
    config : PipelineConfig
        Uses ``config.extractor`` for OCR fallback, max pages, etc.

    Example::

        extractor = PDFExtractor(config)
        content = await extractor.extract("document.pdf")
        print(content.text[:200])
    """

    def __init__(self, config: PipelineConfig) -> None:
        super().__init__(config)
        self.method = ExtractionMethod.DIRECT
        self._extractor_config = config.extractor

    @property
    def supported_formats(self) -> list[str]:
        return [".pdf"]

    async def extract(self, file_path: str) -> ExtractedContent:
        """Extract text from a PDF.

        Parameters
        ----------
        file_path : str
            Path to the PDF file.

        Returns
        -------
        ExtractedContent
            The extracted text content with page-level detail.
        """
        path = Path(file_path)
        start = time.monotonic()
        pages: dict[int, str] = {}
        full_text_parts: list[str] = []

        reader = PdfReader(str(path))
        total_pages = min(len(reader.pages), self._extractor_config.max_pages)

        for page_num in range(total_pages):
            page = reader.pages[page_num]
            text = page.extract_text() or ""
            pages[page_num + 1] = text
            full_text_parts.append(text)

        full_text = "\n\n".join(full_text_parts)
        duration = time.monotonic() - start

        # Check quality — if extracted text is too sparse, trigger OCR
        word_count = len(full_text.split())
        quality = self._assess_quality(word_count, total_pages)

        if quality < 0.3 and self.supports_ocr():
            return await self._fallback_to_ocr(file_path)
        if quality < 0.1 and not self.supports_ocr():
            full_text = self._apply_repair(full_text)
            word_count = len(full_text.split())
            quality = self._assess_quality(word_count, total_pages)

        file_hash = await compute_file_hash(file_path)

        return ExtractedContent(
            book_id="",
            text=full_text.strip(),
            method=self.method,
            pages=pages,
            extraction_time_s=duration,
            word_count=word_count,
            quality_score=quality,
            metadata={
                "file_path": str(path),
                "total_pages": total_pages,
                "file_hash": file_hash,
            },
        )

    async def extract_pages(self, file_path: str) -> dict[int, str]:
        """Return page-number → text mapping."""
        path = Path(file_path)
        reader = PdfReader(str(path))
        pages: dict[int, str] = {}
        for i, page in enumerate(reader.pages):
            if i >= self._extractor_config.max_pages:
                break
            pages[i + 1] = page.extract_text() or ""
        return pages

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _fallback_to_ocr(self, file_path: str) -> ExtractedContent:
        """Delegate to OCR when direct extraction yields poor results."""
        from .ocr_extractor import OCRExtractor

        ocr = OCRExtractor(self.config)
        return await ocr.extract(file_path)

    @staticmethod
    def _assess_quality(word_count: int, total_pages: int) -> float:
        """Heuristic quality based on average words per page."""
        if total_pages == 0:
            return 0.0
        words_per_page = word_count / total_pages
        if words_per_page > 150:
            return 1.0
        if words_per_page > 50:
            return 0.5
        if words_per_page > 10:
            return 0.2
        return 0.05

    @staticmethod
    def _apply_repair(text: str) -> str:
        """Basic repair for common PDF extraction artefacts."""
        import re

        text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)  # hyphenated line breaks
        text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)  # single newlines -> space
        return text
