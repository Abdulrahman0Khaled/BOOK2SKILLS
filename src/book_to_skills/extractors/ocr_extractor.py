"""OCR extractor — extract text from scanned documents via OCR.

Uses ``pytesseract`` (Tesseract OCR) as the primary engine with
``pdf2image`` to convert PDF pages to images.

This is a fallback for PDFs where direct text extraction yields poor
results (e.g. scanned books).
"""

from __future__ import annotations

import time
from pathlib import Path

from ..config import PipelineConfig
from ..domain.enums import ExtractionMethod
from ..domain.models import ExtractedContent
from ..utils.file_utils import compute_file_hash
from .base import BaseExtractor


class OCRExtractor(BaseExtractor):
    """OCR-based text extractor for scanned documents.

    Converts PDF pages to images with ``pdf2image`` and runs
    ``pytesseract`` for text recognition.

    Parameters
    ----------
    config : PipelineConfig
        Uses ``config.extractor.ocr_languages``, ``config.extractor.dpi``,
        and ``config.extractor.max_pages``.

    Note
    ----
    Requires the following system packages:
    - ``tesseract-ocr`` (with language packs)
    - ``poppler-utils`` (for ``pdf2image``)

    Example::

        extractor = OCRExtractor(config)
        content = await extractor.extract("scanned_book.pdf")
    """

    def __init__(self, config: PipelineConfig) -> None:
        super().__init__(config)
        self.method = ExtractionMethod.OCR
        self._extractor_config = config.extractor

    @property
    def supported_formats(self) -> list[str]:
        return [".pdf", ".png", ".jpg", ".jpeg", ".tiff"]

    async def extract(self, file_path: str) -> ExtractedContent:
        """Extract text using OCR.

        Parameters
        ----------
        file_path : str
            Path to the document (PDF or image).

        Returns
        -------
        ExtractedContent
        """
        path = Path(file_path)
        ext = path.suffix.lower()
        start = time.monotonic()
        pages: dict[int, str] = {}

        if ext == ".pdf":
            pages = await self._ocr_pdf(path)
        elif ext in (".png", ".jpg", ".jpeg", ".tiff"):
            text = await self._ocr_image(path)
            pages[1] = text
        else:
            msg = f"OCR does not support format: {ext}"
            raise ValueError(msg)

        full_text = "\n\n".join(pages.values()) if pages else ""
        duration = time.monotonic() - start
        word_count = len(full_text.split())
        file_hash = await compute_file_hash(file_path)

        return ExtractedContent(
            book_id="",
            text=full_text.strip(),
            method=self.method,
            pages=pages,
            extraction_time_s=duration,
            word_count=word_count,
            quality_score=self._assess_quality(word_count, len(pages)),
            metadata={
                "file_path": str(path),
                "pages_ocr": len(pages),
                "file_hash": file_hash,
                "ocr_languages": self._extractor_config.ocr_languages,
            },
        )

    async def extract_pages(self, file_path: str) -> dict[int, str]:
        """Return page-number → OCR text."""
        path = Path(file_path)
        ext = path.suffix.lower()
        if ext == ".pdf":
            return await self._ocr_pdf(path)
        text = await self._ocr_image(path)
        return {1: text}

    # ------------------------------------------------------------------
    # OCR internals (lazy imports for optional deps)
    # ------------------------------------------------------------------

    async def _ocr_pdf(self, path: Path) -> dict[int, str]:
        """OCR every page of a PDF via pdf2image + pytesseract."""
        from pdf2image import convert_from_path

        images = convert_from_path(
            str(path),
            dpi=self._extractor_config.dpi,
            first_page=1,
            last_page=self._extractor_config.max_pages,
        )
        pages: dict[int, str] = {}
        for page_num, img in enumerate(images, 1):
            text = await self._run_tesseract(img)
            if text.strip():
                pages[page_num] = text
        return pages

    async def _ocr_image(self, path: Path) -> str:
        """OCR a single image file."""
        from PIL import Image

        img = Image.open(str(path))
        return await self._run_tesseract(img)

    async def _run_tesseract(self, image) -> str:
        """Run Tesseract OCR on a PIL Image."""
        # pytesseract is synchronous; run in thread executor
        import asyncio

        import pytesseract

        def _ocr() -> str:
            return pytesseract.image_to_string(
                image,
                lang=self._extractor_config.ocr_languages,
            )

        return await asyncio.to_thread(_ocr)

    @staticmethod
    def _assess_quality(word_count: int, num_pages: int) -> float:
        """Heuristic OCR quality based on words per page."""
        if num_pages == 0 or word_count == 0:
            return 0.0
        avg_words = word_count / num_pages
        if avg_words > 200:
            return 0.9
        if avg_words > 80:
            return 0.7
        if avg_words > 20:
            return 0.4
        return 0.15
