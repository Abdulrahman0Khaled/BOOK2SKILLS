"""OpenRouter LLM provider implementation."""

from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI

from ..config import PipelineConfig
from ..domain.enums import LLMProvider
from .base import BaseLLMProvider, LLMResponse


class OpenRouterProvider(BaseLLMProvider):
    """OpenRouter provider for accessing 200+ models through one API.

    Uses OpenAI-compatible API endpoint at https://openrouter.ai/api/v1
    """

    def __init__(self, config: PipelineConfig) -> None:
        super().__init__(config)
        self.provider_type = LLMProvider.OPENROUTER
        self.client = AsyncOpenAI(
            base_url=config.llm.base_url or "https://openrouter.ai/api/v1",
            api_key=config.llm.api_key,
            timeout=config.llm.timeout_s,
            max_retries=config.llm.max_retries,
            default_headers={
                "HTTP-Referer": "https://github.com/Abdulrahman0Khaled/BOOK2SKILLS",
                "X-Title": "Book-to-Skills Pipeline",
            },
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

        model_name = model or self.config.llm.model_large
        response = await self.client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=temperature if temperature is not None else self.config.llm.temperature,
            max_tokens=max_tokens or self.config.llm.max_tokens,
        )

        choice = response.choices[0]
        usage = response.usage

        return LLMResponse(
            content=choice.message.content or "",
            model=model_name,
            provider=self.provider_type.value,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
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
        json_prompt = f"{prompt}\n\nRespond with valid JSON."
        resp = await self.generate(
            prompt=json_prompt,
            system_prompt=system_prompt,
            temperature=temperature,
        )
        import json

        return output_schema(**json.loads(resp.content))
