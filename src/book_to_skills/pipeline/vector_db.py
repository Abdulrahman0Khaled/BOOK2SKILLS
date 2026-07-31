"""VectorDBStage — persistent vector storage via ChromaDB.

Uses `chromadb` with a real persistent client rooted at
``config.vector_db.persist_dir`` when the library is installed. The
import is **lazy**: if chromadb is missing (or fails to initialise) the
stage transparently falls back to an in-memory cosine store so the
pipeline never breaks.

Highlights:

- The collection is created **once** via ``get_or_create_collection``
  and reused (persisted across runs in the same process).
- Chunks and skills are upserted with rich metadata: ``book_id``,
  ``skill_id`` / ``chunk_id``, ``category``, ``tags``, ``status``,
  ``quality_score``, ``source_type``, plus a text preview.
- ``VectorDBStage.search(query_embedding, top_k)`` is available for
  downstream retrieval (API, RAG, dedup, knowledge graph).
- Chroma metadata only accepts scalar values, so lists (e.g. ``tags``)
  are joined into comma-separated strings on the way in and split back
  on the way out.

Example::

    stage = VectorDBStage(config)
    context = await stage.execute(context)
    store = context.stage_results["vector_db"]["store"]
    hits = stage.search(query_embedding, top_k=5)
"""

from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass
from typing import Any

from ..config import PipelineConfig
from ..domain.enums import PipelineStage
from ..domain.models import PipelineContext
from .base import BaseStage

logger = logging.getLogger(__name__)

# Chroma metadata only supports scalar values — lists are joined with this
_METADATA_LIST_SEP = ","


@dataclass
class VectorEntry:
    """A single entry to be indexed in the vector store."""

    id: str
    vector: list[float]
    payload: dict[str, Any]
    source_type: str  # "chunk" or "skill"
    source_id: str


@dataclass
class VectorSearchResult:
    """Result from a vector similarity search."""

    id: str
    score: float
    payload: dict[str, Any]
    source_type: str


class InMemoryVectorStore:
    """Simple in-memory vector store with cosine-similarity search.

    Used as the automatic fallback when chromadb is not installed.
    """

    def __init__(self, dim: int, distance_metric: str = "cosine") -> None:
        self._entries: dict[str, VectorEntry] = {}
        self._dim = dim
        self._distance_metric = distance_metric
        self.backend = "in_memory"

    def add(self, entry: VectorEntry) -> None:
        """Insert or update a vector entry."""
        self._entries[entry.id] = entry

    def add_many(self, entries: list[VectorEntry]) -> int:
        for entry in entries:
            self.add(entry)
        return len(entries)

    def upsert(self, entries: list[VectorEntry]) -> int:
        """Insert or update entries (same as :meth:`add_many`)."""
        return self.add_many(entries)

    def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        source_type: str | None = None,
    ) -> list[VectorSearchResult]:
        """Return top-k most similar entries by cosine similarity."""
        if not self._entries:
            return []

        results: list[VectorSearchResult] = []
        for entry in self._entries.values():
            if source_type and entry.source_type != source_type:
                continue
            if not entry.vector or len(entry.vector) != self._dim:
                continue
            score = self._cosine_similarity(query_vector, entry.vector)
            results.append(
                VectorSearchResult(
                    id=entry.id,
                    score=score,
                    payload=entry.payload,
                    source_type=entry.source_type,
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def count(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()

    # ------------------------------------------------------------------
    # Distance metrics
    # ------------------------------------------------------------------

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b, strict=True))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)


class ChromaVectorStore:
    """ChromaDB-backed persistent vector store with in-memory fallback.

    The chromadb import happens **lazily** inside ``__init__``; when it
    fails, all operations delegate to an :class:`InMemoryVectorStore`
    and ``backend`` reports ``"in_memory"``. The collection is created
    exactly once via ``get_or_create_collection`` and persists on disk
    under ``persist_dir``.
    """

    def __init__(
        self,
        persist_dir: str,
        collection_name: str,
        dim: int,
        distance_metric: str = "cosine",
    ) -> None:
        self._dim = dim
        self._distance_metric = distance_metric
        self._collection: Any | None = None
        self._client: Any | None = None
        self._fallback: InMemoryVectorStore | None = None
        self.backend = "in_memory"

        try:
            # Lazy import — library is optional at runtime
            import chromadb  # type: ignore

            self._client = chromadb.PersistentClient(path=str(persist_dir))
            space = "cosine" if distance_metric == "cosine" else "l2"
            self._collection = self._client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": space},
            )
            self.backend = "chroma"
            logger.info(
                "VectorDBStage: connected to chromadb collection '%s' at %s",
                collection_name,
                persist_dir,
            )
        except Exception as exc:
            logger.warning(
                "VectorDBStage: chromadb unavailable (%s); using in-memory "
                "vector store — embeddings will NOT persist",
                exc,
            )
            self._fallback = InMemoryVectorStore(dim=dim, distance_metric=distance_metric)
            self._collection = None

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def upsert(self, entries: list[VectorEntry]) -> int:
        """Insert or update entries, returning the number upserted."""
        if self._collection is None:
            assert self._fallback is not None
            return self._fallback.upsert(entries)

        if not entries:
            return 0

        ids = [e.id for e in entries]
        embeddings = [e.vector for e in entries]
        metadatas = [self._sanitize_metadata(e.payload) for e in entries]
        documents = [str(e.payload.get("text", "")) for e in entries]

        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents,
        )
        return len(entries)

    def add_many(self, entries: list[VectorEntry]) -> int:
        """Alias of :meth:`upsert` (compat with the in-memory store)."""
        return self.upsert(entries)

    # ------------------------------------------------------------------
    # Query path
    # ------------------------------------------------------------------

    def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        source_type: str | None = None,
    ) -> list[VectorSearchResult]:
        """Return top-k most similar entries, best first."""
        if self._collection is None:
            assert self._fallback is not None
            return self._fallback.search(query_vector, top_k=top_k, source_type=source_type)

        response = self._collection.query(
            query_embeddings=[query_vector],
            n_results=top_k,
            include=["metadatas", "documents", "distances"],
        )

        results: list[VectorSearchResult] = []
        ids = response.get("ids", [[]])[0]
        distances = response.get("distances", [[]])[0]
        metadatas = response.get("metadatas", [[]])[0]

        for i, doc_id in enumerate(ids):
            distance = distances[i] if i < len(distances) else 1.0
            if self._distance_metric == "cosine":
                # Chroma returns cosine *distance* → convert to similarity
                score = max(0.0, 1.0 - float(distance))
            else:
                score = -float(distance)

            payload = dict(metadatas[i]) if i < len(metadatas) and metadatas[i] else {}
            # Restore list-typed metadata that was flattened on the way in
            payload = self._desanitize_metadata(payload)
            entry_type = payload.get("source_type", str(doc_id).split("_", 1)[0])
            if source_type and entry_type != source_type:
                continue
            results.append(
                VectorSearchResult(
                    id=str(doc_id),
                    score=round(float(score), 4),
                    payload=payload,
                    source_type=str(entry_type),
                )
            )
        return results

    def count(self) -> int:
        if self._collection is None:
            assert self._fallback is not None
            return self._fallback.count()
        try:
            return int(self._collection.count())
        except Exception:
            return 0

    def clear(self) -> None:
        """Delete all vectors from the store."""
        if self._collection is None:
            assert self._fallback is not None
            self._fallback.clear()
            return
        try:
            self._collection.delete()
        except Exception as exc:
            logger.warning("VectorDBStage: clear failed (%s)", exc)

    # ------------------------------------------------------------------
    # Metadata helpers (chroma accepts scalars only)
    # ------------------------------------------------------------------

    @classmethod
    def _sanitize_metadata(cls, payload: dict[str, Any]) -> dict[str, Any]:
        """Flatten payload into chroma-compatible scalar metadata."""
        clean: dict[str, Any] = {}
        for key, value in payload.items():
            if value is None:
                continue
            if isinstance(value, (str, int, float, bool)):
                clean[key] = value
            elif isinstance(value, (list, tuple, set)):
                clean[key] = _METADATA_LIST_SEP.join(str(v) for v in value)
            else:
                clean[key] = str(value)
        return clean

    @classmethod
    def _desanitize_metadata(cls, metadata: dict[str, Any]) -> dict[str, Any]:
        """Restore list-shaped metadata fields flattened by chroma."""
        restored = dict(metadata)
        for key in ("tags", "source_chapters", "knowledge_ids", "related_skills"):
            if key in restored and isinstance(restored[key], str):
                restored[key] = [
                    v.strip() for v in restored[key].split(_METADATA_LIST_SEP) if v.strip()
                ]
        return restored


class VectorDBStage(BaseStage):
    """Pipeline stage that stores embedded chunks/skills in a vector store.

    Uses a persistent ChromaDB collection when available
    (``config.vector_db.persist_dir``), falling back to an in-memory
    store otherwise. The store instance is created once (thread-safe)
    and kept in ``context.stage_results["vector_db"]["store"]`` for
    downstream retrieval by subsequent stages or API consumers.

    Example::

        stage = VectorDBStage(config)
        context = await stage.execute(context)
        store = context.stage_results["vector_db"]["store"]
        results = store.search(query_vector, top_k=5)
        hits = stage.search(query_vector, top_k=5)  # same thing
    """

    def __init__(self, config: PipelineConfig) -> None:
        super().__init__(config)
        self.stage = PipelineStage.VECTOR_DB
        self._vector_config = config.vector_db
        self._store: ChromaVectorStore | None = None
        self._store_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_store(self) -> ChromaVectorStore:
        """Create (once) and return the shared vector store.

        Thread-safe: concurrent callers receive the same instance, and
        the underlying collection is created exactly once.
        """
        if self._store is None:
            with self._store_lock:
                if self._store is None:
                    self._store = ChromaVectorStore(
                        persist_dir=self._vector_config.persist_dir,
                        collection_name=self._vector_config.collection_name,
                        dim=self._vector_config.embedding_dim or 384,
                        distance_metric=self._vector_config.distance_metric,
                    )
        return self._store

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        source_type: str | None = None,
    ) -> list[VectorSearchResult]:
        """Query the vector store for the top-k most similar entries.

        Parameters
        ----------
        query_embedding : list[float]
            Embedding vector to search with.
        top_k : int
            Maximum number of results to return.
        source_type : str | None
            Optional filter — ``"chunk"`` or ``"skill"``.

        Returns
        -------
        list[VectorSearchResult]
            Best matches, sorted by descending score.
        """
        store = self.get_store()
        return store.search(query_embedding, top_k=top_k, source_type=source_type)

    async def process(self, context: PipelineContext) -> PipelineContext:
        """Index all chunks and skills with embeddings into the store.

        Parameters
        ----------
        context : PipelineContext
            Should have chunks and skills with embeddings set.

        Returns
        -------
        PipelineContext
            Context with a ``"store"`` key in ``stage_results["vector_db"]``.
        """
        store = self.get_store()
        book_id = self._book_id(context)

        entries: list[VectorEntry] = []

        # ── Index chunks ────────────────────────────────────────────
        chunk_count = 0
        for chunk in context.chunks:
            if not chunk.embedding:
                continue
            payload: dict[str, Any] = {
                "chunk_id": chunk.id,
                "book_id": book_id,
                "text": chunk.text,
                "text_preview": chunk.text[:200],
                "index": chunk.index,
                "word_count": chunk.word_count,
                "strategy": chunk.strategy.value if chunk.strategy else "",
                "cleaned_id": chunk.cleaned_id,
                "source_type": "chunk",
                "tags": chunk.metadata.get("tags", []),
            }
            entries.append(
                VectorEntry(
                    id=f"chunk_{chunk.id}",
                    vector=chunk.embedding,
                    payload=payload,
                    source_type="chunk",
                    source_id=chunk.id,
                )
            )
            chunk_count += 1

        # ── Index skills ────────────────────────────────────────────
        skill_count = 0
        for skill in context.skills:
            embedding = skill.embedding
            if not embedding:
                continue
            payload = {
                "skill_id": skill.id,
                "book_id": book_id,
                "name": skill.name,
                "description": skill.description[:200],
                "category": skill.category,
                "tags": skill.tags,
                "status": skill.status.value if skill.status else "",
                "quality_score": skill.quality_score,
                "source_type": "skill",
                "source_chapters": skill.source_chapters,
                "knowledge_ids": skill.knowledge_ids,
                "text": (f"{skill.name}. {skill.description} " + " ".join(skill.best_practices)),
            }
            entries.append(
                VectorEntry(
                    id=f"skill_{skill.id}",
                    vector=embedding,
                    payload=payload,
                    source_type="skill",
                    source_id=skill.id,
                )
            )
            skill_count += 1

        store.upsert(entries)

        result = {
            "chunks_indexed": chunk_count,
            "skills_indexed": skill_count,
            "total_vectors": store.count(),
            "dimension": self._vector_config.embedding_dim or 384,
            "backend": store.backend,
            "persist_dir": self._vector_config.persist_dir,
            "collection_name": self._vector_config.collection_name,
            "store": store,
        }
        context.stage_results[self.stage.value] = result

        self.record_metric("chunks_indexed", chunk_count)
        self.record_metric("skills_indexed", skill_count)
        self.record_metric("total_vectors", store.count())
        return context

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _book_id(self, context: PipelineContext) -> str:
        """Stable book identifier for vector metadata."""
        if context.book and context.book.id:
            return context.book.id
        if context.book and context.book.file_hash:
            return context.book.file_hash[:12]
        return ""
