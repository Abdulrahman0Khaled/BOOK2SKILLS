"""Task queue with priority support and concurrency control.

Provides an async TaskQueue backed by an in-memory heap (default) or an
optional Redis backend. Tasks are dequeued in priority order, and a
configurable max-concurrency limit prevents overloading downstream
resources. Status tracking lets callers observe task lifecycle.
"""

from __future__ import annotations

import asyncio
import enum
import heapq
import threading
import time
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

from book_to_skills.config import PipelineConfig, QueueConfig
from book_to_skills.domain.enums import QueuePriority


class TaskStatus(str, enum.Enum):
    """Lifecycle status of a queued task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


@dataclass(order=False)
class Task:
    """A unit of work managed by the task queue.

    Attributes:
        id: Unique task identifier (auto-generated UUID hex).
        name: Human-readable task name.
        priority: Lower values = higher priority (same as QueuePriority).
        status: Current task lifecycle status.
        created_at: Timestamp when the task was enqueued.
        started_at: Timestamp when execution began (None until run).
        completed_at: Timestamp when execution finished.
        result: The return value of the task coroutine.
        error: Exception message if the task failed.
        timeout_s: Max wall-clock seconds for execution (None = no limit).
        metadata: Arbitrary user-defined key-value pairs.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    name: str = ""
    priority: int = QueuePriority.MEDIUM.value
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    result: Any = None
    error: str | None = None
    timeout_s: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    # Not included in field comparison — used during execution
    _coro: Callable[[], Coroutine] | None = field(default=None, repr=False, compare=False)

    @property
    def duration_s(self) -> float | None:
        """Task execution duration in seconds, or None if not yet completed."""
        if self.started_at is not None and self.completed_at is not None:
            return self.completed_at - self.started_at
        if self.started_at is not None:
            return time.time() - self.started_at
        return None

    @property
    def is_done(self) -> bool:
        """True if the task has reached a terminal state."""
        return self.status in (
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.TIMED_OUT,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize task to a dictionary for storage / observability."""
        return {
            "id": self.id,
            "name": self.name,
            "priority": self.priority,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "timeout_s": self.timeout_s,
            "metadata": self.metadata,
        }


# Heap entries: (priority, timestamp, task) — timestamp breaks ties for FIFO
HeapEntry = tuple[int, float, Task]


class MemoryQueueBackend:
    """Priority-queue backend stored in memory.

    Uses the ``heapq`` module for efficient O(log n) push/pop. Tasks
    with equal priority are ordered by insertion time (FIFO within
    priority level).
    """

    def __init__(self) -> None:
        self._heap: list[HeapEntry] = []
        self._lock = threading.Lock()
        self._counter: float = 0.0  # tie-breaker for same priority items

    def push(self, task: Task) -> None:
        """Push a task onto the priority heap."""
        with self._lock:
            self._counter += 1.0
            entry = (task.priority, self._counter, task)
            heapq.heappush(self._heap, entry)

    def pop(self) -> Task | None:
        """Pop the highest-priority (lowest value) task.

        Returns None if the queue is empty.
        """
        with self._lock:
            while self._heap:
                _, _, task = heapq.heappop(self._heap)
                if task.status == TaskStatus.CANCELLED:
                    continue  # skip cancelled tasks
                return task
            return None

    def peek(self) -> Task | None:
        """Return the highest-priority task without removing it."""
        with self._lock:
            while self._heap:
                _, _, task = self._heap[0]
                if task.status == TaskStatus.CANCELLED:
                    heapq.heappop(self._heap)
                    continue
                return task
            return None

    def remove(self, task_id: str) -> bool:
        """Mark a task as cancelled (removed from queue).

        The task stays in the heap but is skipped during pop/peek.
        Returns True if the task was found.
        """
        with self._lock:
            for _, _, task in self._heap:
                if task.id == task_id and task.status == TaskStatus.PENDING:
                    task.status = TaskStatus.CANCELLED
                    return True
            return False

    def size(self) -> int:
        """Return the number of pending (non-cancelled) tasks."""
        with self._lock:
            return sum(1 for _, _, t in self._heap if t.status == TaskStatus.PENDING)

    def pending_tasks(self) -> list[Task]:
        """Return all pending tasks (for observability)."""
        with self._lock:
            return [t for _, _, t in self._heap if t.status == TaskStatus.PENDING]


class TaskQueue:
    """Async task queue with priority scheduling and concurrency control.

    Features:
    - In-memory priority heap (default) with optional Redis backend
    - Configurable ``max_concurrent`` tasks running simultaneously
    - Priority-based dequeuing (lower number = higher priority)
    - Task status tracking (pending → running → completed/failed)
    - Per-task timeout support
    - Async/await interface designed for pipeline integration

    Usage::

        queue = TaskQueue(config.queue)

        async def process(item: str) -> str:
            return f"processed: {item}"

        await queue.enqueue(process, "file1.pdf", priority=1)
        result = await queue.dequeue()
        await queue.get_status(task_id)
    """

    def __init__(
        self,
        config: QueueConfig | PipelineConfig | None = None,
        max_concurrent: int | None = None,
    ) -> None:
        # Normalise: accept either QueueConfig or PipelineConfig
        raw_config = config or QueueConfig()
        if isinstance(raw_config, PipelineConfig):
            resolved_config: QueueConfig = raw_config.queue
        else:
            resolved_config = raw_config
        self._config = resolved_config
        self._max_concurrent = max_concurrent or self._config.max_concurrent_jobs
        self._semaphore = asyncio.Semaphore(self._max_concurrent)

        # Backend
        backend_name = self._config.backend.lower()
        if backend_name == "redis":
            # Redis backend is optional — require explicit opt-in
            self._backend: Any = self._build_redis_backend()
        else:
            self._backend = MemoryQueueBackend()

        # Task registry: task_id -> Task (for status lookups on completed tasks)
        self._registry: dict[str, Task] = {}
        self._registry_lock = threading.Lock()

        # Worker management
        self._workers: set[asyncio.Task] = set()
        self._running = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def enqueue(
        self,
        coro_fn: Callable[[], Coroutine],
        name: str = "",
        priority: int = QueuePriority.MEDIUM.value,
        timeout_s: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Enqueue a task for asynchronous execution.

        Args:
            coro_fn: An async callable ``() -> T`` that performs the work.
            name: Optional human-readable name for the task.
            priority: Priority level (lower = higher priority).
                Use ``QueuePriority`` enum values (CRITICAL=0 .. BATCH=4).
            timeout_s: Max execution time in seconds. ``None`` = no limit.
            metadata: Optional arbitrary key-value pairs attached to the task.

        Returns:
            The task ID, which can be used for ``get_status`` or ``cancel``.
        """
        task = Task(
            name=name or coro_fn.__name__,
            priority=priority,
            timeout_s=timeout_s,
            metadata=metadata or {},
            _coro=coro_fn,
        )
        self._backend.push(task)
        with self._registry_lock:
            self._registry[task.id] = task
        return task.id

    async def dequeue(self) -> Task | None:
        """Dequeue and return the highest-priority pending task.

        Returns ``None`` if the queue is empty.
        The task is not executed by dequeue itself; it is returned so the
        caller can run it. For automatic execution, use ``start_worker``.
        """
        return self._backend.pop()

    async def get_status(self, task_id: str) -> dict[str, Any] | None:
        """Return the current status dict for a task by ID.

        Returns ``None`` if the task ID is unknown.
        """
        with self._registry_lock:
            task = self._registry.get(task_id)
        if task is None:
            return None
        return task.to_dict()

    async def cancel(self, task_id: str) -> bool:
        """Cancel a pending task by ID.

        Returns ``True`` if the task was found and cancelled; ``False``
        if already running, done, or unknown.
        """
        with self._registry_lock:
            task = self._registry.get(task_id)
        if task is None:
            return False
        if task.status != TaskStatus.PENDING:
            return False
        return self._backend.remove(task_id)

    async def queue_size(self) -> int:
        """Return the number of pending tasks."""
        return self._backend.size()

    async def stats(self) -> dict[str, Any]:
        """Return queue statistics for monitoring."""
        with self._registry_lock:
            total = len(self._registry)
            by_status: dict[str, int] = {}
            for t in self._registry.values():
                by_status[t.status.value] = by_status.get(t.status.value, 0) + 1
        return {
            "pending": await self.queue_size(),
            "total_tracked": total,
            "by_status": by_status,
            "max_concurrent": self._max_concurrent,
            "backend": self._config.backend,
        }

    async def list_pending(self) -> list[dict[str, Any]]:
        """Return all pending tasks as dicts (for UI / observability)."""
        return [t.to_dict() for t in self._backend.pending_tasks()]

    # ------------------------------------------------------------------
    # Worker loop (optional automatic execution)
    # ------------------------------------------------------------------

    async def start_worker(self) -> None:
        """Start the background worker loop.

        Continuously dequeues tasks and runs them up to the concurrency
        limit. Runs until ``stop_worker`` is called. Idles when the queue
        is empty.
        """
        self._running = True
        while self._running:
            task = self._backend.pop()
            if task is None:
                # Queue empty — yield briefly before re-checking
                await asyncio.sleep(0.1)
                continue
            # Acquire semaphore slot
            await self._semaphore.acquire()
            worker = asyncio.create_task(self._execute_task(task))
            worker.add_done_callback(lambda _: self._semaphore.release())
            self._workers.add(worker)
            worker.add_done_callback(self._workers.discard)

    async def stop_worker(self) -> None:
        """Signal the worker loop to stop after finishing current tasks."""
        self._running = False

    async def wait_for_empty(self, poll_interval: float = 0.2) -> None:
        """Block until all queued and running tasks complete.

        Args:
            poll_interval: Seconds between status polls.
        """
        while True:
            if (await self.queue_size()) == 0:
                with self._registry_lock:
                    running = any(t.status == TaskStatus.RUNNING for t in self._registry.values())
                if not running:
                    break
            await asyncio.sleep(poll_interval)

    # ------------------------------------------------------------------
    # Internal execution
    # ------------------------------------------------------------------

    async def _execute_task(self, task: Task) -> None:
        """Run a single task, updating its status throughout the lifecycle."""
        task.status = TaskStatus.RUNNING
        task.started_at = time.time()

        try:
            if task.timeout_s is not None:
                result = await asyncio.wait_for(
                    task._coro(),
                    timeout=task.timeout_s,
                )
            else:
                result = await task._coro()

            task.status = TaskStatus.COMPLETED
            task.result = result
            task.completed_at = time.time()

        except TimeoutError:
            task.status = TaskStatus.TIMED_OUT
            task.error = f"Task timed out after {task.timeout_s}s"
            task.completed_at = time.time()

        except Exception as exc:
            task.status = TaskStatus.FAILED
            task.error = f"{type(exc).__name__}: {exc}"
            task.completed_at = time.time()

    # ------------------------------------------------------------------
    # Redis backend (optional)
    # ------------------------------------------------------------------

    def _build_redis_backend(self) -> MemoryQueueBackend | RedisQueueBackend:
        """Build a Redis-backed queue if redis is available.

        Falls back to memory queue when the redis-py package is not
        installed or the connection fails.
        """
        try:
            import redis.asyncio as aioredis  # ruff: ignore[unused-import]

            return RedisQueueBackend(self._config.redis_url)
        except ImportError:
            import warnings

            warnings.warn("redis-py not installed; falling back to memory queue backend")
            return MemoryQueueBackend()

    def __repr__(self) -> str:
        return f"TaskQueue(backend={self._config.backend}, max_concurrent={self._max_concurrent})"


class RedisQueueBackend:
    """Redis-backed queue backend (optional, requires redis-py).

    Uses a Redis sorted set with priority as the score to maintain
    ordering. Not imported by default; instantiated only when
    ``QueueConfig.backend == "redis"``.
    """

    def __init__(self, redis_url: str) -> None:
        import redis.asyncio as aioredis

        self._client: aioredis.Redis = aioredis.from_url(  # type: ignore[no-untyped-call]
            redis_url, decode_responses=True
        )
        self._queue_key = "book_to_skills:task_queue"

    async def push(self, task: Task) -> None:
        """Push a task as a JSON blob scored by priority."""
        import json

        data = json.dumps(task.to_dict(), default=str)
        await self._client.zadd(self._queue_key, {data: task.priority})

    async def pop(self) -> Task | None:
        """Pop the lowest-score (highest-priority) task."""
        import json

        result = await self._client.zpopmin(self._queue_key, count=1)
        if not result:
            return None
        data_str, _ = result[0]
        data = json.loads(data_str)
        return Task(**data)

    async def size(self) -> int:
        """Return the number of tasks in the Redis sorted set."""
        return await self._client.zcard(self._queue_key)

    async def remove(self, task_id: str) -> bool:
        """Remove a task by ID from the Redis sorted set."""
        import json

        # Scan all entries looking for matching ID
        entries = await self._client.zrange(self._queue_key, 0, -1)
        removed = 0
        for entry_str in entries:
            try:
                data = json.loads(entry_str)
            except json.JSONDecodeError:
                continue
            if data.get("id") == task_id:
                await self._client.zrem(self._queue_key, entry_str)
                removed += 1
        return removed > 0
