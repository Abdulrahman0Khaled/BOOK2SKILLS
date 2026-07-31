"""Structured logging and progress display for the pipeline.

Provides a ``StructuredLogger`` built on ``structlog`` that produces
structured JSON log entries with trace_id correlation, plus a progress
bar helper using ``rich`` and ``tqdm`` for CLI feedback during long-
running pipeline stages.
"""

from __future__ import annotations

import logging
import sys
import time
import uuid
from typing import Any

from book_to_skills.config import MonitoringConfig, PipelineConfig

# ------------------------------------------------------------------
# Optional dependency guards
# ------------------------------------------------------------------

_has_structlog: bool = False
_has_rich: bool = False
_has_tqdm: bool = False

try:
    import structlog

    _has_structlog = True
except ImportError:  # pragma: no cover
    structlog = None  # type: ignore[assignment]

try:
    from rich.console import Console

    _has_rich = True
except ImportError:  # pragma: no cover
    Console = None  # type: ignore[assignment]

try:
    import tqdm as _tqdm

    _has_tqdm = True
except ImportError:  # pragma: no cover
    _tqdm = None  # type: ignore[assignment]


# ------------------------------------------------------------------
# Structured logger
# ------------------------------------------------------------------


class StructuredLogger:
    """Async-compatible structured logger with trace_id correlation.

    Wraps ``structlog`` to produce JSON log lines enriched with:
    - ``trace_id``: a UUID passed at construction or auto-generated,
      used to correlate all log messages from a single pipeline run.
    - ``timestamp``, ``level``, ``logger``, ``message``, and optional
      ``extra`` key-value pairs.

    Falls back to standard library ``logging`` when ``structlog`` is
    not installed.

    Usage::

        log = StructuredLogger(trace_id="abc123")
        log.info("Pipeline started", book_count=5)
        log.error("Extraction failed", exc=repr(err))
        log.warning("Low quality score", score=0.2)
        log.debug("Chunk details", chunk_id="chk_01")
    """

    def __init__(
        self,
        name: str = "book_to_skills",
        config: MonitoringConfig | PipelineConfig | None = None,
        trace_id: str | None = None,
    ) -> None:
        self._name = name
        # Normalise: accept either MonitoringConfig or PipelineConfig
        raw_config = config or MonitoringConfig()
        if isinstance(raw_config, PipelineConfig):
            resolved_config: MonitoringConfig = raw_config.monitoring
        else:
            resolved_config = raw_config
        self._config = resolved_config
        self._trace_id: str = trace_id or uuid.uuid4().hex[:12]
        self._bound_context: dict[str, Any] = {}

        # Initialise the underlying logger
        log_level = getattr(logging, self._config.log_level.upper(), logging.INFO)
        self._logger = self._build_logger(name, log_level)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def trace_id(self) -> str:
        """Return the current trace_id for this logger instance."""
        return self._trace_id

    def with_trace_id(self, trace_id: str) -> StructuredLogger:
        """Return a new logger bound to a different trace_id.

        Useful for spawning sub-loggers for parallel pipeline branches.
        """
        return StructuredLogger(
            name=self._name,
            config=self._config,
            trace_id=trace_id,
        )

    # ------------------------------------------------------------------
    # Log methods (sync — intentionally not async to keep hot-path fast)
    # ------------------------------------------------------------------

    def info(self, message: str, **extra: Any) -> None:
        """Log at INFO level.

        Args:
            message: Human-readable log message.
            **extra: Additional structured key-value pairs.
        """
        self._log(logging.INFO, message, **extra)

    def error(self, message: str, **extra: Any) -> None:
        """Log at ERROR level.

        Args:
            message: Human-readable log message.
            **extra: Additional structured key-value pairs.
        """
        self._log(logging.ERROR, message, **extra)

    def warning(self, message: str, **extra: Any) -> None:
        """Log at WARNING level.

        Args:
            message: Human-readable log message.
            **extra: Additional structured key-value pairs.
        """
        self._log(logging.WARNING, message, **extra)

    def debug(self, message: str, **extra: Any) -> None:
        """Log at DEBUG level.

        Args:
            message: Human-readable log message.
            **extra: Additional structured key-value pairs.
        """
        self._log(logging.DEBUG, message, **extra)

    def critical(self, message: str, **extra: Any) -> None:
        """Log at CRITICAL level.

        Args:
            message: Human-readable log message.
            **extra: Additional structured key-value pairs.
        """
        self._log(logging.CRITICAL, message, **extra)

    # ------------------------------------------------------------------
    # Bound log methods for chaining
    # ------------------------------------------------------------------

    def bind(self, **kwargs: Any) -> StructuredLogger:
        """Return a new logger with additional bound context fields.

        This returns a *new* logger instance with the extra context
        appended to every log call.  Original logger is unchanged.
        """
        new_logger = StructuredLogger(
            name=self._name,
            config=self._config,
            trace_id=self._trace_id,
        )
        new_logger._bound_context = {
            **self._bound_context,
            **kwargs,
        }
        return new_logger

    # ------------------------------------------------------------------
    # Internal implementation
    # ------------------------------------------------------------------

    def _log(self, level: int, message: str, **extra: Any) -> None:
        """Emit a log record with structured context."""
        bound = getattr(self, "_bound_context", {})
        event = {
            "timestamp": time.time(),
            "level": logging.getLevelName(level).lower(),
            "logger": self._name,
            "trace_id": self._trace_id,
            "message": message,
            **bound,
            **extra,
        }
        self._logger.log(level, message, extra=event)

    @staticmethod
    def _build_logger(name: str, level: int) -> logging.Logger | Any:
        """Build the underlying logger (structlog or stdlib)."""
        if _has_structlog and structlog is not None:
            return _build_structlog_logger(name, level)
        return _build_stdlib_logger(name, level)

    def __repr__(self) -> str:
        return f"StructuredLogger(name={self._name!r}, trace_id={self._trace_id!r})"


# ------------------------------------------------------------------
# Logger factory helpers
# ------------------------------------------------------------------


def _build_structlog_logger(name: str, level: int) -> Any:
    """Configure and return a structlog logger."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if _has_rich else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logger: logging.Logger = structlog.get_logger(name)
    logger.setLevel(level)
    return logger


def _build_stdlib_logger(name: str, level: int) -> logging.Logger:
    """Configure and return a stdlib logger as fallback."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter("[%(levelname)s] %(name)s: %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


# ------------------------------------------------------------------
# Progress bar
# ------------------------------------------------------------------


class ProgressBar:
    """Context-manager progress bar wrapper around ``tqdm`` / ``rich.progress``.

    Provides a consistent interface regardless of which display backend
    is active.  Falls back to a no-op progress bar when neither ``tqdm``
    nor ``rich`` is installed.

    Usage::

        with ProgressBar(total=100, desc="Processing books") as bar:
            for _ in range(100):
                do_work()
                bar.update(1)

        # Manual usage without context manager
        bar = ProgressBar(total=50, desc="Extracting")
        bar.start()
        ...
        bar.update(5)
        ...
        bar.finish()
    """

    def __init__(
        self,
        total: int = 0,
        desc: str = "",
        unit: str = "it",
        leave: bool = True,
        config: MonitoringConfig | None = None,
    ) -> None:
        self._total = total
        self._desc = desc
        self._unit = unit
        self._leave = leave
        self._config = config or MonitoringConfig()

        self._bar: Any = None
        self._tqdm_instance: Any = None
        self._progress: Any = None
        self._task_id: Any = None
        self._n: int = 0

    def start(self) -> None:
        """Initialise and display the progress bar."""
        if not self._config.enable_progress_bars:
            return

        if _has_tqdm and _tqdm is not None:
            self._tqdm_instance = _tqdm.tqdm(
                total=self._total,
                desc=self._desc,
                unit=self._unit,
                leave=self._leave,
                file=sys.stdout,
            )
        elif _has_rich and Console is not None:
            from rich.progress import (
                BarColumn,
                Progress,
                TextColumn,
                TimeElapsedColumn,
                TimeRemainingColumn,
            )

            self._progress = Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
            )
            self._progress.start()
            self._task_id = self._progress.add_task(self._desc, total=self._total)
        else:
            # No display library — track internally
            pass

    def update(self, n: int = 1) -> None:
        """Advance the progress bar by *n* steps."""
        if not self._config.enable_progress_bars:
            return

        self._n += n

        if self._tqdm_instance is not None:
            self._tqdm_instance.update(n)
        elif self._progress is not None and self._task_id is not None:
            self._progress.update(self._task_id, advance=n)

    def set_description(self, desc: str) -> None:
        """Update the description text."""
        if self._tqdm_instance is not None:
            self._tqdm_instance.set_description(desc)
        elif self._progress is not None and self._task_id is not None:
            self._progress.update(self._task_id, description=desc)

    def finish(self) -> None:
        """Close the progress bar and clean up."""
        if self._tqdm_instance is not None:
            self._tqdm_instance.close()
        elif self._progress is not None:
            self._progress.stop()
        self._bar = None

    @property
    def n(self) -> int:
        """Current progress value."""
        return self._n

    # Context manager support
    def __enter__(self) -> ProgressBar:
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.finish()

    def __repr__(self) -> str:
        return f"ProgressBar(desc={self._desc!r}, {self._n}/{self._total})"


# ------------------------------------------------------------------
# Convenience factory
# ------------------------------------------------------------------


def get_logger(
    name: str = "book_to_skills",
    config: MonitoringConfig | None = None,
    trace_id: str | None = None,
) -> StructuredLogger:
    """Quick factory for a ``StructuredLogger``.

    Usage::

        from book_to_skills.monitoring.logger import get_logger

        log = get_logger(trace_id="abc123")
        log.info("Ready")
    """
    return StructuredLogger(name=name, config=config, trace_id=trace_id)


def progress_bar(
    total: int = 0,
    desc: str = "",
    unit: str = "it",
    leave: bool = True,
    config: MonitoringConfig | None = None,
) -> ProgressBar:
    """Quick factory for a ``ProgressBar``.

    Usage::

        from book_to_skills.monitoring.logger import progress_bar

        with progress_bar(total=100, desc="Processing") as bar:
            ...
    """
    return ProgressBar(
        total=total,
        desc=desc,
        unit=unit,
        leave=leave,
        config=config,
    )
