"""OpenAI LLM provider implementation."""

from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI

from ..config import PipelineConfig
from ..domain.enums import LLMProvider
from .base import BaseLLMProvider, LLMResponse


class OpenAIProvider(BaseLLMProvider):
    """OpenAI API provider (GPT-4o, GPT-4o-mini, etc.)."""

    def __init__(self, config: PipelineConfig) -> None:
        super().__init__(config)
        self.provider_type = LLMProvider.OPENAI
        self.client = AsyncOpenAI(
            api_key=config.llm.api_key or None,
            base_url=config.llm.base_url or None,
            timeout=config.llm.timeout_s,
            max_retries=config.llm.max_retries,
        )

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        import time

        start = time.monotonic()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await self.client.chat.completions.create(
            model=model or self.config.llm.model_large,
            messages=messages,
            temperature=temperature if temperature is not None else self.config.llm.temperature,
            max_tokens=max_tokens or self.config.llm.max_tokens,
        )

        choice = response.choices[0]
        usage = response.usage

        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            provider=self.provider_type.value,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=(usage.total_tokens if usage else 0),
            duration_s=time.monotonic() - start,
            finish_reason=choice.finish_reason or "stop",
        )

    async def generate_structured(
        self,
        prompt: str,
        output_schema: type[Any],
        system_prompt: str = "",
        temperature: float | None = None,
    ) -> Any:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await self.client.beta.chat.completions.parse(
            model=self.config.llm.model_large,
            messages=messages,
            response_format=output_schema,
            temperature=temperature if temperature is not None else self.config.llm.temperature,
        )

        return response.choices[0].message.parsed
