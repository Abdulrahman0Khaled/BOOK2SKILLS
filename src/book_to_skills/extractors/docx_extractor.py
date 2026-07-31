"""DOCX document extractor using python-docx."""

from __future__ import annotations

from pathlib import Path

from ..config import PipelineConfig
from ..domain.enums import ExtractionMethod
from ..domain.models import ExtractedContent
from .base import BaseExtractor


class DOCXExtractor(BaseExtractor):
    """Extract text from DOCX files using python-docx."""

    def __init__(self, config: PipelineConfig) -> None:
        super().__init__(config)
        self.method = ExtractionMethod.DIRECT

    @property
    def supported_formats(self) -> list[str]:
        return ["docx", "doc"]

    async def extract(self, file_path: str) -> ExtractedContent:
        """Extract all text from a DOCX file."""
        import time

        start = time.monotonic()

        pages = await self.extract_pages(file_path)
        full_text = "\n\n".join(pages[i] for i in sorted(pages.keys()) if pages[i].strip())

        word_count = len(full_text.split())

        return ExtractedContent(
            book_id=Path(file_path).stem,
            text=full_text,
            method=self.method,
            pages=pages,
            extraction_time_s=time.monotonic() - start,
            word_count=word_count,
            quality_score=min(1.0, word_count / 5000),
        )

    async def extract_pages(self, file_path: str) -> dict[int, str]:
        """Extract text from DOCX, grouping into pseudo-pages (~2000 chars each)."""
        from docx import Document

        doc = Document(file_path)
        all_paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]

        # Group paragraphs into pseudo-pages (~2000 chars each)
        pages: dict[int, str] = {}
        current_page: list[str] = []
        current_length = 0
        page_num = 1
        chars_per_page = 2000

        for para in all_paragraphs:
            current_page.append(para)
            current_length += len(para)
            if current_length >= chars_per_page:
                pages[page_num] = "\n".join(current_page)
                page_num += 1
                current_page = []
                current_length = 0

        if current_page:
            pages[page_num] = "\n".join(current_page)

        return pages
