"""Extractor factory — resolve a file path to the appropriate extractor.

Usage::

    from book_to_skills.extractors.extractor_factory import get_extractor
    extractor = await get_extractor("book.pdf", config)
    content = await extractor.extract("book.pdf")
"""

from __future__ import annotations

from pathlib import Path

from ..config import PipelineConfig
from ..domain.enums import ExtractionMethod
from ..domain.models import ExtractedContent
from .base import BaseExtractor
from .docx_extractor import DOCXExtractor
from .ocr_extractor import OCRExtractor
from .pdf_extractor import PDFExtractor

# Extension → extractor class mapping
_EXTENSION_MAP: dict[str, type[BaseExtractor]] = {
    ".pdf": PDFExtractor,
    ".docx": DOCXExtractor,
    ".doc": DOCXExtractor,
    # Image formats for direct OCR (when explicitly used)
    ".png": OCRExtractor,
    ".jpg": OCRExtractor,
    ".jpeg": OCRExtractor,
    ".tiff": OCRExtractor,
}


async def get_extractor(file_path: str, config: PipelineConfig) -> BaseExtractor:
    """Return the best extractor for the given file.

    Inspects the file extension and returns the matching extractor.
    Falls back to OCR when the config specifies ``hybrid`` mode and
    the primary extractor's quality is below threshold.

    Parameters
    ----------
    file_path : str
        Path to the document to be extracted.
    config : PipelineConfig
        Pipeline configuration.

    Returns
    -------
    BaseExtractor
        An initialised extractor instance.

    Raises
    ------
    ValueError
        If the file extension is not supported.
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext not in _EXTENSION_MAP:
        supported = list(_EXTENSION_MAP.keys())
        msg = f"Unsupported file extension: '{ext}'. Supported formats: {supported}"
        raise ValueError(msg)

    extractor_cls = _EXTENSION_MAP[ext]
    extractor = extractor_cls(config)

    # In hybrid mode, wrap PDF extraction to potentially fall back to OCR
    pdf_mode = config.extractor.pdf_extraction_mode
    if ext == ".pdf" and pdf_mode == "ocr":
        return OCRExtractor(config)
    if ext == ".pdf" and pdf_mode == "hybrid" and config.extractor.use_ocr_fallback:
        return _HybridExtractor(config)

    return extractor


async def register_extractor(extension: str, extractor_cls: type[BaseExtractor]) -> None:
    """Register a custom extractor for a file extension at runtime.

    Parameters
    ----------
    extension : str
        File extension including the dot (e.g. ``".epub"``).
    extractor_cls : type[BaseExtractor]
        A subclass of :class:`BaseExtractor`.
    """
    _EXTENSION_MAP[extension.lower()] = extractor_cls


class _HybridExtractor(BaseExtractor):
    """Internal hybrid extractor: tries direct PDF first, falls back to OCR.

    Only used when ``pdf_extraction_mode = "hybrid"``.
    """

    def __init__(self, config: PipelineConfig) -> None:
        super().__init__(config)
        self.method = ExtractionMethod.HYBRID
        self._pdf = PDFExtractor(config)
        self._ocr = OCRExtractor(config)

    async def extract(self, file_path: str) -> ExtractedContent:
        """Try direct PDF extraction; fall back to OCR if quality < 0.3."""
        result = await self._pdf.extract(file_path)
        if result.quality_score >= 0.3:
            result.method = ExtractionMethod.HYBRID
            return result
        # Fall back to OCR
        ocr_result = await self._ocr.extract(file_path)
        ocr_result.method = ExtractionMethod.HYBRID
        return ocr_result

    async def extract_pages(self, file_path: str) -> dict[int, str]:
        return await self._pdf.extract_pages(file_path)

    @property
    def supported_formats(self) -> list[str]:
        return [".pdf"]
