"""Unit tests for pipeline stages base class."""

from __future__ import annotations

from book_to_skills.domain.enums import PipelineStage
from book_to_skills.domain.models import PipelineContext, ProcessingResult
from book_to_skills.pipeline.base import BaseStage


class TestBaseStage:
    """Test BaseStage abstract class."""

    def test_stage_name_from_class(self):
        """Test that stage name falls back to EXTRACT for unknown stages."""

        class TestStage(BaseStage):
            async def process(self, context):
                return context

        from book_to_skills.config import PipelineConfig

        stage = TestStage(PipelineConfig())
        assert stage.stage == PipelineStage.EXTRACT  # fallback for unknown stages

    def test_cache_key_generation(self):
        """Test cache key is generated from file hash."""

        class TestStage(BaseStage):
            async def process(self, context):
                return context

        from book_to_skills.config import PipelineConfig
        from book_to_skills.domain.enums import BookFormat
        from book_to_skills.domain.models import Book

        stage = TestStage(PipelineConfig())
        ctx = PipelineContext()
        assert stage.get_cache_key(ctx) is None  # no book yet

        ctx.book = Book(file_path="/tmp/test.pdf", format=BookFormat.PDF, file_hash="abc123")
        key = stage.get_cache_key(ctx)
        assert key is not None
        assert "extract" in key
        assert "abc123" in key

    def test_execute_catches_errors(self):
        """Test that execute wraps errors properly."""

        class FailingStage(BaseStage):
            async def process(self, context):
                msg = "Something went wrong"
                raise RuntimeError(msg)

        import asyncio

        from book_to_skills.config import PipelineConfig

        stage = FailingStage(PipelineConfig())
        ctx = PipelineContext()
        result = asyncio.run(stage.execute(ctx))
        assert isinstance(result, ProcessingResult)
        assert result.success is False
        assert result.error is not None
        assert "Something went wrong" in result.error

    def test_execute_success(self):
        """Test successful execution."""

        class SuccessStage(BaseStage):
            async def process(self, context):
                context.current_stage = self.stage
                return context

        import asyncio

        from book_to_skills.config import PipelineConfig

        stage = SuccessStage(PipelineConfig())
        ctx = PipelineContext()
        result = asyncio.run(stage.execute(ctx))
        assert isinstance(result, ProcessingResult)
        assert result.success is True
        assert result.error is None
        assert result.duration_s >= 0

    def test_metrics_recording(self):
        """Test metric recording."""

        class MetricStage(BaseStage):
            async def process(self, context):
                self.record_metric("words_processed", 1000.0)
                self.record_metric("quality_score", 0.95)
                return context

        import asyncio

        from book_to_skills.config import PipelineConfig

        stage = MetricStage(PipelineConfig())
        ctx = PipelineContext()
        result = asyncio.run(stage.execute(ctx))
        assert result.metrics["words_processed"] == 1000.0
        assert result.metrics["quality_score"] == 0.95
