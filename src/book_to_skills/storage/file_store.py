"""File-based persistent storage for skills and knowledge graphs.

Provides a ``FileStore`` that saves generated Hermes skills as JSON files
with rich metadata, and persists knowledge graphs as structured JSON.
All data lives under the ``outputs/skills`` directory by default,
matching the pipeline's ``StorageConfig``.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from book_to_skills.config import PipelineConfig, StorageConfig
from book_to_skills.domain.models import HermesSkill, KnowledgeGraph
from book_to_skills.utils.file_utils import ensure_dir, read_json, write_json


class FileStore:
    """Persistent file storage for skills and knowledge graphs.

    Skills are stored as individual JSON files in a configured output
    directory, each carrying full metadata (creation time, source book,
    quality score, generation info, etc.). Knowledge graphs are saved
    as single JSON files representing the full graph structure.

    All operations are thread-safe.

    Usage::

        store = FileStore(config.storage)
        await store.save_skill(skill)
        skill = await store.load_skill(skill_id)
        skills = await store.list_skills()
        await store.save_knowledge_graph(graph)
    """

    def __init__(
        self,
        config: StorageConfig | PipelineConfig | None = None,
        skills_dir: str | Path | None = None,
        knowledge_dir: str | Path | None = None,
    ) -> None:
        # Normalise: accept either StorageConfig or PipelineConfig
        raw_config = config or StorageConfig()
        if isinstance(raw_config, PipelineConfig):
            resolved_config: StorageConfig = raw_config.storage
        else:
            resolved_config = raw_config
        self._config = resolved_config

        # Resolve directories
        self._skills_dir: Path = ensure_dir(skills_dir or self._config.skills_dir)
        self._knowledge_dir: Path = ensure_dir(knowledge_dir or self._config.knowledge_graph_dir)

        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Skills CRUD
    # ------------------------------------------------------------------

    async def save_skill(self, skill: HermesSkill) -> str:
        """Persist a skill to disk as JSON.

        The skill is written to ``{skills_dir}/{skill_id}.json``.
        If the skill already has an ID, it is reused; otherwise one is
        generated.

        Args:
            skill: The ``HermesSkill`` instance to persist.

        Returns:
            The skill ID.
        """
        if not skill.id:
            skill.id = uuid.uuid4().hex[:12]
        skill.updated_at = datetime.now(UTC)

        data = self._skill_to_dict(skill)
        file_path = self._skills_dir / f"{skill.id}.json"
        with self._lock:
            write_json(file_path, data)
        return skill.id

    async def load_skill(self, skill_id: str) -> HermesSkill | None:
        """Load a skill from disk by its ID.

        Args:
            skill_id: The unique skill identifier.

        Returns:
            A ``HermesSkill`` instance, or ``None`` if not found.
        """
        file_path = self._skills_dir / f"{skill_id}.json"
        if not file_path.exists():
            return None
        try:
            with self._lock:
                data = read_json(file_path)
            return self._dict_to_skill(data)
        except (json.JSONDecodeError, KeyError, OSError):
            return None

    async def list_skills(
        self,
        category: str | None = None,
        status: str | None = None,
        tags: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[HermesSkill]:
        """List all persisted skills with optional filtering.

        Args:
            category: Filter by exact category match.
            status: Filter by skill status (e.g. ``"draft"``, ``"published"``).
            tags: Filter by tags (skill must have at least one matching tag).
            limit: Maximum number of skills to return.
            offset: Number of skills to skip (for pagination).

        Returns:
            A list of ``HermesSkill`` instances sorted by ``updated_at``
            descending.
        """
        skills: list[HermesSkill] = []
        pattern = "*.json"
        with self._lock:
            json_files = sorted(
                self._skills_dir.glob(pattern),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

        for fp in json_files[offset : offset + limit]:
            try:
                data = read_json(fp)
                skill = self._dict_to_skill(data)
            except (json.JSONDecodeError, KeyError, OSError):
                continue

            # Apply filters
            if category and skill.category != category:
                continue
            if status and skill.status.value != status:
                continue
            if tags and not any(t in skill.tags for t in tags):
                continue

            skills.append(skill)

        return skills

    async def delete_skill(self, skill_id: str) -> bool:
        """Delete a skill file by ID.

        Args:
            skill_id: The skill identifier to remove.

        Returns:
            ``True`` if the file existed and was deleted.
        """
        file_path = self._skills_dir / f"{skill_id}.json"
        if not file_path.exists():
            return False
        with self._lock:
            file_path.unlink(missing_ok=True)
        return True

    async def skill_count(self) -> int:
        """Return the total number of persisted skills."""
        with self._lock:
            return len(list(self._skills_dir.glob("*.json")))

    async def skill_exists(self, skill_id: str) -> bool:
        """Check whether a skill file exists on disk."""
        return (self._skills_dir / f"{skill_id}.json").exists()

    # ------------------------------------------------------------------
    # Knowledge Graph
    # ------------------------------------------------------------------

    async def save_knowledge_graph(self, graph: KnowledgeGraph) -> str:
        """Persist a knowledge graph to disk.

        The graph is written as ``{knowledge_dir}/{graph_id}.json``.
        If the graph already has an ID it is reused; otherwise one is
        generated.

        Args:
            graph: The ``KnowledgeGraph`` instance to persist.

        Returns:
            The knowledge graph ID.
        """
        if not graph.id:
            graph.id = uuid.uuid4().hex[:12]
        graph.created_at = datetime.now(UTC)

        data = {
            "id": graph.id,
            "nodes": graph.nodes,
            "edges": graph.edges,
            "created_at": graph.created_at.isoformat(),
        }
        file_path = self._knowledge_dir / f"{graph.id}.json"
        with self._lock:
            write_json(file_path, data)
        return graph.id

    async def load_knowledge_graph(self, graph_id: str) -> KnowledgeGraph | None:
        """Load a knowledge graph from disk by ID.

        Args:
            graph_id: The knowledge graph identifier.

        Returns:
            A ``KnowledgeGraph`` instance, or ``None`` if not found.
        """
        file_path = self._knowledge_dir / f"{graph_id}.json"
        if not file_path.exists():
            return None
        try:
            with self._lock:
                data = read_json(file_path)
            return KnowledgeGraph(
                id=data["id"],
                nodes=data.get("nodes", []),
                edges=data.get("edges", []),
                created_at=datetime.fromisoformat(data["created_at"])
                if "created_at" in data
                else datetime.now(UTC),
            )
        except (json.JSONDecodeError, KeyError, OSError):
            return None

    async def list_knowledge_graphs(self, limit: int = 10, offset: int = 0) -> list[KnowledgeGraph]:
        """List all persisted knowledge graphs.

        Args:
            limit: Maximum number of graphs to return.
            offset: Number of graphs to skip (for pagination).

        Returns:
            A list of ``KnowledgeGraph`` instances sorted by creation time
            descending.
        """
        graphs: list[KnowledgeGraph] = []
        with self._lock:
            json_files = sorted(
                self._knowledge_dir.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

        for fp in json_files[offset : offset + limit]:
            try:
                data = read_json(fp)
                graph = KnowledgeGraph(
                    id=data["id"],
                    nodes=data.get("nodes", []),
                    edges=data.get("edges", []),
                    created_at=datetime.fromisoformat(data["created_at"])
                    if "created_at" in data
                    else datetime.now(UTC),
                )
                graphs.append(graph)
            except (json.JSONDecodeError, KeyError, OSError):
                continue

        return graphs

    async def delete_knowledge_graph(self, graph_id: str) -> bool:
        """Delete a knowledge graph file by ID."""
        file_path = self._knowledge_dir / f"{graph_id}.json"
        if not file_path.exists():
            return False
        with self._lock:
            file_path.unlink(missing_ok=True)
        return True

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    async def stats(self) -> dict[str, Any]:
        """Return storage statistics (file counts, directory sizes)."""
        with self._lock:
            skill_files = list(self._skills_dir.glob("*.json"))
            graph_files = list(self._knowledge_dir.glob("*.json"))
            skills_size = sum(p.stat().st_size for p in skill_files)
            graphs_size = sum(p.stat().st_size for p in graph_files)

        return {
            "skills_count": len(skill_files),
            "skills_size_bytes": skills_size,
            "knowledge_graphs_count": len(graph_files),
            "knowledge_graphs_size_bytes": graphs_size,
            "skills_dir": str(self._skills_dir),
            "knowledge_graph_dir": str(self._knowledge_dir),
        }

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _skill_to_dict(skill: HermesSkill) -> dict[str, Any]:
        """Convert a ``HermesSkill`` to a JSON-serialisable dict."""
        return {
            "id": skill.id,
            "knowledge_ids": skill.knowledge_ids,
            "book_id": skill.book_id,
            "source_book": skill.source_book,
            "source_chapters": skill.source_chapters,
            "name": skill.name,
            "description": skill.description,
            "version": skill.version,
            "examples": skill.examples,
            "best_practices": skill.best_practices,
            "pitfalls": skill.pitfalls,
            "workflow": skill.workflow,
            "checklist": skill.checklist,
            "references": skill.references,
            "tags": skill.tags,
            "category": skill.category,
            "related_skills": skill.related_skills,
            "status": skill.status.value,
            "quality_score": skill.quality_score,
            "review_feedback": skill.review_feedback,
            "review_notes": skill.review_notes,
            "model_used": skill.model_used,
            "prompt_tokens": skill.prompt_tokens,
            "completion_tokens": skill.completion_tokens,
            "created_at": skill.created_at.isoformat(),
            "updated_at": skill.updated_at.isoformat(),
        }

    @staticmethod
    def _dict_to_skill(data: dict[str, Any]) -> HermesSkill:
        """Convert a JSON dict back to a ``HermesSkill``."""
        return HermesSkill(
            id=data.get("id", ""),
            knowledge_ids=data.get("knowledge_ids", []),
            book_id=data.get("book_id", ""),
            source_book=data.get("source_book", ""),
            source_chapters=data.get("source_chapters", []),
            name=data.get("name", ""),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            examples=data.get("examples", []),
            best_practices=data.get("best_practices", []),
            pitfalls=data.get("pitfalls", []),
            workflow=data.get("workflow", []),
            checklist=data.get("checklist", []),
            references=data.get("references", []),
            tags=data.get("tags", []),
            category=data.get("category", ""),
            related_skills=data.get("related_skills", []),
            status=data.get("status", "draft"),
            quality_score=data.get("quality_score", 0.0),
            review_feedback=data.get("review_feedback", ""),
            review_notes=data.get("review_notes", []),
            model_used=data.get("model_used", ""),
            prompt_tokens=data.get("prompt_tokens", 0),
            completion_tokens=data.get("completion_tokens", 0),
            created_at=data.get("created_at", datetime.now(UTC)),
            updated_at=data.get("updated_at", datetime.now(UTC)),
        )

    def __repr__(self) -> str:
        return f"FileStore(skills_dir={self._skills_dir}, knowledge_dir={self._knowledge_dir})"
