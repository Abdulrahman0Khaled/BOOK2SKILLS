"""Unit tests for updated domain models (v2 fields)."""

from __future__ import annotations

from book_to_skills.domain.enums import SkillStatus
from book_to_skills.domain.models import HermesSkill, KnowledgeUnit, TextChunk


class TestHermesSkillV2:
    """Test the new v2 fields on HermesSkill."""

    def test_source_book_default(self):
        s = HermesSkill(name="test", description="test")
        assert s.source_book == ""
        assert s.source_chapters == []

    def test_source_book_set(self):
        s = HermesSkill(name="test", description="test", source_book="hooked.pdf")
        assert s.source_book == "hooked.pdf"

    def test_embedding_default_none(self):
        s = HermesSkill(name="test", description="test")
        assert s.embedding is None

    def test_embedding_set(self):
        s = HermesSkill(name="test", description="test", embedding=[0.1, 0.2, 0.3])
        assert s.embedding == [0.1, 0.2, 0.3]

    def test_review_feedback_default(self):
        s = HermesSkill(name="test", description="test")
        assert s.review_feedback == ""
        assert s.review_notes == []

    def test_review_feedback_set(self):
        s = HermesSkill(
            name="test",
            description="test",
            review_feedback="Great clarity, missing workflow",
            review_notes=["Add workflow section", "Tags are good"],
            quality_score=8.5,
        )
        assert s.review_feedback == "Great clarity, missing workflow"
        assert len(s.review_notes) == 2
        assert s.quality_score == 8.5

    def test_quality_score_range(self):
        s = HermesSkill(name="test", description="test", quality_score=9.7)
        assert s.quality_score == 9.7

    def test_status_approved(self):
        s = HermesSkill(name="test", description="test", status=SkillStatus.APPROVED)
        assert s.status == SkillStatus.APPROVED

    def test_markdown_still_works_with_v2_fields(self):
        s = HermesSkill(
            name="test-skill",
            description="A test skill",
            source_book="book.pdf",
            best_practices=["Do X"],
            workflow=[{"title": "Step", "description": "Do it"}],
        )
        md = s.to_skill_markdown()
        assert "test-skill" in md
        assert "Do X" in md


class TestKnowledgeUnitV2:
    """Test the new v2 fields on KnowledgeUnit."""

    def test_book_fields_default(self):
        ku = KnowledgeUnit(
            chunk_id="c1",
            unit_type="best_practice",
            title="T",
            content="C",
        )
        assert ku.book_id == ""
        assert ku.source_book == ""

    def test_book_fields_set(self):
        ku = KnowledgeUnit(
            chunk_id="c1",
            book_id="abc123",
            source_book="dot_com_secrets.pdf",
            unit_type="skill",
            title="T",
            content="C",
            tags=["marketing", "sales"],
        )
        assert ku.book_id == "abc123"
        assert ku.source_book == "dot_com_secrets.pdf"
        assert ku.tags == ["marketing", "sales"]


class TestTextChunkV2:
    """Test embedding field on TextChunk."""

    def test_embedding_default(self):
        c = TextChunk(cleaned_id="cl", index=0, text="hello")
        assert c.embedding is None

    def test_embedding_set(self):
        c = TextChunk(cleaned_id="cl", index=0, text="hello", embedding=[1.0, 2.0])
        assert c.embedding == [1.0, 2.0]
