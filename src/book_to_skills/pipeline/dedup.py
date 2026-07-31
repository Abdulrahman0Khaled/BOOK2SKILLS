"""DedupStage — semantic deduplication of skills.

Detects duplicate or near-duplicate skills using **embedding cosine
similarity** (the primary signal): two skills whose semantic
similarity is >= ``_SEMANTIC_THRESHOLD`` (0.85) are considered
duplicates regardless of how their names happen to be phrased.

When embeddings are unavailable (no ``skill.embedding`` and no way to
compute one) the stage falls back to the lexical heuristic — name
similarity via ``difflib`` >= 0.75 **and** content overlap >= 0.60 —
so behaviour never degrades to "no dedup at all".

When a duplicate pair is found:

- The skill with the higher ``quality_score`` survives (ties keep the
  existing survivor).
- The survivor absorbs the removed skill's ``knowledge_ids``,
  ``source_chapters`` and ``tags`` (order-preserving, unique merge).

Every merge is recorded in ``stage_results["dedup"]["merged_pairs"]``
with the method that detected it (``"semantic"`` or ``"lexical"``).
"""

from __future__ import annotations

import difflib
import logging
import re
from collections.abc import Sequence

from ..config import PipelineConfig
from ..domain.enums import PipelineStage
from ..domain.models import HermesSkill, PipelineContext
from .base import BaseStage
from .embeddings import cosine_similarity, hash_embed_text, skill_to_text

logger = logging.getLogger(__name__)

# Semantic (embedding cosine) duplicate threshold
_SEMANTIC_THRESHOLD = 0.85
# Lexical fallback thresholds (kept from the original heuristic stage)
_NAME_SIMILARITY_THRESHOLD = 0.75
_CONTENT_OVERLAP_THRESHOLD = 0.60


class DedupStage(BaseStage):
    """Pipeline stage that deduplicates skills semantically.

    Two skills are duplicates when either:

    1. Their **embedding cosine similarity** >= ``_SEMANTIC_THRESHOLD``
       (0.85) — the semantic path, preferred when embeddings exist; or
    2. Their name similarity (SequenceMatcher ratio) >= 0.75 **and**
       content overlap >= 0.60 — the lexical fallback.

    When a duplicate is found the higher-quality skill survives and
    absorbs the removed skill's ``knowledge_ids``, ``source_chapters``
    and ``tags``.

    Example::

        stage = DedupStage(config)
        context = await stage.execute(context)
        # context.skills now contains only unique entries
    """

    def __init__(self, config: PipelineConfig) -> None:
        super().__init__(config)
        self.stage = PipelineStage.DEDUP
        self._dim = config.vector_db.embedding_dim or 384

    async def process(self, context: PipelineContext) -> PipelineContext:
        """Remove duplicate skills from the context.

        Parameters
        ----------
        context : PipelineContext
            Must have ``context.skills`` populated.

        Returns
        -------
        PipelineContext
            Context with duplicates removed.
        """
        if len(context.skills) < 2:
            dedup_info = {
                "input_count": len(context.skills),
                "removed_count": 0,
                "final_count": len(context.skills),
                "merged_pairs": [],
                "semantic_matches": 0,
                "lexical_matches": 0,
            }
            context.stage_results[self.stage.value] = dedup_info
            return context

        input_count = len(context.skills)
        deduped, merged_pairs = self._deduplicate(context.skills)
        removed = input_count - len(deduped)

        context.skills = deduped

        semantic_matches = sum(1 for p in merged_pairs if p.get("method") == "semantic")
        context.stage_results[self.stage.value] = {
            "input_count": input_count,
            "removed_count": removed,
            "final_count": len(deduped),
            "merged_pairs": merged_pairs,
            "semantic_matches": semantic_matches,
            "lexical_matches": len(merged_pairs) - semantic_matches,
        }

        self.record_metric("input_count", input_count)
        self.record_metric("removed_count", removed)
        return context

    # ------------------------------------------------------------------
    # Deduplication logic
    # ------------------------------------------------------------------

    def _deduplicate(self, skills: list[HermesSkill]) -> tuple[list[HermesSkill], list[dict]]:
        """Return (deduplicated skills, merge records)."""
        survivors: list[HermesSkill] = []
        merged_pairs: list[dict] = []

        for skill in skills:
            merged = False
            for existing in survivors:
                if self._is_duplicate(existing, skill):
                    method = self._match_method(existing, skill)
                    kept, removed = self._keep_better(existing, skill)
                    self._merge_into(kept, removed)
                    merged_pairs.append({
                        "kept_id": kept.id,
                        "kept_name": kept.name,
                        "removed_id": removed.id,
                        "removed_name": removed.name,
                        "method": method,
                        "similarity": round(self._semantic_similarity(existing, skill) or 0.0, 4),
                    })
                    if removed is existing:
                        survivors.remove(existing)
                        survivors.append(skill)
                    merged = True
                    break
            if not merged:
                survivors.append(skill)
        return survivors, merged_pairs

    def _match_method(self, a: HermesSkill, b: HermesSkill) -> str:
        """Report which detector flagged the pair."""
        sem = self._semantic_similarity(a, b)
        if sem is not None and sem >= _SEMANTIC_THRESHOLD:
            return "semantic"
        return "lexical"

    def _is_duplicate(self, a: HermesSkill, b: HermesSkill) -> bool:
        """Determine whether two skills are duplicates.

        Primary signal is embedding cosine similarity; the lexical
        name/content heuristic is the fallback when embeddings cannot
        be compared.
        """
        sem = self._semantic_similarity(a, b)
        if sem is not None and sem >= _SEMANTIC_THRESHOLD:
            return True

        name_sim = self._name_similarity(a.name, b.name)
        if name_sim < _NAME_SIMILARITY_THRESHOLD:
            return False
        return self._content_overlap(a, b) >= _CONTENT_OVERLAP_THRESHOLD

    # ------------------------------------------------------------------
    # Similarity helpers
    # ------------------------------------------------------------------

    def _semantic_similarity(self, a: HermesSkill, b: HermesSkill) -> float | None:
        """Cosine similarity between two skills' embeddings.

        Uses ``skill.embedding`` when present; otherwise computes a
        hash embedding on the fly (same 384-dim space as the default
        transformer model). Returns ``None`` when a comparison is not
        possible (mismatched dimensions).
        """
        emb_a = self._embedding_for(a)
        emb_b = self._embedding_for(b)
        if emb_a is None or emb_b is None:
            return None
        try:
            return cosine_similarity(emb_a, emb_b)
        except Exception:
            return None

    def _embedding_for(self, skill: HermesSkill) -> list[float] | None:
        """Return the skill's embedding, computing a fallback if needed."""
        if skill.embedding:
            return skill.embedding
        return hash_embed_text(skill_to_text(skill), self._dim)

    @staticmethod
    def _keep_better(a: HermesSkill, b: HermesSkill) -> tuple[HermesSkill, HermesSkill]:
        """Return (keeper, removed) — the higher-quality skill survives."""
        if b.quality_score > a.quality_score:
            return b, a
        return a, b

    @staticmethod
    def _merge_into(kept: HermesSkill, removed: HermesSkill) -> None:
        """Absorb the removed skill's provenance into the survivor."""
        kept.knowledge_ids = DedupStage._merge_ids(kept.knowledge_ids, removed.knowledge_ids)
        kept.source_chapters = DedupStage._merge_ids(kept.source_chapters, removed.source_chapters)
        kept.tags = DedupStage._merge_ids(kept.tags, removed.tags)
        kept.related_skills = DedupStage._merge_ids(kept.related_skills, removed.related_skills)

    @staticmethod
    def _name_similarity(name_a: str, name_b: str) -> float:
        """Normalised similarity between two skill names."""
        norm_a = re.sub(r"[^a-zA-Z0-9\s]", "", name_a).lower().strip()
        norm_b = re.sub(r"[^a-zA-Z0-9\s]", "", name_b).lower().strip()
        return difflib.SequenceMatcher(None, norm_a, norm_b).ratio()

    @staticmethod
    def _content_overlap(a: HermesSkill, b: HermesSkill) -> float:
        """Jaccard-like overlap of content words between two skills."""
        words_a = DedupStage._skill_words(a)
        words_b = DedupStage._skill_words(b)
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union)

    @staticmethod
    def _skill_words(skill: HermesSkill) -> set[str]:
        """Extract a set of normalised content words from a skill."""
        parts = [
            skill.description,
            " ".join(skill.best_practices),
            " ".join(skill.pitfalls),
            " ".join(skill.checklist),
        ]
        text = " ".join(parts).lower()
        words = re.findall(r"[a-z0-9]+", text)
        stopwords = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "can",
            "could",
            "should",
            "may",
            "might",
            "shall",
            "to",
            "of",
            "in",
            "for",
            "on",
            "with",
            "at",
            "by",
            "from",
            "as",
            "into",
            "through",
            "during",
            "before",
            "after",
            "above",
            "below",
            "between",
            "out",
            "off",
            "over",
            "under",
            "again",
            "further",
            "then",
            "once",
            "here",
            "there",
            "when",
            "where",
            "why",
            "how",
            "all",
            "each",
            "every",
            "both",
            "few",
            "more",
            "most",
            "other",
            "some",
            "such",
            "no",
            "nor",
            "not",
            "only",
            "own",
            "same",
            "so",
            "than",
            "too",
            "very",
            "just",
            "because",
            "and",
            "but",
            "or",
            "if",
            "while",
            "that",
            "this",
            "it",
            "its",
        }
        return {w for w in words if w not in stopwords and len(w) > 2}

    @staticmethod
    def _merge_ids(a: Sequence[str], b: Sequence[str]) -> list[str]:
        """Merge two id lists preserving order and uniqueness."""
        seen: set[str] = set()
        result: list[str] = []
        for idx in list(a) + list(b):
            if idx not in seen:
                seen.add(idx)
                result.append(idx)
        return result
