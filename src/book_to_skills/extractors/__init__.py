"""Document extractors for the book-to-skills system.

Each extractor handles a specific file format and implements
:class:`~book_to_skills.extractors.base.BaseExtractor`.
"""

from __future__ import annotations

from .base import BaseExtractor
from .extractor_factory import get_extractor, register_extractor

try:
    from .pdf_extractor import PDFExtractor
except ImportError:  # pragma: no cover
    PDFExtractor = None  # type: ignore[assignment,misc]

try:
    from .docx_extractor import DOCXExtractor
except ImportError:  # pragma: no cover
    DOCXExtractor = None  # type: ignore[assignment,misc]

try:
    from .ocr_extractor import OCRExtractor
except ImportError:  # pragma: no cover
    OCRExtractor = None  # type: ignore[assignment,misc]

__all__ = [
    "BaseExtractor",
    "DOCXExtractor",
    "OCRExtractor",
    "PDFExtractor",
    "get_extractor",
    "register_extractor",
]
