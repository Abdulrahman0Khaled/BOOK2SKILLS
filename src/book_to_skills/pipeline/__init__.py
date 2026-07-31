"""Pipeline stages for the book-to-skills system.

Each stage inherits from :class:`~book_to_skills.pipeline.base.BaseStage`
and implements ``async process(context) -> PipelineContext``.
"""

from __future__ import annotations

from .base import BaseStage
from .chunk import ChunkStage
from .clean import CleanStage
from .dedup import DedupStage
from .embeddings import EmbeddingsStage
from .extract import ExtractStage
from .kg import KnowledgeGraphStage
from .knowledge import KnowledgeStage
from .orchestrator import PipelineOrchestrator
from .review import ReviewStage
from .skill_gen import SkillGenStage
from .vector_db import VectorDBStage

__all__ = [
    "BaseStage",
    "ChunkStage",
    "CleanStage",
    "DedupStage",
    "EmbeddingsStage",
    "ExtractStage",
    "KnowledgeGraphStage",
    "KnowledgeStage",
    "PipelineOrchestrator",
    "ReviewStage",
    "SkillGenStage",
    "VectorDBStage",
]
