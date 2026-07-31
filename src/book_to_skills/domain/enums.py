"""Enumerations for the book-to-skills pipeline."""

from enum import Enum


class PipelineStage(str, Enum):
    """Stages of the book-to-skills pipeline."""

    EXTRACT = "extract"
    CLEAN = "clean"
    CHUNK = "chunk"
    KNOWLEDGE = "knowledge"
    SKILL_GEN = "skill_gen"
    REVIEW = "review"
    DEDUP = "dedup"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    EMBEDDINGS = "embeddings"
    VECTOR_DB = "vector_db"

    def __str__(self) -> str:
        return self.value

    @property
    def description(self) -> str:
        descriptions = {
            PipelineStage.EXTRACT: "Extract raw text from PDF/DOCX documents",
            PipelineStage.CLEAN: "Clean and normalize extracted text",
            PipelineStage.CHUNK: "Split text into semantic chunks",
            PipelineStage.KNOWLEDGE: "Extract structured knowledge from chunks",
            PipelineStage.SKILL_GEN: "Generate Hermes Skills from knowledge",
            PipelineStage.REVIEW: "Review and validate generated skills",
            PipelineStage.DEDUP: "Deduplicate skills across the system",
            PipelineStage.KNOWLEDGE_GRAPH: "Build knowledge graph relationships",
            PipelineStage.EMBEDDINGS: "Generate vector embeddings",
            PipelineStage.VECTOR_DB: "Store embeddings in vector database",
        }
        return descriptions.get(self, "Unknown stage")


class BookFormat(str, Enum):
    """Supported book file formats."""

    PDF = "pdf"
    DOCX = "docx"
    DOC = "doc"

    @classmethod
    def from_extension(cls, path: str) -> "BookFormat":
        ext = path.rsplit(".", 1)[-1].lower()
        if ext == "pdf":
            return cls.PDF
        if ext in ("docx", "doc"):
            return cls.DOCX
        msg = f"Unsupported format: {ext}"
        raise ValueError(msg)


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    GEMINI = "gemini"
    OLLAMA = "ollama"
    OPENROUTER = "openrouter"

    @property
    def requires_api_key(self) -> bool:
        return self in {
            LLMProvider.OPENAI,
            LLMProvider.ANTHROPIC,
            LLMProvider.DEEPSEEK,
            LLMProvider.GEMINI,
            LLMProvider.OPENROUTER,
        }


class ExtractionMethod(str, Enum):
    """Method used for text extraction."""

    DIRECT = "direct"
    OCR = "ocr"
    HYBRID = "hybrid"


class SkillStatus(str, Enum):
    """Status of a generated skill."""

    DRAFT = "draft"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"


class ChunkStrategy(str, Enum):
    """Chunking strategies for text segmentation."""

    SEMANTIC = "semantic"
    PARAGRAPH = "paragraph"
    FIXED_SIZE = "fixed_size"
    RECURSIVE = "recursive"
    HYBRID = "hybrid"


class QueuePriority(int, Enum):
    """Task queue priority levels."""

    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3
    BATCH = 4
