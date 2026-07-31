"""Unit tests for domain models."""

from __future__ import annotations

from datetime import datetime

from book_to_skills.domain.enums import BookFormat, LLMProvider, PipelineStage, SkillStatus
from book_to_skills.domain.models import (
    Book,
    ExtractedContent,
    HermesSkill,
    KnowledgeUnit,
    PipelineContext,
    ProcessingResult,
    TextChunk,
)


class TestBook:
    """Test Book model."""

    def test_create_book(self):
        book = Book(
            file_path="/tmp/test.pdf",
            format=BookFormat.PDF,
            title="Test Book",
        )
        assert book.title == "Test Book"
        assert book.file_path == "/tmp/test.pdf"
        assert book.format == BookFormat.PDF
        assert book.id is not None
        assert len(book.id) == 12
        assert isinstance(book.created_at, datetime)
        assert isinstance(book.updated_at, datetime)

    def test_book_defaults(self):
        book = Book(file_path="/tmp/test.pdf", format=BookFormat.PDF)
        assert book.file_hash == ""
        assert book.total_pages == 0
        assert book.language == "en"
        assert book.metadata == {}

    def test_book_auto_id(self):
        b1 = Book(file_path="/tmp/a.pdf", format=BookFormat.PDF)
        b2 = Book(file_path="/tmp/b.pdf", format=BookFormat.PDF)
        assert b1.id != b2.id  # unique IDs

    def test_book_empty_path_raises(self):
        import pytest

        with pytest.raises(ValueError):
            Book(file_path="", format=BookFormat.PDF)

    def test_book_format_from_extension(self):
        assert BookFormat.from_extension("book.pdf") == BookFormat.PDF
        assert BookFormat.from_extension("book.docx") == BookFormat.DOCX
        assert BookFormat.from_extension("book.DOC") == BookFormat.DOCX


class TestExtractedContent:
    """Test ExtractedContent model."""

    def test_create_extracted(self):
        content = ExtractedContent(
            book_id="book-1",
            text="Hello world",
        )
        assert content.book_id == "book-1"
        assert content.text == "Hello world"
        assert content.word_count == 0  # not auto-calculated

    def test_empty_text_raises(self):
        import pytest

        with pytest.raises(ValueError):
            ExtractedContent(book_id="book-1", text="   ")


class TestTextChunk:
    """Test TextChunk model."""

    def test_create_chunk(self):
        chunk = TextChunk(
            cleaned_id="clean-1",
            index=0,
            text="Sample chunk text for testing",
        )
        assert chunk.cleaned_id == "clean-1"
        assert chunk.index == 0
        assert chunk.word_count == 0  # not auto-calculated


class TestHermesSkill:
    """Test HermesSkill model."""

    def test_create_skill(self):
        skill = HermesSkill(
            name="test-skill",
            description="A test skill",
        )
        assert skill.name == "test-skill"
        assert skill.status == SkillStatus.DRAFT
        assert skill.version == "1.0.0"
        assert skill.created_at is not None

    def test_skill_to_markdown(self):
        skill = HermesSkill(
            name="audience-research",
            description="Research your target audience effectively",
            version="1.0.0",
            best_practices=["Research demographics", "Use surveys"],
            pitfalls=["No data assumptions"],
            examples=[{"title": "Persona", "code": "Name: John"}],
            workflow=[
                {"title": "Define", "description": "Define audience"},
                {"title": "Research", "description": "Conduct research"},
            ],
            tags=["marketing"],
            category="marketing",
        )

        md = skill.to_skill_markdown()
        assert "audience-research" in md
        assert "Best Practices" in md
        assert "Pitfalls" in md
        assert "Examples" in md
        assert "Workflow" in md
        assert "Research your target audience" in md
        assert "No data assumptions" in md

    def test_empty_skill_markdown(self):
        skill = HermesSkill(name="empty", description="An empty skill")
        md = skill.to_skill_markdown()
        assert "---" in md
        assert "name: empty" in md

    def test_skill_with_related_skills(self):
        skill = HermesSkill(
            name="test",
            description="test",
            related_skills=["skill-a", "skill-b"],
        )
        md = skill.to_skill_markdown()
        assert "skill-a" in md
        assert "skill-b" in md


class TestPipelineContext:
    """Test PipelineContext model."""

    def test_create_context(self):
        ctx = PipelineContext()
        assert ctx.run_id is not None
        assert ctx.current_stage == PipelineStage.EXTRACT
        assert ctx.errors == []
        assert ctx.knowledge_units == []
        assert ctx.skills == []
        assert ctx.chunks == []
        assert ctx.started_at is not None
        assert ctx.completed_at is None

    def test_add_error(self):
        ctx = PipelineContext()
        ctx.add_error("extract", "File not found")
        assert len(ctx.errors) == 1
        assert ctx.errors[0]["stage"] == "extract"
        assert "timestamp" in ctx.errors[0]

    def test_mark_completed(self):
        ctx = PipelineContext()
        ctx.mark_completed()
        assert ctx.completed_at is not None
        assert isinstance(ctx.total_duration_s, float)

    def test_multiple_errors(self):
        ctx = PipelineContext()
        ctx.add_error("stage1", "error 1")
        ctx.add_error("stage2", "error 2")
        assert len(ctx.errors) == 2


class TestProcessingResult:
    """Test ProcessingResult model."""

    def test_success_result(self):
        result = ProcessingResult(
            stage=PipelineStage.EXTRACT,
            success=True,
            context_id="ctx-1",
            output={"text_length": 100},
            duration_s=1.5,
        )
        assert result.stage == PipelineStage.EXTRACT
        assert result.success is True
        assert result.duration_s == 1.5
        assert result.error is None

    def test_failure_result(self):
        result = ProcessingResult(
            stage=PipelineStage.KNOWLEDGE,
            success=False,
            context_id="ctx-1",
            error="LLM timeout",
        )
        assert result.success is False
        assert result.error == "LLM timeout"


class TestKnowledgeUnit:
    """Test KnowledgeUnit model."""

    def test_create_knowledge_unit(self):
        ku = KnowledgeUnit(
            chunk_id="chunk-1",
            unit_type="best_practice",
            title="Test Practice",
            content="This is a best practice.",
        )
        assert ku.unit_type == "best_practice"
        assert ku.confidence == 0.0
        assert ku.tags == []

    def test_high_confidence(self):
        ku = KnowledgeUnit(
            chunk_id="chunk-1",
            unit_type="skill",
            title="Test",
            content="Content",
            confidence=0.95,
        )
        assert ku.confidence == 0.95


class TestEnums:
    """Test enum values."""

    def test_pipeline_stage_values(self):
        assert PipelineStage.EXTRACT.value == "extract"
        assert PipelineStage.VECTOR_DB.value == "vector_db"
        assert len(list(PipelineStage)) == 10

    def test_pipeline_stage_descriptions(self):
        for stage in PipelineStage:
            assert stage.description
            assert len(stage.description) > 5

    def test_llm_provider_requires_key(self):
        assert LLMProvider.OPENAI.requires_api_key is True
        assert LLMProvider.ANTHROPIC.requires_api_key is True
        assert LLMProvider.DEEPSEEK.requires_api_key is True
        assert LLMProvider.GEMINI.requires_api_key is True
        assert LLMProvider.OLLAMA.requires_api_key is False
        assert LLMProvider.OPENROUTER.requires_api_key is True

    def test_book_format_from_ext(self):
        assert BookFormat.from_extension("test.PDF") == BookFormat.PDF
        assert BookFormat.from_extension("test.Docx") == BookFormat.DOCX

    def test_skill_status_cycle(self):
        assert SkillStatus("draft") == SkillStatus.DRAFT
        assert SkillStatus("published") == SkillStatus.PUBLISHED
