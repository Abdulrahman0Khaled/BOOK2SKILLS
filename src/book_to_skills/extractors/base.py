"""Abstract base class for document extractors."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..config import PipelineConfig
from ..domain.enums import ExtractionMethod
from ..domain.models import ExtractedContent


class BaseExtractor(ABC):
    """Abstract document extractor with fallback to OCR."""

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.method: ExtractionMethod = ExtractionMethod.DIRECT

    @abstractmethod
    async def extract(self, file_path: str) -> ExtractedContent:
        """Extract text content from a document."""
        ...

    @abstractmethod
    async def extract_pages(self, file_path: str) -> dict[int, str]:
        """Extract text per page."""
        ...

    def supports_ocr(self) -> bool:
        return self.config.extractor.use_ocr_fallback

    @property
    def supported_formats(self) -> list[str]:
        return []
