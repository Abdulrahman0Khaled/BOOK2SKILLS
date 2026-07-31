"""LLM providers for the book-to-skills system.

Each provider wraps a different LLM API and implements
:class:`~book_to_skills.llm.base.BaseLLMProvider`.

Provider classes are imported lazily through the factory, so missing
SDKs (``openai``, ``anthropic``, etc.) do not break imports.
"""

from __future__ import annotations

from .base import BaseLLMProvider, LLMResponse
from .provider_factory import get_llm_provider, register_provider

# Eager imports — will only fail if the SDK is truly needed at import
# time.  For environments where only some providers are installed,
# use the factory.
try:
    from .openai_provider import OpenAIProvider
except ModuleNotFoundError:
    OpenAIProvider = None  # type: ignore[assignment,misc]

try:
    from .anthropic_provider import AnthropicProvider
except ModuleNotFoundError:
    AnthropicProvider = None  # type: ignore[assignment,misc]

try:
    from .gemini_provider import GeminiProvider
except ModuleNotFoundError:
    GeminiProvider = None  # type: ignore[assignment,misc]

try:
    from .ollama_provider import OllamaProvider
except ModuleNotFoundError:
    OllamaProvider = None  # type: ignore[assignment,misc]

try:
    from .openrouter_provider import OpenRouterProvider
except ModuleNotFoundError:
    OpenRouterProvider = None  # type: ignore[assignment,misc]

__all__ = [
    "AnthropicProvider",
    "BaseLLMProvider",
    "GeminiProvider",
    "LLMResponse",
    "OllamaProvider",
    "OpenAIProvider",
    "OpenRouterProvider",
    "get_llm_provider",
    "register_provider",
]
