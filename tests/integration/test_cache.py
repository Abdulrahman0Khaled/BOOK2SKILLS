"""Integration tests for cache manager."""

from __future__ import annotations

import pytest

from book_to_skills.cache.cache_manager import CacheManager
from book_to_skills.config import PipelineConfig


@pytest.mark.integration
class TestCacheManager:
    """Test CacheManager integration."""

    @pytest.fixture
    def config(self):
        return PipelineConfig(
            cache__enabled=True,
            cache__backend="disk",
            cache__cache_dir="/tmp/test-b2s-cache",
            cache__ttl_hours=1,
            monitoring__enable_progress_bars=False,
        )

    @pytest.fixture
    def memory_config(self):
        return PipelineConfig(
            cache__enabled=True,
            cache__backend="memory",
            monitoring__enable_progress_bars=False,
        )

    @pytest.mark.asyncio
    async def test_disk_cache_set_get(self, config):
        mgr = CacheManager(config)
        await mgr.clear()

        await mgr.set("test-key", {"value": 42})
        result = await mgr.get("test-key")
        assert result == {"value": 42}

    @pytest.mark.asyncio
    async def test_disk_cache_miss(self, config):
        mgr = CacheManager(config)
        result = await mgr.get("non-existent-key")
        assert result is None

    @pytest.mark.asyncio
    async def test_disk_cache_clear(self, config):
        mgr = CacheManager(config)
        await mgr.set("key1", "value1")
        await mgr.set("key2", "value2")
        await mgr.clear()
        assert await mgr.get("key1") is None
        assert await mgr.get("key2") is None

    @pytest.mark.asyncio
    async def test_memory_cache(self, memory_config):
        mgr = CacheManager(memory_config)
        await mgr.set("mem-key", {"data": "test"})
        result = await mgr.get("mem-key")
        assert result == {"data": "test"}

    @pytest.mark.asyncio
    async def test_memory_cache_miss(self, memory_config):
        mgr = CacheManager(memory_config)
        assert await mgr.get("nothing") is None

    @pytest.mark.asyncio
    async def test_memory_cache_clear(self, memory_config):
        mgr = CacheManager(memory_config)
        await mgr.set("a", 1)
        await mgr.set("b", 2)
        await mgr.clear()
        assert await mgr.get("a") is None
        assert await mgr.get("b") is None

    @pytest.mark.asyncio
    async def test_disk_cache_overwrite(self, config):
        mgr = CacheManager(config)
        await mgr.set("overwrite-key", "old")
        await mgr.set("overwrite-key", "new")
        result = await mgr.get("overwrite-key")
        assert result == "new"
