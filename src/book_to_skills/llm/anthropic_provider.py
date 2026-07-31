"""Anthropic Claude LLM provider implementation."""

from __future__ import annotations

from typing import Any

from anthropic import AsyncAnthropic

from ..config import PipelineConfig
from ..domain.enums import LLMProvider
from .base import BaseLLMProvider, LLMResponse


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude API provider."""

    def __init__(self, config: PipelineConfig) -> None:
        super().__init__(config)
        self.provider_type = LLMProvider.ANTHROPIC
        self.client = AsyncAnthropic(
            api_key=config.llm.api_key,
            max_retries=config.llm.max_retries,
            timeout=config.llm.timeout_s,
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

        kwargs: dict[str, Any] = {
            "model": model or self.config.llm.model_large,
            "max_tokens": max_tokens or self.config.llm.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if system_prompt:
            kwargs["system"] = system_prompt

        response = await self.client.messages.create(**kwargs)

        return LLMResponse(
            content=response.content[0].text if response.content else "",
            model=response.model,
            provider=self.provider_type.value,
            prompt_tokens=response.usage.input_tokens if response.usage else 0,
            completion_tokens=response.usage.output_tokens if response.usage else 0,
            total_tokens=(
                (response.usage.input_tokens + response.usage.output_tokens)
                if response.usage
                else 0
            ),
            duration_s=time.monotonic() - start,
            finish_reason=response.stop_reason or "stop",
        )

    async def generate_structured(
        self,
        prompt: str,
        output_schema: type[Any],
        system_prompt: str = "",
        temperature: float | None = None,
    ) -> Any:
        # Claude doesn't support native structured output like OpenAI.
        # Fallback: generate text and parse as JSON.
        json_prompt = f"{prompt}\n\nRespond with valid JSON matching this schema."
        resp = await self.generate(
            prompt=json_prompt,
            system_prompt=system_prompt,
            temperature=temperature,
        )
        import json

        return output_schema(**json.loads(resp.content))
