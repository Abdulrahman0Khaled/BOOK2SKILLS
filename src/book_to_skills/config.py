"""Configuration management for book-to-skills pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseModel):
    """LLM provider configuration."""

    provider: str = "openai"
    model_small: str = "gpt-4o-mini"
    model_large: str = "gpt-4o"
    temperature: float = 0.3
    max_tokens: int = 4096
    api_key: str = ""
    base_url: str = ""
    timeout_s: int = 120
    max_retries: int = 3


class ExtractorConfig(BaseModel):
    """Document extractor configuration."""

    use_ocr_fallback: bool = True
    ocr_languages: str = "ara+eng"
    pdf_extraction_mode: str = "hybrid"  # direct, ocr, hybrid
    max_pages: int = 500
    extract_images: bool = False
    dpi: int = 300


class ChunkConfig(BaseModel):
    """Chunking configuration."""

    strategy: str = "semantic"
    max_chunk_words: int = 800
    min_chunk_words: int = 80
    overlap_words: int = 100
    split_at_headings: bool = True
    use_semantic_boundaries: bool = True


class KnowledgeConfig(BaseModel):
    """Knowledge extraction configuration."""

    extract_types: list[str] = Field(
        default_factory=lambda: [
            "skill",
            "best_practice",
            "anti_pattern",
            "rule",
            "workflow",
            "checklist",
            "example",
            "template",
            "framework",
            "decision_tree",
            "common_mistake",
            "reference",
        ]
    )
    min_confidence: float = 0.3
    max_units_per_chunk: int = 10
    include_source_references: bool = True


class SkillGenConfig(BaseModel):
    """Skill generation configuration."""

    include_examples: bool = True
    include_best_practices: bool = True
    include_pitfalls: bool = True
    include_workflow: bool = True
    include_checklist: bool = False
    max_skills_per_book: int = 50


class CacheConfig(BaseModel):
    """Caching configuration."""

    enabled: bool = True
    backend: str = "disk"  # disk, redis, memory
    cache_dir: str = "cache"
    ttl_hours: int = 168  # 7 days
    max_size_mb: int = 1024


class QueueConfig(BaseModel):
    """Queue configuration."""

    backend: str = "memory"  # memory, redis
    redis_url: str = "redis://localhost:6379/0"
    max_concurrent_jobs: int = 4
    default_timeout_s: int = 600


class VectorDBConfig(BaseModel):
    """Vector database configuration."""

    backend: str = "chroma"  # chroma, qdrant
    persist_dir: str = "data/vector_store"
    collection_name: str = "book_skills"
    embedding_dim: int = 384
    distance_metric: str = "cosine"
    embedding_model: str = "all-MiniLM-L6-v2"  # local sentence-transformers model
    embedding_batch_size: int = 32  # texts per model.encode() call


class StorageConfig(BaseModel):
    """Output storage configuration."""

    skills_dir: str = "outputs/skills"
    knowledge_graph_dir: str = "outputs/knowledge_graph"
    embeddings_dir: str = "outputs/embeddings"
    format: str = "markdown"  # markdown, json, yaml


class MonitoringConfig(BaseModel):
    """Monitoring and logging configuration."""

    log_level: str = "INFO"
    log_format: str = "json"  # json, console
    enable_metrics: bool = True
    metrics_port: int = 9090
    enable_progress_bars: bool = True
    structured_logging: bool = True


class PipelineConfig(BaseSettings):
    """Root configuration for the book-to-skills pipeline."""

    model_config = SettingsConfigDict(
        env_prefix="B2S_",
        env_file=".env",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    # General
    project_name: str = "book-to-skills"
    version: str = "1.0.0"
    debug: bool = False
    data_dir: str = "data"
    max_workers: int = 4

    # Sub-configs
    llm: LLMConfig = LLMConfig()
    extractor: ExtractorConfig = ExtractorConfig()
    chunk: ChunkConfig = ChunkConfig()
    knowledge: KnowledgeConfig = KnowledgeConfig()
    skill_gen: SkillGenConfig = SkillGenConfig()
    cache: CacheConfig = CacheConfig()
    queue: QueueConfig = QueueConfig()
    vector_db: VectorDBConfig = VectorDBConfig()
    storage: StorageConfig = StorageConfig()
    monitoring: MonitoringConfig = MonitoringConfig()

    # Pipeline control
    stages_enabled: list[str] = Field(
        default_factory=lambda: [
            "extract",
            "clean",
            "chunk",
            "knowledge",
            "skill_gen",
            "review",
            "dedup",
            "knowledge_graph",
            "embeddings",
            "vector_db",
        ]
    )
    skip_on_error: bool = False
    run_parallel_stages: bool = False
    incremental_mode: bool = True  # skip already-processed files

    @field_validator("stages_enabled")
    @classmethod
    def validate_stages(cls, v: list[str]) -> list[str]:
        valid = {
            "extract",
            "clean",
            "chunk",
            "knowledge",
            "skill_gen",
            "review",
            "dedup",
            "knowledge_graph",
            "embeddings",
            "vector_db",
        }
        for s in v:
            if s not in valid:
                msg = f"Unknown stage: {s}. Valid: {valid}"
                raise ValueError(msg)
        return v

    @property
    def cache_path(self) -> Path:
        return Path(self.cache.cache_dir)

    @property
    def skills_output_path(self) -> Path:
        return Path(self.storage.skills_dir)

    @property
    def vector_store_path(self) -> Path:
        return Path(self.vector_db.persist_dir)

    def model_post_init(self, __context: Any) -> None:
        """Ensure all data directories exist."""
        for d in [self.cache_path, self.skills_output_path, self.vector_store_path]:
            d.mkdir(parents=True, exist_ok=True)
