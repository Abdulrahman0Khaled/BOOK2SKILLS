"""ChunkStage — split cleaned text into semantic chunks with overlap.

Uses a recursive boundary-aware chunker that respects paragraph and
sentence boundaries while targeting the configured word count.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from ..config import PipelineConfig
from ..domain.enums import ChunkStrategy, PipelineStage
from ..domain.models import PipelineContext, TextChunk
from .base import BaseStage

# Regex to detect common section heading patterns
_HEADING_RE = re.compile(
    r"^(#{1,4}\s+|(?:CHAPTER|SECTION|PART|APPENDIX)\s+\d+[.:]?\s*)",
    re.IGNORECASE,
)
# Naive paragraph split (double newline)
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")


class ChunkStage(BaseStage):
    """Pipeline stage that splits cleaned text into overlapping chunks.

    Chunking strategy is read from ``config.chunk.strategy``.
    Default is ``SEMANTIC`` (boundary-aware paragraph grouping).

    Stores produced chunks in ``context.chunks``.

    Example::

        stage = ChunkStage(config)
        context = await stage.execute(context)
        assert len(context.chunks) > 0
    """

    def __init__(self, config: PipelineConfig) -> None:
        super().__init__(config)
        self.stage = PipelineStage.CHUNK
        self._chunk_config = config.chunk

    async def process(self, context: PipelineContext) -> PipelineContext:
        """Chunk cleaned text and set ``context.chunks``.

        Parameters
        ----------
        context : PipelineContext
            Must have ``context.cleaned`` set.

        Returns
        -------
        PipelineContext
            Context with ``chunks`` populated.

        Raises
        ------
        ValueError
            If ``context.cleaned`` is None or empty.
        """
        cleaned = context.cleaned
        if cleaned is None or not cleaned.text.strip():
            msg = "No cleaned text to chunk"
            raise ValueError(msg)

        strategy = ChunkStrategy(self._chunk_config.strategy)
        max_words = self._chunk_config.max_chunk_words
        min_words = self._chunk_config.min_chunk_words
        overlap = self._chunk_config.overlap_words

        if strategy == ChunkStrategy.FIXED_SIZE:
            raw_chunks = self._chunk_fixed_size(cleaned.text, max_words, overlap)
        elif strategy == ChunkStrategy.PARAGRAPH:
            raw_chunks = self._chunk_by_paragraph(cleaned.text, max_words, overlap)
        elif strategy == ChunkStrategy.RECURSIVE:
            raw_chunks = self._chunk_recursive(cleaned.text, max_words, min_words, overlap)
        else:
            # SEMANTIC or HYBRID — use heading-aware chunker
            raw_chunks = self._chunk_semantic(cleaned.text, max_words, overlap)

        chunks: list[TextChunk] = []
        for idx, text in enumerate(raw_chunks):
            word_count = len(text.split())
            if word_count < min_words and len(raw_chunks) > 1:
                # Merge tiny trailing chunk into previous one
                if chunks:
                    chunks[-1].text += "\n\n" + text
                    chunks[-1].word_count = len(chunks[-1].text.split())
                    continue
            chunk = TextChunk(
                cleaned_id=cleaned.id,
                index=idx,
                text=text,
                word_count=word_count,
                strategy=strategy,
            )
            chunks.append(chunk)

        context.chunks = chunks
        context.stage_results[self.stage.value] = {
            "strategy": strategy.value,
            "num_chunks": len(chunks),
            "max_words": max_words,
            "overlap_words": overlap,
        }

        self.record_metric("num_chunks", len(chunks))
        self.record_metric("avg_chunk_words", self._avg_word_count(chunks))
        return context

    # ------------------------------------------------------------------
    # Chunking strategies
    # ------------------------------------------------------------------

    def _chunk_semantic(self, text: str, max_words: int, overlap: int) -> list[str]:
        """Heading-aware semantic chunker.

        Preserves section boundaries; groups paragraphs up to ``max_words``
        and carries an overlap window between chunks.
        """
        paragraphs = _PARAGRAPH_SPLIT.split(text.strip())
        return self._group_paragraphs(paragraphs, max_words, overlap)

    def _chunk_by_paragraph(self, text: str, max_words: int, overlap: int) -> list[str]:
        """Simple paragraph-as-chunk strategy.

        Every paragraph becomes its own chunk. Long paragraphs are
        sub-divided at sentence boundaries.
        """
        paragraphs = _PARAGRAPH_SPLIT.split(text.strip())
        chunks: list[str] = []
        carry: str | None = None

        for para in paragraphs:
            para_word_count = len(para.split())
            if para_word_count <= max_words:
                chunk_text = para
                if carry:
                    chunk_text = carry + "\n\n" + para
                    carry = None
                if para_word_count < max_words // 4:
                    carry = chunk_text
                    continue
                chunks.append(chunk_text)
            else:
                # Sub-divide long paragraph
                sub_chunks = self._split_sentences(para, max_words)
                chunks.extend(sub_chunks)

        if carry:
            chunks.append(carry)
        return chunks

    def _chunk_fixed_size(self, text: str, max_words: int, overlap: int) -> list[str]:
        """Fixed-size word-count chunking regardless of content boundaries."""
        words = text.split()
        chunks: list[str] = []
        start = 0
        while start < len(words):
            end = start + max_words
            chunk = " ".join(words[start:end])
            chunks.append(chunk)
            start = end - overlap if end < len(words) else len(words)
        return chunks

    def _chunk_recursive(
        self, text: str, max_words: int, min_words: int, overlap: int
    ) -> list[str]:
        """Recursive chunker — splits at headings first, then paragraphs.

        If a region is still above ``max_words`` it falls back to
        sentence splitting.
        """
        # Phase 1: split on headings
        sections = _HEADING_RE.split(text)
        sections = [s.strip() for s in sections if s.strip()]

        if len(sections) <= 1:
            # No headings — fall through to paragraph-based grouping
            return self._chunk_by_paragraph(text, max_words, overlap)

        chunks: list[str] = []
        buffer: list[str] = []
        buffer_words = 0

        for section in sections:
            words = section.split()
            if buffer_words + len(words) <= max_words:
                buffer.append(section)
                buffer_words += len(words)
            else:
                if buffer:
                    chunks.append("\n\n".join(buffer))
                buffer = [section]
                buffer_words = len(words)

        if buffer:
            remaining = "\n\n".join(buffer)
            # If oversized, sub-chunk
            if buffer_words > max_words:
                chunks.extend(self._split_sentences(remaining, max_words))
            else:
                chunks.append(remaining)

        # Apply overlap by merging the last ``overlap`` words from
        # chunk i into chunk i+1.
        return self._apply_overlap(chunks, overlap, min_words)

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _group_paragraphs(self, paragraphs: list[str], max_words: int, overlap: int) -> list[str]:
        """Group paragraphs into chunks respecting section boundaries."""
        chunks: list[str] = []
        current_group: list[str] = []
        current_words = 0

        for para in paragraphs:
            para_words = len(para.split())

            is_heading = bool(_HEADING_RE.match(para.strip()))

            # Start fresh group on a heading if current group has content
            if is_heading and current_group and current_words > 0:
                chunks.append("\n\n".join(current_group))
                current_group = []
                current_words = 0

            # If adding this paragraph would exceed max_words, flush
            if current_words + para_words > max_words and current_group:
                chunks.append("\n\n".join(current_group))
                # Carry overlap from the end of the previous group
                prev_text = "\n".join(current_group)
                overlap_words = self._extract_tail(prev_text, overlap)
                current_group = [overlap_words] if overlap_words else []
                current_words = len(overlap_words.split()) if overlap_words else 0

            current_group.append(para)
            current_words += para_words

        if current_group:
            chunks.append("\n\n".join(current_group))

        return chunks

    def _split_sentences(self, text: str, max_words: int) -> list[str]:
        """Split text at sentence boundaries when it exceeds ``max_words``."""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks: list[str] = []
        buf: list[str] = []
        buf_words = 0

        for sent in sentences:
            sent_words = len(sent.split())
            if buf_words + sent_words > max_words and buf:
                chunks.append(" ".join(buf))
                buf = []
                buf_words = 0
            buf.append(sent)
            buf_words += sent_words

        if buf:
            chunks.append(" ".join(buf))
        return chunks or [text]

    def _extract_tail(self, text: str, n_words: int) -> str:
        """Return the last ``n_words`` words from ``text``."""
        words = text.split()
        return " ".join(words[-n_words:]) if len(words) > n_words else ""

    def _apply_overlap(self, chunks: list[str], overlap: int, min_words: int) -> list[str]:
        """Prepend tail of previous chunk to current chunk for continuity."""
        if len(chunks) <= 1 or overlap <= 0:
            return chunks

        result: list[str] = [chunks[0]]
        for i in range(1, len(chunks)):
            tail = self._extract_tail(chunks[i - 1], overlap)
            merged = (tail + "\n" + chunks[i]) if tail else chunks[i]
            result.append(merged)

        # Re-check min_words after merge
        final: list[str] = []
        for chunk in result:
            wc = len(chunk.split())
            if wc < min_words and final:
                final[-1] += "\n" + chunk
            else:
                final.append(chunk)
        return final

    @staticmethod
    def _avg_word_count(chunks: Sequence[TextChunk]) -> float:
        if not chunks:
            return 0.0
        return sum(c.word_count for c in chunks) / len(chunks)
