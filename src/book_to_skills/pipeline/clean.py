"""CleanStage — clean and normalise extracted text.

Removes common footer/header lines, excessive blank lines, Unicode
artefacts, and normalises whitespace.
"""

from __future__ import annotations

import re
import unicodedata

from ..config import PipelineConfig
from ..domain.enums import PipelineStage
from ..domain.models import CleanedContent, PipelineContext
from .base import BaseStage


class CleanStage(BaseStage):
    """Pipeline stage that cleans and normalises extracted text.

    Performs the following clean-up steps in order:

    1. Unicode normalisation (NFKC).
    2. Remove common footer/header patterns (page numbers, copyright
       lines, running headers).
    3. Collapse three-or-more consecutive newlines into two.
    4. Strip trailing whitespace from every line.
    5. Normalise multiple spaces to single spaces.
    6. Remove control characters (except newlines and tabs).

    The cleaned result is stored in ``context.cleaned``.
    """

    # Patterns that commonly appear in PDF/DOCX headers and footers
    _FOOTER_PATTERNS: list[re.Pattern[str]] = [
        re.compile(r"^\s*Page\s+\d+\s*$", re.IGNORECASE),
        re.compile(r"^\s*\d+\s*/\s*\d+\s*$"),  # 3 / 42
        re.compile(r"^\s*Copyright\s+©?\s*\d{4}.*$", re.IGNORECASE),
        re.compile(r"^\s*All\s+rights?\s+reserved\.?\s*$", re.IGNORECASE),
        re.compile(r"^_{10,}\s*$"),  # horizontal rules
        re.compile(r"^[-=]{20,}\s*$"),
    ]

    def __init__(self, config: PipelineConfig) -> None:
        super().__init__(config)
        self.stage = PipelineStage.CLEAN
        self._transformations: list[str] = []

    async def process(self, context: PipelineContext) -> PipelineContext:
        """Clean extracted text and store in ``context.cleaned``.

        Parameters
        ----------
        context : PipelineContext
            Must have ``context.extracted`` set.

        Returns
        -------
        PipelineContext
            The same context with ``cleaned`` populated.

        Raises
        ------
        ValueError
            If ``context.extracted`` is None.
        """
        extracted = context.extracted
        if extracted is None:
            msg = "No extracted content to clean"
            raise ValueError(msg)

        self._transformations.clear()
        text = extracted.text
        original_word_count = self._count_words(text)

        text = self._normalise_unicode(text)
        text = self._remove_footers_and_headers(text)
        text = self._collapse_blank_lines(text)
        text = self._strip_line_trailing_whitespace(text)
        text = self._normalise_spaces(text)
        text = self._remove_control_chars(text)
        text = text.strip()

        cleaned_word_count = self._count_words(text)
        quality = self._compute_quality(
            original_word_count, cleaned_word_count, len(self._transformations)
        )

        cleaned = CleanedContent(
            extract_id=extracted.id,
            text=text,
            original_word_count=original_word_count,
            cleaned_word_count=cleaned_word_count,
            transformations=self._transformations.copy(),
            quality_score=quality,
        )

        context.cleaned = cleaned
        context.stage_results[self.stage.value] = {
            "original_words": original_word_count,
            "cleaned_words": cleaned_word_count,
            "transformations": len(self._transformations),
            "quality_score": quality,
        }

        self.record_metric("original_word_count", original_word_count)
        self.record_metric("cleaned_word_count", cleaned_word_count)
        self.record_metric("quality_score", quality)
        return context

    # ------------------------------------------------------------------
    # Internal cleaning helpers
    # ------------------------------------------------------------------

    def _normalise_unicode(self, text: str) -> str:
        """Normalise to NFKC form (compatibility decomposition)."""
        result = unicodedata.normalize("NFKC", text)
        if result != text:
            self._transformations.append("unicode_nfkc")
        return result

    def _remove_footers_and_headers(self, text: str) -> str:
        """Remove lines matching common footer/header patterns."""
        lines = text.splitlines()
        filtered: list[str] = []
        for line in lines:
            stripped = line.strip()
            if any(p.match(stripped) for p in self._FOOTER_PATTERNS):
                continue
            filtered.append(line)

        if len(filtered) < len(lines):
            self._transformations.append("footer_header_removal")
        return "\n".join(filtered)

    def _collapse_blank_lines(self, text: str) -> str:
        """Replace three or more consecutive newlines with exactly two."""
        result = re.sub(r"\n{3,}", "\n\n", text)
        if result != text:
            self._transformations.append("blank_line_collapse")
        return result

    def _strip_line_trailing_whitespace(self, text: str) -> str:
        """Strip trailing whitespace from each line."""
        lines = [line.rstrip() for line in text.splitlines()]
        result = "\n".join(lines)
        if result != text:
            self._transformations.append("trailing_whitespace_removed")
        return result

    def _normalise_spaces(self, text: str) -> str:
        """Collapse multiple consecutive spaces to a single space."""
        result = re.sub(r" {2,}", " ", text)
        if result != text:
            self._transformations.append("space_normalisation")
        return result

    def _remove_control_chars(self, text: str) -> str:
        """Strip control characters except newline (``\\n``) and tab."""
        result = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
        if result != text:
            self._transformations.append("control_char_removal")
        return result

    @staticmethod
    def _count_words(text: str) -> int:
        """Approximate word count by splitting on whitespace."""
        return len(text.split())

    @staticmethod
    def _compute_quality(original: int, cleaned: int, transformation_count: int) -> float:
        """Heuristic quality score based on ratio kept & transformations applied.

        Returns a float in [0, 1].
        """
        if original == 0:
            return 0.0
        kept_ratio = cleaned / max(original, 1)
        # Penalise very low kept ratios (suggests over-aggressive cleaning)
        if kept_ratio < 0.3:
            return max(0.0, kept_ratio)
        # Reward moderate transformation counts
        transform_bonus = min(transformation_count / 10, 0.2)
        return min(kept_ratio + transform_bonus, 1.0)
