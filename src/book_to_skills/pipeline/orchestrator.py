"""Pipeline orchestrator — manages the 10-stage book-to-skills pipeline.

Handles stage ordering, parallel execution, incremental processing,
caching, persistence, and metrics collection.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import typer

from ..cache.cache_manager import CacheManager
from ..config import PipelineConfig
from ..domain.enums import PipelineStage
from ..domain.models import (
    Book,
    HermesSkill,
    PipelineContext,
    ProcessingResult,
)
from ..monitoring.metrics import MetricsCollector
from ..pipeline.chunk import ChunkStage
from ..pipeline.clean import CleanStage
from ..pipeline.dedup import DedupStage
from ..pipeline.embeddings import EmbeddingsStage

# ---------------------------------------------------------------------------
# Stage imports — all 10 concrete stages
# ---------------------------------------------------------------------------
from ..pipeline.extract import ExtractStage
from ..pipeline.kg import KnowledgeGraphStage
from ..pipeline.knowledge import KnowledgeStage
from ..pipeline.review import ReviewStage
from ..pipeline.skill_gen import SkillGenStage
from ..pipeline.vector_db import VectorDBStage
from ..storage.file_store import FileStore
from ..utils.hash_utils import compute_file_hash

# ---------------------------------------------------------------------------
# Stage registry
# ---------------------------------------------------------------------------

STAGE_REGISTRY: dict[PipelineStage, type] = {
    PipelineStage.EXTRACT: ExtractStage,
    PipelineStage.CLEAN: CleanStage,
    PipelineStage.CHUNK: ChunkStage,
    PipelineStage.KNOWLEDGE: KnowledgeStage,
    PipelineStage.SKILL_GEN: SkillGenStage,
    PipelineStage.REVIEW: ReviewStage,
    PipelineStage.DEDUP: DedupStage,
    PipelineStage.KNOWLEDGE_GRAPH: KnowledgeGraphStage,
    PipelineStage.EMBEDDINGS: EmbeddingsStage,
    PipelineStage.VECTOR_DB: VectorDBStage,
}

STAGE_ORDER: list[PipelineStage] = [
    PipelineStage.EXTRACT,
    PipelineStage.CLEAN,
    PipelineStage.CHUNK,
    PipelineStage.KNOWLEDGE,
    PipelineStage.SKILL_GEN,
    PipelineStage.REVIEW,
    PipelineStage.DEDUP,
    PipelineStage.KNOWLEDGE_GRAPH,
    PipelineStage.EMBEDDINGS,
    PipelineStage.VECTOR_DB,
]


class PipelineOrchestrator:
    """Orchestrates the full book-to-skills pipeline.

    Responsibilities:
    - Stage ordering and execution (sequential / parallel)
    - Incremental processing (skip unchanged files via file hash)
    - Caching stage outputs via :class:`~book_to_skills.cache.CacheManager`
    - Persisting results via :class:`~book_to_skills.storage.FileStore`
    - Collecting metrics via :class:`~book_to_skills.monitoring.MetricsCollector`
    - Error handling and partial-run support
    """

    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()
        self.cache = CacheManager(self.config.cache)
        self.store = FileStore(self.config)
        self.metrics = MetricsCollector()

        # Instantiate enabled stages
        self._stages: dict[PipelineStage, Any] = {}
        for stage in STAGE_ORDER:
            if stage.value in self.config.stages_enabled:
                constructor = STAGE_REGISTRY.get(stage)
                if constructor:
                    self._stages[stage] = constructor(self.config)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_pipeline(
        self,
        file_path: str,
        stages: list[str] | None = None,
        incremental: bool | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> PipelineContext:
        """Run the full pipeline on a single book file.

        Args:
            file_path: Path to the book file (PDF or DOCX).
            stages: Optional subset of stage names to run. If ``None``, runs all
                enabled stages from config.
            incremental: If ``True``, skip stages whose inputs haven't changed
                (based on file hash). Defaults to ``config.incremental_mode``.

        Returns:
            :class:`~book_to_skills.domain.models.PipelineContext` carrying
            the final state after all stages.
        """
        effective_incremental = self._resolve_incremental(incremental)

        # Build initial context
        context = await self._build_initial_context(file_path)

        # Determine which stages to run
        stage_filter: list[PipelineStage] = (
            [PipelineStage(s) for s in stages] if stages else STAGE_ORDER
        )
        to_run = [s for s in stage_filter if s in self._stages]

        try:
            if self.config.run_parallel_stages and len(to_run) > 1:
                context = await self._run_parallel(
                    context, to_run, effective_incremental, progress_callback
                )
            else:
                context = await self._run_sequential(
                    context, to_run, effective_incremental, progress_callback
                )

            # ── Persist generated skills to the output store ──────────────
            saved = 0
            existing_names = {s.name for s in await self.store.list_skills()}

            # Stamp provenance on every skill before saving so that
            # incremental runs can match skills back to their source book.
            book_id = ""
            source_book = ""
            if context.book:
                book_id = context.book.file_hash[:12] or context.book.id
                source_book = Path(context.book.file_path).name

            for skill in context.skills:
                if not (skill.name and skill.description):
                    continue
                if not skill.book_id and book_id:
                    skill.book_id = book_id
                if not skill.source_book and source_book:
                    skill.source_book = source_book
                # Deduplicate: same skill name already persisted → skip
                if skill.name in existing_names:
                    continue
                try:
                    await self.store.save_skill(skill)
                    existing_names.add(skill.name)
                    saved += 1
                except Exception:
                    continue

            context.mark_completed()
            context.stage_results["skills_saved"] = saved
        except Exception as exc:
            context.add_error("pipeline", str(exc))
        finally:
            try:
                await self.metrics.reset()
            except Exception:
                pass

        return context

    async def run_stage(
        self,
        stage_name: str,
        file_path: str,
    ) -> ProcessingResult:
        """Run a single pipeline stage on a book file and return its result.

        Args:
            stage_name: One of ``extract``, ``clean``, ``chunk``, ``knowledge``,
                ``skill_gen``, ``review``, ``dedup``, ``knowledge_graph``,
                ``embeddings``, ``vector_db``.
            file_path: Path to the book file.

        Returns:
            :class:`~book_to_skills.domain.models.ProcessingResult`
        """
        stage_enum = PipelineStage(stage_name)
        stage = self._stages.get(stage_enum)

        if stage is None:
            raise ValueError(
                f"Stage '{stage_name}' is not available or not enabled. "
                f"Enabled: {list(self._stages.keys())}"
            )

        context = await self._build_initial_context(file_path)
        return await stage.execute(context)

    async def run_all(
        self,
        stages: list[str] | None = None,
        incremental: bool | None = None,
    ) -> list[PipelineContext]:
        """Run the pipeline on every book in the project.

        Searches for books in ``books/`` first, then falls back to
        ``data/books/``.

        When *incremental* is ``True`` (default), books whose output skills
        already exist on disk are skipped.

        Returns:
            List of :class:`~book_to_skills.domain.models.PipelineContext`
            objects, one per book.
        """
        _incr = self.config.incremental_mode if incremental is None else incremental

        # Search both possible book directories
        candidates: list[Path] = []
        for d in (Path("books"), Path(self.config.data_dir) / "books"):
            if d.exists():
                candidates.append(d)

        if not candidates:
            raise FileNotFoundError(
                "No books directory found. Place PDF/DOCX files in a 'books/' folder."
            )

        supported = {".pdf", ".docx", ".doc"}
        book_files: list[Path] = []
        for cd in candidates:
            book_files.extend(p for p in cd.iterdir() if p.suffix.lower() in supported)
        book_files = sorted(set(book_files))  # dedupe + sort

        if not book_files:
            raise FileNotFoundError(
                f"No supported book files (.pdf, .docx) found in {[str(d) for d in candidates]}"
            )

        typer.secho(
            f"\n📚 Found {len(book_files)} book(s) to process\n",
            fg=typer.colors.CYAN,
        )

        results: list[PipelineContext] = []
        for bf in book_files:
            # ── book-level incremental skip ─────────────────────────────
            if _incr:
                from ..utils.hash_utils import compute_file_hash

                file_hash = compute_file_hash(str(bf))
                # Check if any skill file already references this book —
                # either via the deterministic ``book_id`` (file hash
                # prefix) or via the saved ``source_book`` file name.
                skills_dir = Path(self.config.storage.skills_dir)
                if skills_dir.exists():
                    skip = False
                    for sf in skills_dir.glob("*.json"):
                        try:
                            data = json.loads(sf.read_text(encoding="utf-8"))
                            if (
                                data.get("book_id", "") == file_hash[:12]
                                or data.get("source_book", "") == bf.name
                            ):
                                skip = True
                                break
                        except Exception:
                            continue
                    if skip:
                        typer.secho(
                            f"  ⏭️  {bf.name} — سبق معالجته، تم التخطي",
                            fg=typer.colors.YELLOW,
                        )
                        continue

            typer.secho(f"  ▶️  {bf.name} ...", fg=typer.colors.GREEN, bold=True)
            ctx = await self.run_pipeline(
                file_path=str(bf),
                stages=stages,
                incremental=incremental,
            )
            results.append(ctx)

        return results

    # ------------------------------------------------------------------
    # Book / skill listing
    # ------------------------------------------------------------------

    def list_books(self) -> list[dict[str, Any]]:
        """Return metadata for all known book files in the project.

        Searches ``books/`` first, then falls back to ``data/books/``.
        """
        candidates = [Path("books"), Path(self.config.data_dir) / "books"]
        supported = {".pdf", ".docx", ".doc"}

        books: list[dict[str, Any]] = []
        seen: set[str] = set()
        for books_dir in candidates:
            if not books_dir.exists():
                continue
            for p in sorted(books_dir.iterdir()):
                if p.suffix.lower() in supported and p.name not in seen:
                    seen.add(p.name)
                    books.append({
                        "file_path": str(p),
                        "file_name": p.name,
                        "size_bytes": p.stat().st_size,
                        "size_mb": round(p.stat().st_size / (1024 * 1024), 2),
                        "format": p.suffix.lstrip(".").lower(),
                        "hash": compute_file_hash(str(p)),
                    })
        return books

    async def list_skills(
        self,
        category: str | None = None,
        status: str | None = None,
        tags: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[HermesSkill]:
        """Return all generated skills from the output store.

        Args:
            category: Filter by exact category match.
            status: Filter by skill status (e.g. ``"approved"``).
            tags: Filter by tags (skill must have at least one matching tag).
            limit: Maximum number of skills to return.
            offset: Number of skills to skip (for pagination).

        Returns:
            List of :class:`~book_to_skills.domain.models.HermesSkill`
            objects (with ``source_book`` populated) sorted by
            ``updated_at`` descending.
        """
        return await self.store.list_skills(
            category=category,
            status=status,
            tags=tags,
            limit=limit,
            offset=offset,
        )

    async def search_skills(self, query: str, limit: int = 50) -> list[HermesSkill]:
        """Keyword search over all persisted skills.

        Matches (case-insensitive) against the skill name, description,
        tags, category, source book and all content sections. When the
        query contains multiple words, every word must match somewhere
        in the skill (AND semantics). Results are ranked by the number
        of distinct fields matched, with name matches weighted highest.

        Args:
            query: Space-separated search keywords.
            limit: Maximum number of results to return.

        Returns:
            List of :class:`~book_to_skills.domain.models.HermesSkill`
            objects ranked by relevance.
        """
        terms = [t for t in re.split(r"\s+", query.strip().lower()) if t]
        if not terms:
            return []

        # Load all skills (FileStore paginates internally).
        all_skills: list[HermesSkill] = []
        offset = 0
        while True:
            batch = await self.store.list_skills(limit=500, offset=offset)
            if not batch:
                break
            all_skills.extend(batch)
            offset += len(batch)

        scored: list[tuple[int, HermesSkill]] = []
        for skill in all_skills:
            haystack = self._skill_search_text(skill)
            if not all(term in haystack for term in terms):
                continue
            # Rank: distinct matching fields, name matches count double.
            field_hits = sum(
                1
                for field in self._skill_search_fields(skill)
                if any(term in field for term in terms)
            )
            name_hits = sum(term in skill.name.lower() for term in terms)
            scored.append((field_hits + 2 * name_hits, skill))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [skill for _, skill in scored[:limit]]

    @staticmethod
    def _skill_search_fields(skill: HermesSkill) -> list[str]:
        """Return the searchable fields of a skill as lowercase strings."""
        fields = [
            skill.name,
            skill.description,
            skill.category,
            skill.source_book,
            skill.review_feedback,
        ]
        fields.extend(skill.tags)
        fields.extend(skill.best_practices)
        fields.extend(skill.pitfalls)
        fields.extend(skill.checklist)
        fields.extend(skill.references)
        fields.extend(step.get("title", "") for step in skill.workflow)
        fields.extend(step.get("description", "") for step in skill.workflow)
        fields.extend(ex.get("title", "") for ex in skill.examples)
        fields.extend(ex.get("code", "") for ex in skill.examples)
        return [f.lower() for f in fields if f]

    @classmethod
    def _skill_search_text(cls, skill: HermesSkill) -> str:
        """Return the full lowercase searchable text of a skill."""
        return " ".join(cls._skill_search_fields(skill))

    async def clear_cache(self) -> None:
        """Clear all cached stage results and reset metrics."""
        await self.cache.clear()
        await self.metrics.hard_reset()

    # ------------------------------------------------------------------
    # Internal — sequential execution
    # ------------------------------------------------------------------

    async def _run_sequential(
        self,
        context: PipelineContext,
        stages: list[PipelineStage],
        incremental: bool,
        progress_callback: Callable[[str], None] | None = None,
    ) -> PipelineContext:
        """Run pipeline stages one at a time in order."""
        for stage_enum in stages:
            stage = self._stages.get(stage_enum)
            if stage is None:
                continue

            if progress_callback:
                progress_callback(stage_enum.value)

            if incremental and await self._should_skip(stage_enum, context):
                # Restore full context from the last checkpoint so the
                # remaining stages see the data produced so far.
                restored = await self._restore_context(context)
                if restored is not None:
                    context = restored
                continue

            start = time.monotonic()
            result = await stage.execute(context)

            duration = time.monotonic() - start
            self.metrics.record_stage(
                stage_name=stage_enum.value,
                duration_s=duration,
                success=result.success,
            )

            if not result.success:
                context.add_error(stage_enum.value, result.error or "Unknown error")
                if self.config.skip_on_error:
                    continue
                raise RuntimeError(f"Pipeline stage '{stage_enum.value}' failed: {result.error}")

            # Cache the light stage result for every stage (fast skip),
            # but only checkpoint the full context at milestone stages.
            if incremental:
                cache_key = self._cache_key(stage_enum, context)
                await self.cache.set(cache_key, result.model_dump(mode="json"))
                if stage_enum in (
                    PipelineStage.EXTRACT,
                    PipelineStage.CHUNK,
                    PipelineStage.SKILL_GEN,
                ):
                    await self._checkpoint_context(context)

        return context

    # ------------------------------------------------------------------
    # Internal — parallel execution
    # ------------------------------------------------------------------

    async def _run_parallel(
        self,
        context: PipelineContext,
        stages: list[PipelineStage],
        incremental: bool,
        progress_callback: Callable[[str], None] | None = None,
    ) -> PipelineContext:
        """Run pipeline stages in parallel where possible.

        Stages are grouped into waves (one per stage) and run sequentially
        by wave to respect data dependencies, with each wave's stages
        executing concurrently.
        """
        waves: list[list[PipelineStage]] = [[s] for s in stages]

        for wave in waves:
            if incremental:
                wave = [s for s in wave if not await self._should_skip(s, context)]

            if not wave:
                continue

            tasks = []
            for stage_enum in wave:
                stage = self._stages.get(stage_enum)
                if stage:
                    tasks.append(stage.execute(context))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for stage_enum, result in zip(wave, results, strict=False):
                if isinstance(result, Exception):
                    context.add_error(stage_enum.value, str(result))
                    if not self.config.skip_on_error:
                        raise RuntimeError(f"Pipeline stage '{stage_enum.value}' failed: {result}")
                    continue

                self.metrics.record_stage(
                    stage_name=stage_enum.value,
                    duration_s=result.duration_s,
                    success=result.success,
                )

                if incremental and result.success:
                    cache_key = self._cache_key(stage_enum, context)
                    await self.cache.set(cache_key, result.model_dump(mode="json"))

        return context

    # ------------------------------------------------------------------
    # Internal — helpers
    # ------------------------------------------------------------------

    async def _build_initial_context(self, file_path: str) -> PipelineContext:
        """Create a fresh :class:`PipelineContext` for the given file."""
        file_hash = compute_file_hash(file_path)
        from ..domain.enums import BookFormat

        book = Book(
            file_path=file_path,
            format=BookFormat.from_extension(file_path),
            file_hash=file_hash,
            file_size_bytes=Path(file_path).stat().st_size,
        )
        return PipelineContext(book=book)

    def _resolve_incremental(self, override: bool | None) -> bool:
        """Resolve the effective incremental mode."""
        return override if override is not None else self.config.incremental_mode

    async def _should_skip(self, stage: PipelineStage, context: PipelineContext) -> bool:
        """Check whether a stage can be skipped due to incremental mode."""
        cache_key = self._cache_key(stage, context)
        cached = await self.cache.get(cache_key)
        return cached is not None

    async def _checkpoint_context(self, context: PipelineContext) -> None:
        """Persist the full pipeline context as a checkpoint.

        Enables incremental resume: the next run restores the context
        from the latest checkpoint instead of starting from scratch.
        """
        if not context.book:
            return
        checkpoint_key = f"ctx:{context.book.file_hash}"
        try:
            await self.cache.set(checkpoint_key, context.model_dump(mode="json"))
        except Exception:
            pass  # checkpointing is best-effort

    async def _restore_context(self, context: PipelineContext) -> PipelineContext | None:
        """Restore a pipeline context from the latest checkpoint."""
        if not context.book:
            return None
        checkpoint_key = f"ctx:{context.book.file_hash}"
        try:
            data = await self.cache.get(checkpoint_key)
            if not data:
                return None
            restored = PipelineContext.model_validate(data)
            # Carry over the current run's identity (fresh run_id + book)
            restored.run_id = context.run_id
            restored.started_at = context.started_at
            restored.completed_at = None
            restored.current_stage = context.current_stage
            if restored.book is None and context.book is not None:
                restored.book = context.book
            return restored
        except Exception:
            return None

    @staticmethod
    def _cache_key(stage: PipelineStage, context: PipelineContext) -> str:
        """Generate a deterministic cache key for a stage result."""
        file_hash = context.book.file_hash if context.book else "unknown"
        return f"{stage.value}:{file_hash}"
