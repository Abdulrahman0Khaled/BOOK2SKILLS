"""Google Gemini LLM provider implementation."""

from __future__ import annotations

from typing import Any

import google.generativeai as genai

from ..config import PipelineConfig
from ..domain.enums import LLMProvider
from .base import BaseLLMProvider, LLMResponse


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API provider."""

    def __init__(self, config: PipelineConfig) -> None:
        super().__init__(config)
        self.provider_type = LLMProvider.GEMINI
        genai.configure(api_key=config.llm.api_key)

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

        model_name = model or self.config.llm.model_large
        gen_model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_prompt or None,
        )

        gen_config: dict[str, Any] = {}
        if temperature is not None:
            gen_config["temperature"] = temperature
        if max_tokens is not None:
            gen_config["max_output_tokens"] = max_tokens

        response = await gen_model.generate_content_async(
            prompt,
            generation_config=gen_config,
        )

        return LLMResponse(
            content=response.text,
            model=model_name,
            provider=self.provider_type.value,
            prompt_tokens=0,  # Gemini doesn't expose token counts easily
            completion_tokens=0,
            total_tokens=0,
            duration_s=time.monotonic() - start,
            finish_reason="stop",
        )

    async def generate_structured(
        self,
        prompt: str,
        output_schema: type[Any],
        system_prompt: str = "",
        temperature: float | None = None,
    ) -> Any:
        import json

        json_prompt = f"{prompt}\n\nRespond with valid JSON matching this schema."
        resp = await self.generate(
            prompt=json_prompt,
            system_prompt=system_prompt,
            temperature=temperature,
        )
        return output_schema(**json.loads(resp.content))
