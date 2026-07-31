"""Unit tests for LLM base provider."""

from __future__ import annotations

from book_to_skills.llm.base import BaseLLMProvider, LLMResponse


class TestLLMResponse:
    """Test LLMResponse model."""

    def test_create_response(self):
        resp = LLMResponse(
            content="Hello",
            model="gpt-4o",
            provider="openai",
        )
        assert resp.content == "Hello"
        assert resp.model == "gpt-4o"
        assert resp.provider == "openai"
        assert resp.total_tokens == 0
        assert resp.finish_reason == "stop"

    def test_token_counts(self):
        resp = LLMResponse(
            content="Test",
            model="gpt-4o",
            provider="openai",
            prompt_tokens=50,
            completion_tokens=150,
            total_tokens=200,
        )
        assert resp.total_tokens == 200


class TestBaseLLMProvider:
    """Test BaseLLMProvider abstract class."""

    def test_count_tokens(self):
        from book_to_skills.config import PipelineConfig

        class TestProvider(BaseLLMProvider):
            async def generate(self, prompt, **kwargs):
                return LLMResponse(content="", model="", provider="")

            async def generate_structured(self, prompt, output_schema, **kwargs):
                return output_schema()

        provider = TestProvider(PipelineConfig())
        assert provider.count_tokens("hello") == 1
        assert provider.count_tokens("a" * 40) == 10

    def test_model_selection(self):
        from book_to_skills.config import PipelineConfig

        class TestProvider(BaseLLMProvider):
            async def generate(self, prompt, **kwargs):
                return LLMResponse(content="", model="", provider="")

            async def generate_structured(self, prompt, output_schema, **kwargs):
                return output_schema()

        cfg = PipelineConfig()
        cfg.llm.model_small = "gpt-4o-mini"
        cfg.llm.model_large = "claude-sonnet-4"
        provider = TestProvider(cfg)
        assert provider.get_small_model() == "gpt-4o-mini"
        assert provider.get_large_model() == "claude-sonnet-4"
