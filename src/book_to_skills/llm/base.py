"""Abstract base class for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel

from ..config import PipelineConfig
from ..domain.enums import LLMProvider


class LLMResponse(BaseModel):
    """Standardized LLM response."""

    content: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    duration_s: float = 0.0
    finish_reason: str = "stop"

    class Config:
        arbitrary_types_allowed = True


class BaseLLMProvider(ABC):
    """Abstract LLM provider with retry, token tracking, and fallback support."""

    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.provider_type: LLMProvider | None = None

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        """Generate text from a prompt."""
        ...

    @abstractmethod
    async def generate_structured(
        self,
        prompt: str,
        output_schema: type[BaseModel],
        system_prompt: str = "",
        temperature: float | None = None,
    ) -> BaseModel:
        """Generate structured output matching a Pydantic schema."""
        ...

    async def generate_with_retry(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
        max_retries: int = 3,
    ) -> LLMResponse:
        """Generate with automatic retry on failure."""
        import asyncio

        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                return await self.generate(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    model=model,
                )
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait = 2**attempt  # exponential backoff
                    await asyncio.sleep(wait)
        raise last_error  # type: ignore[misc]

    def count_tokens(self, text: str) -> int:
        """Approximate token count (4 chars per token)."""
        return len(text) // 4

    def get_small_model(self) -> str:
        return self.config.llm.model_small

    def get_large_model(self) -> str:
        return self.config.llm.model_large
