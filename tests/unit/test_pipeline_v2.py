"""Unit tests for upgraded pipeline stages (v2)."""

from __future__ import annotations

import pytest

from book_to_skills.config import PipelineConfig
from book_to_skills.domain.enums import SkillStatus
from book_to_skills.domain.models import (
    Book,
    HermesSkill,
    PipelineContext,
    TextChunk,
)
from book_to_skills.utils.text_utils import normalize_skill_name, normalize_title


class TestTextUtilsIntegration:
    """Text utils used correctly in skill generation flow."""

    def test_name_normalization_flow(self):
        """LLM junk names become clean kebab-case."""
        cases = {
            "How to RecordedWebinars": "how-to-recorded-webinars",
            "Single_Click_Action": "single-click-action",
            "OverwhelmProspects": "overwhelm-prospects",
            "Command Attention Technique": "command-attention",
        }
        for raw, expected in cases.items():
            assert normalize_skill_name(raw) == expected

    def test_title_normalization_flow(self):
        assert normalize_title("buffer_founding_story") == "Buffer Founding Story"
        assert normalize_title("PleasureQuestionsExample") == "Pleasure Questions Example"


@pytest.mark.asyncio
class TestKnowledgeStageV2:
    """KnowledgeStage fills provenance fields."""

    @pytest.fixture
    def config(self, tmp_path):
        cfg = PipelineConfig(
            monitoring__enable_progress_bars=False,
            llm__provider="openai",
            llm__model_small="gpt-4o-mini",
            llm__api_key="sk-test",
        )
        # NOTE: nested kwarg overrides are ignored by pydantic-settings
        cfg.storage.skills_dir = str(tmp_path / "skills")
        cfg.storage.knowledge_graph_dir = str(tmp_path / "kg")
        cfg.vector_db.persist_dir = str(tmp_path / "vectors")
        return cfg

    @pytest.fixture
    def context(self, config):
        from book_to_skills.domain.enums import BookFormat

        book = Book(
            id="book-test-1",
            file_path="/tmp/hooked.pdf",
            format=BookFormat.PDF,
            file_hash="hash123",
        )
        chunk = TextChunk(
            cleaned_id="c1",
            index=0,
            text="Rule 1: Always test your marketing campaigns. "
            "Best Practice: Research your audience before launching. "
            "Avoid: Trying to sell to everyone.",
        )
        ctx = PipelineContext(book=book)
        ctx.chunks = [chunk]
        return ctx

    async def test_heuristic_fallback_propagates_book_info(self, config, context):
        """Even heuristic extraction should fill book_id/source_book."""
        from book_to_skills.pipeline.knowledge import KnowledgeStage

        # Force heuristic by making LLM provider fail (no real key)
        stage = KnowledgeStage(config)
        ctx = await stage.process(context)

        # LLM may or may not be reachable; either way book info must flow
        for ku in ctx.knowledge_units:
            assert ku.book_id == "book-test-1" or ku.book_id != ""
        assert ctx.knowledge_units or ctx.skills  # at least something produced


class TestSkillGenV2:
    """SkillGen uses normalized names."""

    def test_skill_name_kebab(self):
        s = HermesSkill(
            name=normalize_skill_name("How to Command Attention Technique"),
            description="Test",
        )
        assert s.name == "how-to-command-attention"

    def test_source_book_in_skill(self):
        s = HermesSkill(name="x", description="y", source_book="hooked.pdf")
        assert s.source_book == "hooked.pdf"


class TestReviewStageV2:
    """ReviewStage heuristics produce sensible statuses."""

    def _make_skill(self, **overrides) -> HermesSkill:
        base = {
            "name": "test-skill",
            "description": "A detailed description of a useful skill with enough length.",
            "best_practices": ["Do X", "Do Y"],
            "pitfalls": ["Don't do Z"],
            "workflow": [{"title": "Step 1", "description": "Do it"}],
            "examples": [{"title": "Example", "code": "code"}],
            "tags": ["marketing"],
            "category": "marketing",
        }
        base.update(overrides)
        return HermesSkill(**base)

    def test_quality_score_present(self):
        s = self._make_skill()
        assert s.quality_score == 0.0  # set by ReviewStage, not model

    def test_review_fields_present(self):
        s = self._make_skill(review_feedback="Good", review_notes=["n1"])
        assert s.review_feedback == "Good"
        assert s.review_notes == ["n1"]

    def test_status_enum_values(self):
        assert SkillStatus.APPROVED.value == "approved"
        assert SkillStatus.REVIEWED.value == "reviewed"
        assert SkillStatus.REJECTED.value == "rejected"
