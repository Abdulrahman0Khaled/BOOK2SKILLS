"""Metrics collection for pipeline observability.

Provides a ``MetricsCollector`` that tracks stage durations, token usage,
and error counts across pipeline runs. Collectors emit structured reports
suitable for logging, dashboards, or performance analysis.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StageMetric:
    """Timing and outcome data for a single pipeline stage execution.

    Attributes:
        stage_name: Name of the pipeline stage (e.g. ``"extract"``).
        duration_s: Wall-clock duration in seconds.
        success: Whether the stage completed without error.
        tokens_in: Input/prompt tokens consumed (0 if not applicable).
        tokens_out: Output/completion tokens produced (0 if not applicable).
        error_count: Number of errors encountered during the stage.
        item_count: Number of items processed (documents, chunks, skills).
        started_at: Unix timestamp when the stage started.
    """

    stage_name: str
    duration_s: float = 0.0
    success: bool = True
    tokens_in: int = 0
    tokens_out: int = 0
    error_count: int = 0
    item_count: int = 0
    started_at: float = field(default_factory=time.time)


@dataclass
class PipelineReport:
    """Aggregate report for a complete pipeline run.

    Attributes:
        run_id: Unique identifier for the pipeline run.
        total_duration_s: Total elapsed wall-clock time.
        stages: Per-stage metrics in execution order.
        total_tokens_in: Sum of all input tokens across stages.
        total_tokens_out: Sum of all output tokens across stages.
        total_errors: Sum of all errors across stages.
        total_items: Sum of all items processed across stages.
        success: ``True`` if all stages completed without error.
        timestamp: When the report was generated.
        extra: Arbitrary extra context (books, config, etc.).
    """

    run_id: str
    total_duration_s: float = 0.0
    stages: list[StageMetric] = field(default_factory=list)
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_errors: int = 0
    total_items: int = 0
    success: bool = True
    timestamp: float = field(default_factory=time.time)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert the report to a JSON-serialisable dictionary."""
        return {
            "run_id": self.run_id,
            "total_duration_s": round(self.total_duration_s, 3),
            "stages": [
                {
                    "stage_name": s.stage_name,
                    "duration_s": round(s.duration_s, 3),
                    "success": s.success,
                    "tokens_in": s.tokens_in,
                    "tokens_out": s.tokens_out,
                    "error_count": s.error_count,
                    "item_count": s.item_count,
                }
                for s in self.stages
            ],
            "total_tokens_in": self.total_tokens_in,
            "total_tokens_out": self.total_tokens_out,
            "total_errors": self.total_errors,
            "total_items": self.total_items,
            "success": self.success,
            "timestamp": self.timestamp,
            "extra": self.extra,
        }


class MetricsCollector:
    """Collects and reports pipeline metrics.

    Thread-safe collector that aggregates duration, token, and error
    metrics across multiple stages. Designed to be used as a singleton
    per pipeline run, reset between runs.

    Usage::

        metrics = MetricsCollector(run_id="run_001")

        # Record a stage's metrics
        metrics.record_stage(
            stage_name="extract",
            duration_s=12.5,
            tokens_in=1500,
            tokens_out=0,
            item_count=3,
        )

        # Track an error
        metrics.track_error(stage_name="chunk")

        # Get full report
        report = await metrics.get_report()
        print(report.total_duration_s)

        # Reset for next run
        await metrics.reset()
    """

    def __init__(
        self,
        run_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self._run_id: str = run_id or ""
        self._lock = threading.RLock()
        self._stages: list[StageMetric] = []
        self._extra: dict[str, Any] = extra or {}
        self._started_at: float = time.time()
        self._previous_duration: float = 0.0  # total of prior runs

    # ------------------------------------------------------------------
    # Recording methods
    # ------------------------------------------------------------------

    def record_stage(
        self,
        stage_name: str,
        duration_s: float,
        success: bool = True,
        tokens_in: int = 0,
        tokens_out: int = 0,
        error_count: int = 0,
        item_count: int = 0,
    ) -> None:
        """Record metrics for a completed pipeline stage.

        Args:
            stage_name: Name of the stage (e.g. ``"extract"``).
            duration_s: Wall-clock duration in seconds.
            success: Whether the stage completed without error.
            tokens_in: Input/prompt tokens consumed.
            tokens_out: Output/completion tokens produced.
            error_count: Number of errors encountered.
            item_count: Number of items processed.
        """
        metric = StageMetric(
            stage_name=stage_name,
            duration_s=duration_s,
            success=success,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            error_count=error_count,
            item_count=item_count,
        )
        with self._lock:
            self._stages.append(metric)

    def track_error(self, stage_name: str) -> None:
        """Increment the error count for the most recent stage.

        If no stage with the given name exists in the current run,
        a new entry is appended.

        Args:
            stage_name: The stage where the error occurred.
        """
        with self._lock:
            for stage in reversed(self._stages):
                if stage.stage_name == stage_name:
                    stage.error_count += 1
                    return
            # No matching stage — create a minimal entry
            self._stages.append(
                StageMetric(
                    stage_name=stage_name,
                    duration_s=0.0,
                    success=False,
                    error_count=1,
                )
            )

    def record_tokens(
        self,
        stage_name: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> None:
        """Add token counts to a stage.

        Args:
            stage_name: The stage to attribute tokens to.
            tokens_in: Additional input tokens to add.
            tokens_out: Additional output tokens to add.
        """
        with self._lock:
            for stage in reversed(self._stages):
                if stage.stage_name == stage_name:
                    stage.tokens_in += tokens_in
                    stage.tokens_out += tokens_out
                    return

    def record_items(self, stage_name: str, count: int = 1) -> None:
        """Add item count to a stage.

        Args:
            stage_name: The stage to attribute items to.
            count: Number of items to add.
        """
        with self._lock:
            for stage in reversed(self._stages):
                if stage.stage_name == stage_name:
                    stage.item_count += count
                    return

    # ------------------------------------------------------------------
    # Timing context manager
    # ------------------------------------------------------------------

    def timed_stage(self, stage_name: str) -> StageTimer:
        """Return a context manager that times a stage and records metrics.

        Usage::

            with metrics.timed_stage("extract") as stage:
                result = await extractor.extract(book)
                stage.tokens_in = 500
                stage.tokens_out = 1200
                stage.item_count = len(result.pages)
        """
        return StageTimer(self, stage_name)

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    async def get_report(
        self,
        extra: dict[str, Any] | None = None,
    ) -> PipelineReport:
        """Generate an aggregate report of all recorded metrics.

        Args:
            extra: Additional context to include in the report
                (e.g. ``{"book_count": 5}``).

        Returns:
            A ``PipelineReport`` instance with aggregated metrics.
        """
        with self._lock:
            total_duration = time.time() - self._started_at
            total_tokens_in = sum(s.tokens_in for s in self._stages)
            total_tokens_out = sum(s.tokens_out for s in self._stages)
            total_errors = sum(s.error_count for s in self._stages)
            total_items = sum(s.item_count for s in self._stages)
            all_success = all(s.success for s in self._stages)

            return PipelineReport(
                run_id=self._run_id,
                total_duration_s=total_duration + self._previous_duration,
                stages=list(self._stages),
                total_tokens_in=total_tokens_in,
                total_tokens_out=total_tokens_out,
                total_errors=total_errors,
                total_items=total_items,
                success=all_success,
                extra={**self._extra, **(extra or {})},
            )

    async def get_summary(self) -> dict[str, Any]:
        """Return a compact summary dict (no per-stage breakdown).

        Useful for quick status checks during a pipeline run.
        """
        with self._lock:
            return {
                "run_id": self._run_id,
                "stages_completed": len(self._stages),
                "total_duration_s": round(
                    time.time() - self._started_at + self._previous_duration, 2
                ),
                "total_tokens": sum(s.tokens_in + s.tokens_out for s in self._stages),
                "total_errors": sum(s.error_count for s in self._stages),
                "total_items": sum(s.item_count for s in self._stages),
                "all_success": all(s.success for s in self._stages),
            }

    async def reset(self) -> None:
        """Reset all metrics for a new pipeline run.

        Preserves the accumulated duration in ``_previous_duration``
        so cumulative reports across runs are still possible.
        """
        with self._lock:
            self._previous_duration += time.time() - self._started_at
            self._stages.clear()
            self._started_at = time.time()

    async def hard_reset(self) -> None:
        """Reset everything including cumulative duration."""
        with self._lock:
            self._stages.clear()
            self._started_at = time.time()
            self._previous_duration = 0.0

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def run_id(self) -> str:
        """Return the run ID associated with this collector."""
        return self._run_id

    @run_id.setter
    def run_id(self, value: str) -> None:
        """Set the run ID (thread-safe)."""
        with self._lock:
            self._run_id = value

    async def stage_count(self) -> int:
        """Return the number of stages recorded so far."""
        with self._lock:
            return len(self._stages)

    def __repr__(self) -> str:
        with self._lock:
            return f"MetricsCollector(run_id={self._run_id!r}, stages={len(self._stages)})"


class StageTimer:
    """Context manager for timing a single pipeline stage.

    Used internally by ``MetricsCollector.timed_stage``.  Populate
    ``tokens_in``, ``tokens_out``, ``item_count``, and ``success``
    inside the ``with`` block; the duration is computed automatically
    on exit.
    """

    def __init__(self, collector: MetricsCollector, stage_name: str) -> None:
        self._collector = collector
        self._stage_name = stage_name
        self._start: float = 0.0

        # Public fields the user sets inside the ``with`` block
        self.tokens_in: int = 0
        self.tokens_out: int = 0
        self.item_count: int = 0
        self.success: bool = True

    def __enter__(self) -> StageTimer:
        self._start = time.time()
        return self

    def __exit__(self, *args: Any) -> None:
        duration = time.time() - self._start
        self._collector.record_stage(
            stage_name=self._stage_name,
            duration_s=duration,
            success=self.success,
            tokens_in=self.tokens_in,
            tokens_out=self.tokens_out,
            item_count=self.item_count,
        )
