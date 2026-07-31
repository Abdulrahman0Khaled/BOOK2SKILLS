"""Cache management with disk and memory backends.

Provides a thread-safe async CacheManager that persists cached data to
JSON files on disk, with an in-memory fallback when disk is unavailable.
Keys are SHA-256 hashed for safe filesystem naming and TTL-based expiration
is supported.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Generic, TypeVar

from book_to_skills.config import CacheConfig, PipelineConfig
from book_to_skills.utils.file_utils import ensure_dir, read_json, write_json
from book_to_skills.utils.hash_utils import compute_text_hash

T = TypeVar("T")

# Cache entry structure stored on disk and in memory
CACHE_ENTRY_VERSION = 1


class CacheEntry(Generic[T]):
    """A single cache entry with value, timestamp, and TTL."""

    __slots__ = ("created_at", "expires_at", "value")

    def __init__(self, value: T, ttl: float | None = None) -> None:
        self.value = value
        self.created_at: float = time.time()
        self.expires_at: float | None = self.created_at + ttl if ttl is not None else None

    @property
    def is_expired(self) -> bool:
        """Check if this entry has expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def to_dict(self) -> dict[str, Any]:
        """Serialize entry to a dictionary for JSON storage."""
        return {
            "_version": CACHE_ENTRY_VERSION,
            "value": self.value,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CacheEntry:
        """Deserialize a dictionary back into a CacheEntry."""
        entry = cls.__new__(cls)
        entry.value = data["value"]
        entry.created_at = data.get("created_at", time.time())
        entry.expires_at = data.get("expires_at")
        return entry


class DiskBackend:
    """Persistent cache backend using JSON files on disk.

    Each cache entry is stored as an individual JSON file under the
    configured cache directory. File names are SHA-256 hashes of the
    original key for safe and predictable filesystem paths.
    """

    def __init__(self, cache_dir: str | Path) -> None:
        self._cache_dir: Path = ensure_dir(cache_dir)

    def _key_path(self, key_hash: str) -> Path:
        """Resolve the filesystem path for a given hashed key."""
        # Use prefix directories to avoid too many files in one folder
        prefix = key_hash[:2]
        subdir = self._cache_dir / prefix
        subdir.mkdir(parents=True, exist_ok=True)
        return subdir / f"{key_hash}.json"

    def get(self, key_hash: str) -> Any | None:
        """Retrieve a value by its hashed key.

        Returns None if the key does not exist, the file is corrupt,
        or the entry has expired (expired entries are deleted).
        """
        path = self._key_path(key_hash)
        if not path.exists():
            return None
        try:
            data = read_json(path)
            entry = CacheEntry.from_dict(data)
            if entry.is_expired:
                path.unlink(missing_ok=True)
                return None
            return entry.value
        except (json.JSONDecodeError, KeyError, OSError):
            # Corrupt entry — remove and treat as miss
            path.unlink(missing_ok=True)
            return None

    def set(self, key_hash: str, value: Any, ttl: float | None = None) -> None:
        """Store a value under its hashed key with optional TTL (seconds)."""
        entry = CacheEntry(value, ttl=ttl)
        path = self._key_path(key_hash)
        write_json(path, entry.to_dict())

    def clear(self) -> None:
        """Remove all cached entries from the disk backend."""
        for p in self._cache_dir.rglob("*.json"):
            p.unlink(missing_ok=True)

    def clear_prefix(self, key_hash_prefix: str) -> None:
        """Remove entries whose hashed key starts with a given prefix."""
        prefix_dir = self._cache_dir / key_hash_prefix[:2]
        if not prefix_dir.exists():
            return
        for p in prefix_dir.glob(f"{key_hash_prefix}*.json"):
            p.unlink(missing_ok=True)

    def count(self) -> int:
        """Return the number of cached entries on disk."""
        return sum(1 for _ in self._cache_dir.rglob("*.json"))


class MemoryBackend:
    """In-memory cache backend using a dictionary.

    Entries are stored as CacheEntry objects with TTL-based expiration
    checked on every read. Thread-safe via a standard Lock.
    """

    def __init__(self) -> None:
        self._store: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()

    def get(self, key_hash: str) -> Any | None:
        """Retrieve a value by its hashed key."""
        with self._lock:
            entry = self._store.get(key_hash)
            if entry is None:
                return None
            if entry.is_expired:
                del self._store[key_hash]
                return None
            return entry.value

    def set(self, key_hash: str, value: Any, ttl: float | None = None) -> None:
        """Store a value under its hashed key with optional TTL (seconds)."""
        with self._lock:
            self._store[key_hash] = CacheEntry(value, ttl=ttl)

    def clear(self) -> None:
        """Remove all entries from the memory backend."""
        with self._lock:
            self._store.clear()

    def clear_prefix(self, key_hash_prefix: str) -> None:
        """Remove entries whose hashed key starts with a given prefix."""
        with self._lock:
            self._store = {
                k: v for k, v in self._store.items() if not k.startswith(key_hash_prefix)
            }

    def count(self) -> int:
        """Return the number of entries in memory."""
        with self._lock:
            return len(self._store)


class CacheManager:
    """Thread-safe async cache manager with disk and memory backends.

    Features:
    - Disk backend (JSON files) as primary, memory as fallback
    - SHA-256 hash-based keys for safe filesystem naming
    - TTL-based expiration
    - Thread-safe operations
    - Async-compatible interface (internal I/O is sync but exposed
      with async wrappers for seamless pipeline integration)

    Usage::

        cache = CacheManager(config.cache)
        await cache.set("my_key", {"data": 42}, ttl=3600)
        value = await cache.get("my_key")
        await cache.clear()
    """

    def __init__(
        self,
        config: CacheConfig | PipelineConfig | None = None,
        cache_dir: str | Path | None = None,
    ) -> None:
        # Normalise: accept either CacheConfig or PipelineConfig
        raw_config = config or CacheConfig()
        if isinstance(raw_config, PipelineConfig):
            resolved_config: CacheConfig = raw_config.cache
        else:
            resolved_config = raw_config
        self._config = resolved_config
        self._lock = threading.RLock()

        # Resolve cache directory
        resolved_dir: str | Path
        if cache_dir is not None:
            resolved_dir = cache_dir
        else:
            resolved_dir = self._config.cache_dir

        # Initialise backend
        backend_name = self._config.backend.lower()
        if backend_name == "disk":
            self._backend: DiskBackend | MemoryBackend = DiskBackend(resolved_dir)
        else:
            self._backend = MemoryBackend()

        # Track whether we fell back to memory (for observability)
        self._using_fallback: bool = backend_name != "disk"

    @property
    def backend_type(self) -> str:
        """Return the active backend type name."""
        if isinstance(self._backend, DiskBackend):
            return "disk"
        return "memory"

    # ------------------------------------------------------------------
    # Public API (async wrappers)
    # ------------------------------------------------------------------

    async def get(self, key: str) -> Any | None:
        """Retrieve a cached value by key.

        Args:
            key: The cache key (will be SHA-256 hashed internally).

        Returns:
            The cached value, or None if the key does not exist or
            has expired.
        """
        key_hash = self._hash_key(key)
        with self._lock:
            return self._backend.get(key_hash)

    async def set(
        self,
        key: str,
        value: Any,
        ttl: float | None = None,
    ) -> None:
        """Store a value in the cache.

        Args:
            key: The cache key (will be SHA-256 hashed internally).
            value: The value to store (must be JSON-serializable).
            ttl: Time-to-live in seconds. Uses config default when None.
        """
        if ttl is None:
            ttl = self._config.ttl_hours * 3600
        key_hash = self._hash_key(key)
        with self._lock:
            self._backend.set(key_hash, value, ttl=ttl)

    async def clear(self) -> None:
        """Remove all entries from the cache."""
        with self._lock:
            self._backend.clear()

    async def get_or_compute(
        self,
        key: str,
        compute_fn,
        ttl: float | None = None,
    ) -> Any:
        """Return cached value if it exists, otherwise compute and cache.

        Args:
            key: The cache key.
            compute_fn: An async callable ``() -> T`` that produces the
                value on a cache miss.
            ttl: Optional TTL in seconds.

        Returns:
            The cached or freshly-computed value.
        """
        cached = await self.get(key)
        if cached is not None:
            return cached
        value = await compute_fn()
        await self.set(key, value, ttl=ttl)
        return value

    async def invalidate(self, key: str) -> None:
        """Remove a specific key from the cache (alias for delete)."""
        key_hash = self._hash_key(key)
        with self._lock:
            self._backend.clear_prefix(key_hash)

    async def stats(self) -> dict[str, Any]:
        """Return cache statistics.

        Returns a dict with backend type, entry count, and config info.
        """
        with self._lock:
            return {
                "backend": self.backend_type,
                "entry_count": self._backend.count(),
                "ttl_hours": self._config.ttl_hours,
                "max_size_mb": self._config.max_size_mb,
                "enabled": self._config.enabled,
            }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_key(key: str) -> str:
        """Produce a consistent SHA-256 hash for a cache key."""
        return compute_text_hash(key)

    def __repr__(self) -> str:
        return f"CacheManager(backend={self.backend_type}, enabled={self._config.enabled})"


# Convenience shortcut for pipeline use
DefaultCache = CacheManager
