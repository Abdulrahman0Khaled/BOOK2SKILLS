"""Unit tests for configuration."""

from __future__ import annotations

from pathlib import Path

from book_to_skills.config import PipelineConfig


class TestPipelineConfig:
    """Test pipeline configuration."""

    def test_default_config(self):
        config = PipelineConfig(_env_file=None)
        assert config.project_name == "book-to-skills"
        assert config.llm.provider == "openai"
        assert config.llm.temperature == 0.3
        assert config.extractor.use_ocr_fallback is True
        assert config.chunk.strategy == "semantic"
        assert config.chunk.max_chunk_words == 800
        assert config.chunk.overlap_words == 100
        assert config.cache.enabled is True
        assert config.cache.backend == "disk"
        assert config.queue.backend == "memory"
        assert config.queue.max_concurrent_jobs == 4

    def test_config_paths(self):
        config = PipelineConfig()
        assert config.cache_path == Path("cache")
        assert config.skills_output_path == Path("outputs/skills")
        assert config.vector_store_path == Path("data/vector_store")

    def test_config_env_override(self, monkeypatch):
        monkeypatch.setenv("B2S_LLM__PROVIDER", "anthropic")
        monkeypatch.setenv("B2S_LLM__MODEL_LARGE", "claude-sonnet-4")
        monkeypatch.setenv("B2S_MAX_WORKERS", "8")

        config = PipelineConfig()
        assert config.llm.provider == "anthropic"
        assert config.llm.model_large == "claude-sonnet-4"
        assert config.max_workers == 8

    def test_valid_stages_default(self):
        config = PipelineConfig()
        assert len(config.stages_enabled) == 10
        assert "extract" in config.stages_enabled
        assert "vector_db" in config.stages_enabled

    def test_invalid_stage_raises(self):
        import pytest

        with pytest.raises(ValueError):
            PipelineConfig(stages_enabled=["extract", "invalid_stage"])

    def test_config_debug_mode(self):
        config = PipelineConfig(debug=True)
        assert config.debug is True
        assert config.monitoring.log_level == "INFO"  # not auto-changed by debug

    def test_incremental_default(self):
        config = PipelineConfig()
        assert config.incremental_mode is True
        assert config.skip_on_error is False

    def test_parallel_stages_default(self):
        config = PipelineConfig()
        assert config.run_parallel_stages is False

    def test_cache_ttl(self):
        config = PipelineConfig()
        assert config.cache.ttl_hours == 168  # 7 days

    def test_vector_db_defaults(self):
        config = PipelineConfig()
        assert config.vector_db.backend == "chroma"
        assert config.vector_db.distance_metric == "cosine"
        assert config.vector_db.collection_name == "book_skills"

    def test_monitoring_defaults(self):
        config = PipelineConfig()
        assert config.monitoring.structured_logging is True
        assert config.monitoring.enable_metrics is True

    def test_skill_gen_defaults(self):
        config = PipelineConfig()
        assert config.skill_gen.include_examples is True
        assert config.skill_gen.include_pitfalls is True
        assert config.skill_gen.max_skills_per_book == 50

    def test_knowledge_extract_types(self):
        config = PipelineConfig()
        assert "skill" in config.knowledge.extract_types
        assert "best_practice" in config.knowledge.extract_types
        assert "anti_pattern" in config.knowledge.extract_types
        assert len(config.knowledge.extract_types) >= 10
