"""Test configuration and fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from book_to_skills.config import PipelineConfig
from book_to_skills.domain.models import Book, HermesSkill, KnowledgeUnit, TextChunk

# Test data paths
FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Sample text for testing
SAMPLE_BOOK_TEXT = """
# Chapter 1: The Power of Marketing

Marketing is the most important aspect of any business. Without marketing,
your customers will never know about your product or service.

## The 4 Ps of Marketing

1. Product: What you sell
2. Price: How much you charge
3. Place: Where you sell
4. Promotion: How you reach customers

### Best Practice: Know Your Audience

Always research your target audience before launching any campaign.
Understanding their needs, pain points, and desires is crucial.

### Common Mistake: Trying to Sell to Everyone

When you try to sell to everyone, you end up selling to no one.
Focus on a specific niche and dominate it.

# Chapter 2: Building Your Brand

A strong brand is your most valuable asset. It's what sets you apart
from competitors and builds trust with your customers.
""".strip()

SAMPLE_CHAPTER_TEXT = """
## Brand Storytelling

Stories are 22 times more memorable than facts alone. Use narrative
to connect with your audience on an emotional level.

### Anti-Pattern: Feature Dumping

Don't just list features. Instead, explain how each feature benefits
the customer and solves their problem.
"""


@pytest.fixture
def test_config() -> PipelineConfig:
    """Create a test configuration with minimal settings."""
    return PipelineConfig(
        debug=True,
        cache__enabled=False,
        monitoring__log_level="DEBUG",
        monitoring__log_format="console",
        monitoring__enable_progress_bars=False,
        llm__provider="openai",
        llm__model_small="gpt-4o-mini",
        llm__model_large="gpt-4o",
        queue__backend="memory",
        queue__max_concurrent_jobs=2,
    )


@pytest.fixture
def sample_book() -> Book:
    """Create a sample book for testing."""
    return Book(
        id="test-book-001",
        title="Marketing Mastery",
        file_path="/tmp/test-book.pdf",
        format="pdf",
        file_size_bytes=1024,
        file_hash="abc123def456",
        total_pages=50,
    )


@pytest.fixture
def sample_chunks() -> list[TextChunk]:
    """Create sample text chunks for testing."""
    return [
        TextChunk(
            id="chunk-001",
            cleaned_id="clean-001",
            index=0,
            text=SAMPLE_BOOK_TEXT,
            word_count=len(SAMPLE_BOOK_TEXT.split()),
        ),
        TextChunk(
            id="chunk-002",
            cleaned_id="clean-001",
            index=1,
            text=SAMPLE_CHAPTER_TEXT,
            word_count=len(SAMPLE_CHAPTER_TEXT.split()),
        ),
    ]


@pytest.fixture
def sample_knowledge_units() -> list[KnowledgeUnit]:
    """Create sample knowledge units for testing."""
    return [
        KnowledgeUnit(
            id="ku-001",
            chunk_id="chunk-001",
            unit_type="skill",
            title="Know Your Audience",
            content="Always research your target audience before launching any campaign.",
            confidence=0.95,
            tags=["marketing", "audience", "research"],
        ),
        KnowledgeUnit(
            id="ku-002",
            chunk_id="chunk-001",
            unit_type="best_practice",
            title="Focus on a Specific Niche",
            content="When you try to sell to everyone, you end up selling to no one.",
            confidence=0.88,
            tags=["marketing", "niche", "focus"],
        ),
        KnowledgeUnit(
            id="ku-003",
            chunk_id="chunk-002",
            unit_type="anti_pattern",
            title="Feature Dumping",
            content="Don't just list features. Explain how each feature benefits the customer.",
            confidence=0.92,
            tags=["marketing", "features", "benefits"],
        ),
    ]


@pytest.fixture
def sample_skill() -> HermesSkill:
    """Create a sample HermesSkill for testing."""
    return HermesSkill(
        id="skill-001",
        knowledge_ids=["ku-001", "ku-002"],
        name="audience-research",
        description="Best practices for researching and understanding your target audience",
        version="1.0.0",
        best_practices=[
            "Research audience demographics before campaigns",
            "Use surveys and interviews for qualitative data",
            "Analyze competitor audiences for gaps",
        ],
        pitfalls=[
            "Assuming you know your audience without data",
            "Targeting too broad an audience",
        ],
        examples=[
            {
                "title": "Audience Persona Template",
                "code": "Name: Ideal Customer\nAge: 25-45\nNeeds: X, Y, Z",
            },
        ],
        workflow=[
            {"title": "Define", "description": "Define your ideal customer profile"},
            {"title": "Research", "description": "Conduct market research"},
        ],
        tags=["marketing", "audience", "research"],
        category="marketing",
    )


@pytest_asyncio.fixture
async def temp_output_dir(tmp_path: Path) -> Path:
    """Create a temporary output directory."""
    d = tmp_path / "outputs"
    d.mkdir(parents=True)
    return d
