"""Abstract base class for all pipeline stages."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..config import PipelineConfig
from ..domain.enums import PipelineStage
from ..domain.models import PipelineContext, ProcessingResult


class BaseStage(ABC):
    """Abstract pipeline stage with caching, retry, and monitoring support."""

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        class_name = self.__class__.__name__.lower()
        # Remove common suffixes to resolve valid stage name
        for suffix in ("stage",):
            if class_name.endswith(suffix):
                class_name = class_name[: -len(suffix)]
        try:
            self.stage = PipelineStage(class_name)
        except ValueError:
            self.stage = PipelineStage.EXTRACT  # fallback
        self._metrics: dict[str, float] = {}

    @abstractmethod
    async def process(self, context: PipelineContext) -> PipelineContext:
        """Execute this pipeline stage."""
        ...

    async def execute(self, context: PipelineContext) -> ProcessingResult:
        """Execute the stage with error handling, timing, and metrics."""
        import time

        start = time.monotonic()
        context.current_stage = self.stage

        try:
            await self.process(context)
            duration = time.monotonic() - start
            return ProcessingResult(
                stage=self.stage,
                success=True,
                context_id=context.run_id,
                output={"context_updated": True},
                duration_s=duration,
                metrics=self._metrics,
            )
        except Exception as e:
            duration = time.monotonic() - start
            context.add_error(self.stage.value, str(e))

            return ProcessingResult(
                stage=self.stage,
                success=False,
                context_id=context.run_id,
                duration_s=duration,
                error=str(e),
                metrics=self._metrics,
            )

    def get_cache_key(self, context: PipelineContext) -> str | None:
        """Generate a cache key for this stage's input context."""
        if context.book and context.book.file_hash:
            return f"{self.stage.value}:{context.book.file_hash}"
        return None

    def record_metric(self, name: str, value: float) -> None:
        self._metrics[name] = value
