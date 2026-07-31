"""EmbeddingsStage — generate real vector embeddings for chunks and skills.

Uses `sentence-transformers` with a local, small model
(``all-MiniLM-L6-v2``, 384-dim) when available. The model is loaded
**lazily** on first use; if the library or model is unavailable the
stage transparently falls back to a deterministic hash-based embedding
(feature hashing with sign, same 384-dim space) and logs a warning —
the pipeline never breaks because of a missing ML dependency.

Behaviour highlights:

- **Chunks and skills are embedded together** in one pass with batching
  (``config.vector_db.embedding_batch_size`` texts per model call).
- Results are stored on the models themselves: ``chunk.embedding`` and
  ``skill.embedding`` (both ``list[float] | None``).
- **Caching by text hash** — embeddings are never recomputed for text
  that was already embedded. The cache is thread-safe (``RLock``) and
  persisted to ``<vector_db.persist_dir>/embedding_cache.json`` so
  repeated runs skip recomputation entirely.
- Thread-safe: cache access and model loading are guarded by a lock, so
  the stage can be shared across concurrent pipeline runs.

Example::

    stage = EmbeddingsStage(config)
    context = await stage.execute(context)
    assert context.chunks[0].embedding is not None
    assert context.skills[0].embedding is not None
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import threading
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..config import PipelineConfig
from ..domain.enums import PipelineStage
from ..domain.models import HermesSkill, PipelineContext, TextChunk
from .base import BaseStage

logger = logging.getLogger(__name__)

# Stopwords list for the fallback bag-of-words embedding
_STOPWORDS: set[str] = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
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
    "shall",
    "should",
    "may",
    "might",
    "must",
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
    "it",
    "its",
    "this",
    "that",
    "these",
    "those",
    "and",
    "but",
    "or",
    "if",
    "while",
    "because",
    "about",
    "up",
    "down",
}

# Dimensionality of the fallback hash-based embedding
_DEFAULT_DIM = 384
# Default local sentence-transformers model
_DEFAULT_MODEL = "all-MiniLM-L6-v2"
# Default texts per model.encode() call
_DEFAULT_BATCH_SIZE = 32
# Cache file version — bump to invalidate stale on-disk caches
_CACHE_VERSION = 1


# ---------------------------------------------------------------------------
# Standalone helpers (reused by DedupStage / KnowledgeGraphStage)
# ---------------------------------------------------------------------------


def hash_embed_text(text: str, dim: int = _DEFAULT_DIM) -> list[float]:
    """Generate a deterministic vector from text using feature hashing.

    Each word is hashed to a fixed set of ``dim`` buckets with a random
    sign; the vector is the L2-normalised term-frequency count. This is
    the zero-dependency fallback used when sentence-transformers is not
    installed. Vectors live in the same 384-dim space as the default
    transformer model, so cosine similarity remains meaningful.
    """
    tokens = _tokenise(text)
    if not tokens:
        return [0.0] * dim

    freq: Counter[str] = Counter(tokens)

    vector = [0.0] * dim
    for word, count in freq.items():
        h = hashlib.md5(word.encode("utf-8"), usedforsecurity=False)
        digest = h.digest()
        # First 4 bytes → bucket index
        idx = int.from_bytes(digest[:4], "little") % dim
        # Next 4 bytes → sign (feature hashing with sign)
        sign = 1 if (int.from_bytes(digest[4:8], "little") % 2 == 0) else -1
        vector[idx] += sign * math.sqrt(count)

    norm = math.sqrt(sum(v * v for v in vector))
    if norm > 0:
        vector = [v / norm for v in vector]
    return vector


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity between two equal-length vectors (0..1)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def skill_to_text(skill: HermesSkill) -> str:
    """Flatten a skill into a text representation for embedding."""
    parts = [
        skill.name,
        skill.description,
        " ".join(skill.best_practices),
        " ".join(skill.pitfalls),
        " ".join(skill.checklist),
        " ".join(skill.references),
    ]
    return " ".join(parts)


def _tokenise(text: str) -> list[str]:
    """Tokenise and clean text for the fallback embedding."""
    text = text.lower()
    tokens = re.findall(r"[a-z]+(?:'[a-z]+)?", text)
    return [t for t in tokens if t not in _STOPWORDS and len(t) > 1]


class EmbeddingsStage(BaseStage):
    """Pipeline stage that generates embeddings for chunks and skills.

    Uses a local sentence-transformers model when available
    (``config.vector_db.embedding_model``, default ``all-MiniLM-L6-v2``)
    and falls back to hash-based embeddings otherwise.

    Generated embeddings are stored on the model objects themselves:
    ``chunk.embedding`` and ``skill.embedding``. A text-hash cache
    (thread-safe, persisted to ``<persist_dir>/embedding_cache.json``)
    guarantees text is never embedded twice.

    Example::

        stage = EmbeddingsStage(config)
        context = await stage.execute(context)
        # Chunks and skills in context have .embedding set
    """

    def __init__(self, config: PipelineConfig) -> None:
        super().__init__(config)
        self.stage = PipelineStage.EMBEDDINGS
        self._vector_config = config.vector_db
        self._dim = self._vector_config.embedding_dim or _DEFAULT_DIM
        self._model_name = getattr(self._vector_config, "embedding_model", _DEFAULT_MODEL)
        self._batch_size = getattr(self._vector_config, "embedding_batch_size", _DEFAULT_BATCH_SIZE)

        # Lazy-loaded sentence-transformer model (None until first use)
        self._model: Any | None = None
        self._model_checked: bool = False

        # Backend label reported in stage results: "sentence_transformers" | "hash"
        self._backend: str = "hash"

        # Text-hash → embedding cache (thread-safe, disk-persisted)
        self._cache: dict[str, list[float]] = {}
        self._cache_lock = threading.RLock()
        self._cache_file: Path | None = None
        if self._vector_config.persist_dir:
            self._cache_file = Path(self._vector_config.persist_dir) / "embedding_cache.json"
        self._load_cache()

    # ------------------------------------------------------------------
    # Model loading (lazy + thread-safe)
    # ------------------------------------------------------------------

    def _get_model(self) -> Any | None:
        """Load the sentence-transformers model exactly once.

        Returns ``None`` (and logs a warning) when the library or model
        is unavailable, in which case hash embeddings are used.
        """
        if self._model_checked:
            return self._model
        with self._cache_lock:
            if self._model_checked:
                return self._model
            self._model_checked = True
            try:
                # Lazy import — library is optional at runtime
                from sentence_transformers import SentenceTransformer  # type: ignore

                self._model = SentenceTransformer(self._model_name)
                self._backend = "sentence_transformers"
                logger.info(
                    "EmbeddingsStage: loaded model '%s' (dim=%d)",
                    self._model_name,
                    self._dim,
                )
            except Exception as exc:
                logger.warning(
                    "EmbeddingsStage: sentence-transformers unavailable (%s); "
                    "falling back to hash embeddings (dim=%d)",
                    exc,
                    self._dim,
                )
                self._model = None
        return self._model

    # ------------------------------------------------------------------
    # Pipeline entry point
    # ------------------------------------------------------------------

    async def process(self, context: PipelineContext) -> PipelineContext:
        """Generate embeddings for chunks and skills in the context.

        Parameters
        ----------
        context : PipelineContext
            Must have ``context.chunks`` and/or ``context.skills``.

        Returns
        -------
        PipelineContext
            Context with embeddings attached to chunks and skills.
        """
        # Collect (owner, text) pairs — chunks and skills in one pass
        chunk_items: list[tuple[TextChunk, str]] = [(c, c.text) for c in context.chunks if c.text]
        skill_items: list[tuple[HermesSkill, str]] = [(s, skill_to_text(s)) for s in context.skills]

        # ── Embed everything (cached + batched) ──────────────────────
        chunk_embeddings = self._embed_texts([t for _, t in chunk_items])
        skill_embeddings_list = self._embed_texts([t for _, t in skill_items])

        chunk_count = 0
        for (chunk, _), embedding in zip(chunk_items, chunk_embeddings, strict=True):
            if embedding:
                chunk.embedding = embedding
                chunk_count += 1

        skill_count = 0
        skill_embeddings: dict[str, list[float]] = {}
        for (skill, _), embedding in zip(skill_items, skill_embeddings_list, strict=True):
            if embedding:
                skill.embedding = embedding
                skill_embeddings[skill.id] = embedding
                skill_count += 1

        self._save_cache()

        stats: dict[str, Any] = {
            "chunks_embedded": chunk_count,
            "skills_embedded": skill_count,
            "dimension": self._dim,
            "backend": self._backend,
            "model": self._model_name if self._backend == "sentence_transformers" else None,
            "cache_size": len(self._cache),
            "skill_embeddings": skill_embeddings,  # backward-compatible map
            "chunk_embeddings_refs": [
                {"chunk_id": c.id, "index": c.index} for c in context.chunks if c.embedding
            ],
        }
        context.stage_results[self.stage.value] = stats

        self.record_metric("chunks_embedded", chunk_count)
        self.record_metric("skills_embedded", skill_count)
        self.record_metric("cache_size", len(self._cache))
        return context

    # ------------------------------------------------------------------
    # Public embedding API (also used standalone / by tests)
    # ------------------------------------------------------------------

    def embed_text(self, text: str) -> list[float]:
        """Embed a single text, using the cache and the active backend."""
        result = self._embed_texts([text])
        return result[0] if result and result[0] else hash_embed_text(text, self._dim)

    def _embed_text(self, text: str) -> list[float]:
        """Backward-compatible alias of :meth:`embed_text`."""
        return self.embed_text(text)

    # ------------------------------------------------------------------
    # Cached, batched embedding core
    # ------------------------------------------------------------------

    def _embed_texts(self, texts: list[str]) -> list[list[float] | None]:
        """Embed many texts with a text-hash cache and model batching.

        Returns a list parallel to ``texts``; entries are ``None`` only
        for empty inputs. Thread-safe: cache reads/writes are locked,
        and duplicate concurrent computations of the same text are
        harmless (idempotent cache writes).
        """
        if not texts:
            return []

        results: list[list[float] | None] = [None] * len(texts)
        pending: list[int] = []

        with self._cache_lock:
            for i, text in enumerate(texts):
                key = self._cache_key(text)
                cached = self._cache.get(key)
                if cached is not None:
                    results[i] = cached
                else:
                    pending.append(i)

        if not pending:
            return results

        # Compute the missing ones (outside the lock — model.encode is slow)
        batch_texts = [texts[i] for i in pending]
        model = self._get_model()
        if model is not None:
            computed = self._encode_with_model(batch_texts, model)
        else:
            computed = [hash_embed_text(t, self._dim) for t in batch_texts]

        with self._cache_lock:
            for i, emb in zip(pending, computed, strict=True):
                if emb:
                    results[i] = emb
                    self._cache[self._cache_key(texts[i])] = emb
        return results

    def _encode_with_model(self, texts: list[str], model: Any) -> list[list[float]]:
        """Encode texts with the transformer model in batches of ``batch_size``."""
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            vectors = model.encode(
                batch,
                batch_size=self._batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
            for vec in vectors:
                embeddings.append([float(x) for x in vec])
        return embeddings

    # ------------------------------------------------------------------
    # Cache (thread-safe, disk-persisted)
    # ------------------------------------------------------------------

    @staticmethod
    def _cache_key(text: str) -> str:
        """Stable key for a text — sha256 of the normalized content."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _load_cache(self) -> None:
        """Load the on-disk embedding cache if present and compatible."""
        if not self._cache_file or not self._cache_file.exists():
            return
        try:
            data = json.loads(self._cache_file.read_text(encoding="utf-8"))
            if data.get("version") != _CACHE_VERSION:
                return
            if data.get("dim") != self._dim:
                return
            entries = data.get("entries", {})
            self._cache = {k: [float(x) for x in v] for k, v in entries.items()}
            logger.info(
                "EmbeddingsStage: loaded %d cached embeddings from %s",
                len(self._cache),
                self._cache_file,
            )
        except Exception as exc:
            logger.warning("EmbeddingsStage: could not load cache (%s)", exc)
            self._cache = {}

    def _save_cache(self) -> None:
        """Persist the embedding cache to disk (best-effort)."""
        if not self._cache_file:
            return
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": _CACHE_VERSION,
                "dim": self._dim,
                "model": self._model_name,
                "backend": self._backend,
                "entries": self._cache,
            }
            tmp = self._cache_file.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload), encoding="utf-8")
            tmp.replace(self._cache_file)
        except Exception as exc:
            logger.warning("EmbeddingsStage: could not save cache (%s)", exc)
