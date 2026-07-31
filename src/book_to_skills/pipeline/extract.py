"""ExtractStage — extract raw text from PDF/DOCX documents.

Uses the extractor factory to get the right extractor for the file format,
then stores the extracted content in PipelineContext.extracted.
"""

from __future__ import annotations

from pathlib import Path

from ..config import PipelineConfig
from ..domain.enums import PipelineStage
from ..domain.models import PipelineContext
from ..extractors.extractor_factory import get_extractor
from .base import BaseStage


class ExtractStage(BaseStage):
    """Pipeline stage that extracts raw text from a book file.

    Examines the book format, selects the appropriate extractor via the
    extractor factory, and populates ``context.extracted`` with the result.

    Example::

        stage = ExtractStage(config)
        context = PipelineContext(book=Book(file_path="book.pdf", format="pdf"))
        result = await stage.execute(context)
    """

    def __init__(self, config: PipelineConfig) -> None:
        super().__init__(config)
        self.stage = PipelineStage.EXTRACT

    async def process(self, context: PipelineContext) -> PipelineContext:
        """Run extraction and store the result in ``context.extracted``.

        Parameters
        ----------
        context : PipelineContext
            Must have ``context.book`` set with a valid ``file_path``.

        Returns
        -------
        PipelineContext
            The same context with ``extracted`` populated.

        Raises
        ------
        ValueError
            If ``context.book`` is None or the file does not exist.
        """
        book = context.book
        if book is None:
            msg = "No book set in pipeline context"
            raise ValueError(msg)

        file_path = Path(book.file_path)
        if not file_path.exists():
            msg = f"Book file not found: {file_path}"
            raise ValueError(msg)

        extractor = await get_extractor(str(file_path), self.config)
        extracted = await extractor.extract(str(file_path))

        # Attach metadata
        extracted.book_id = book.id
        self.record_metric("extraction_time_s", extracted.extraction_time_s)
        self.record_metric("word_count", extracted.word_count)
        self.record_metric("quality_score", extracted.quality_score)

        context.extracted = extracted
        context.stage_results[self.stage.value] = {
            "method": extracted.method.value,
            "word_count": extracted.word_count,
            "pages": len(extracted.pages),
        }
        return context
