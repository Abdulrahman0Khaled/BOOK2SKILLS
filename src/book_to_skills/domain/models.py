"""Domain models for the book-to-skills pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from .enums import (
    BookFormat,
    ChunkStrategy,
    ExtractionMethod,
    PipelineStage,
    SkillStatus,
)


class Book(BaseModel):
    """Represents a book loaded into the pipeline."""

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    title: str | None = None
    file_path: str
    format: BookFormat
    file_size_bytes: int = 0
    file_hash: str = ""  # SHA-256 of raw file
    total_pages: int = 0
    language: str = "en"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("file_path cannot be empty")
        return v


class ExtractedContent(BaseModel):
    """Raw extracted text content from a book."""

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    book_id: str
    text: str
    method: ExtractionMethod = ExtractionMethod.DIRECT
    pages: dict[int, str] = Field(default_factory=dict)  # page_number -> text
    extraction_time_s: float = 0.0
    word_count: int = 0
    quality_score: float = 0.0  # 0.0 - 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("extracted text cannot be empty")
        return v


class CleanedContent(BaseModel):
    """Cleaned and normalized text content."""

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    extract_id: str
    text: str
    original_word_count: int = 0
    cleaned_word_count: int = 0
    transformations: list[str] = Field(default_factory=list)
    quality_score: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TextChunk(BaseModel):
    """A semantic chunk of text from a book."""

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    cleaned_id: str
    index: int = 0
    text: str
    word_count: int = 0
    strategy: ChunkStrategy = ChunkStrategy.SEMANTIC
    embedding: list[float] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class KnowledgeUnit(BaseModel):
    """An extracted piece of knowledge from a chunk."""

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    chunk_id: str
    book_id: str = ""
    source_book: str = ""
    unit_type: str  # skill, best_practice, anti_pattern, rule, workflow, etc.
    title: str
    content: str
    confidence: float = 0.0
    source_reference: str = ""  # chapter/section reference
    tags: list[str] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class HermesSkill(BaseModel):
    """A generated AI Agent Skill (compatible with OpenClaw, Claude, Codex, Hermes, etc.) complete with all sections."""

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    knowledge_ids: list[str] = Field(default_factory=list)
    book_id: str = ""
    source_book: str = ""  # book title/filename for provenance
    source_chapters: list[str] = Field(default_factory=list)

    # Core skill fields
    name: str = ""
    description: str = ""
    version: str = "1.0.0"

    # Structured sections
    examples: list[dict[str, str]] = Field(default_factory=list)
    best_practices: list[str] = Field(default_factory=list)
    pitfalls: list[str] = Field(default_factory=list)
    workflow: list[dict[str, str]] = Field(default_factory=list)
    checklist: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)

    # Metadata
    tags: list[str] = Field(default_factory=list)
    category: str = ""
    related_skills: list[str] = Field(default_factory=list)
    status: SkillStatus = SkillStatus.DRAFT
    quality_score: float = 0.0

    # Review feedback (populated by ReviewStage)
    review_feedback: str = ""
    review_notes: list[str] = Field(default_factory=list)

    # Vector embedding (set by EmbeddingsStage)
    embedding: list[float] | None = None

    # Generation info
    model_used: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_skill_markdown(self) -> str:
        """Render the skill as an AI agent-compatible SKILL.md file (OpenClaw, Claude, Codex, Hermes, etc.)."""
        lines = ["---", f"name: {self.name}", f'description: "{self.description}"']

        if self.version:
            lines.append(f"version: {self.version}")

        if self.tags:
            lines.append(f"tags: [{', '.join(self.tags)}]")

        if self.related_skills:
            lines.append(f"related_skills: [{', '.join(self.related_skills)}]")

        if self.category:
            lines.append(f"category: {self.category}")

        lines.append("---\n")

        # Description section
        lines.append(f"# {self.name}\n")
        lines.append(f"{self.description}\n")

        # Best Practices
        if self.best_practices:
            lines.append("## Best Practices\n")
            for bp in self.best_practices:
                lines.append(f"- {bp}")
            lines.append("")

        # Workflow
        if self.workflow:
            lines.append("## Workflow\n")
            for i, step in enumerate(self.workflow, 1):
                title = step.get("title", f"Step {i}")
                desc = step.get("description", "")
                lines.append(f"### {i}. {title}")
                if desc:
                    lines.append(f"\n{desc}\n")

        # Examples
        if self.examples:
            lines.append("## Examples\n")
            for ex in self.examples:
                title = ex.get("title", "Example")
                code = ex.get("code", "")
                lines.append(f"### {title}")
                lines.append(f"```\n{code}\n```\n")

        # Pitfalls
        if self.pitfalls:
            lines.append("## Pitfalls\n")
            for pit in self.pitfalls:
                lines.append(f"- ⚠️ {pit}")
            lines.append("")

        # Checklist
        if self.checklist:
            lines.append("## Checklist\n")
            for item in self.checklist:
                lines.append(f"- [ ] {item}")
            lines.append("")

        # References
        if self.references:
            lines.append("## References\n")
            for ref in self.references:
                lines.append(f"- {ref}")
            lines.append("")

        return "\n".join(lines)


class PipelineContext(BaseModel):
    """Full context for a pipeline run, carried through all stages."""

    run_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    book: Book | None = None
    extracted: ExtractedContent | None = None
    cleaned: CleanedContent | None = None
    chunks: list[TextChunk] = Field(default_factory=list)
    knowledge_units: list[KnowledgeUnit] = Field(default_factory=list)
    skills: list[HermesSkill] = Field(default_factory=list)
    current_stage: PipelineStage = PipelineStage.EXTRACT
    stage_results: dict[str, Any] = Field(default_factory=dict)
    errors: list[dict[str, str]] = Field(default_factory=list)
    knowledge_graph: KnowledgeGraph | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    total_duration_s: float = 0.0

    def add_error(self, stage: str, message: str) -> None:
        self.errors.append({
            "stage": stage,
            "message": message,
            "timestamp": datetime.now(UTC).isoformat(),
        })

    def mark_completed(self) -> None:
        self.completed_at = datetime.now(UTC)
        if self.started_at:
            self.total_duration_s = (self.completed_at - self.started_at).total_seconds()


class ProcessingResult(BaseModel):
    """Result of a single pipeline stage."""

    stage: PipelineStage
    success: bool
    context_id: str
    output: dict[str, Any] = Field(default_factory=dict)
    duration_s: float = 0.0
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)


class KnowledgeGraph(BaseModel):
    """Knowledge graph representation for relationships between skills."""

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# Aliases for universal AI Agent skills (OpenClaw, Claude, Codex, Hermes, etc.)
AgentSkill = HermesSkill
Skill = HermesSkill
