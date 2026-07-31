"""LLM Provider Factory — resolves a provider string to a concrete instance.

Usage::

    from book_to_skills.llm.provider_factory import get_llm_provider
    provider = get_llm_provider(config)
    resp = await provider.generate("Hello")
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..config import PipelineConfig
from ..domain.enums import LLMProvider

if TYPE_CHECKING:
    from .base import BaseLLMProvider

# Lazy registry: mapping from LLMProvider enum to fully-qualified
# module path + class name.  Actual import happens inside
# ``get_llm_provider`` so that missing SDKs do not break imports.
_REGISTRY: dict[LLMProvider, tuple[str, str]] = {
    LLMProvider.OPENAI: ("book_to_skills.llm.openai_provider", "OpenAIProvider"),
    LLMProvider.ANTHROPIC: ("book_to_skills.llm.anthropic_provider", "AnthropicProvider"),
    LLMProvider.DEEPSEEK: ("book_to_skills.llm.deepseek_provider", "DeepSeekProvider"),
    LLMProvider.GEMINI: ("book_to_skills.llm.gemini_provider", "GeminiProvider"),
    LLMProvider.OLLAMA: ("book_to_skills.llm.ollama_provider", "OllamaProvider"),
    LLMProvider.OPENROUTER: ("book_to_skills.llm.openrouter_provider", "OpenRouterProvider"),
}


def get_llm_provider(config: PipelineConfig) -> BaseLLMProvider:
    """Resolve the configured LLM provider and return an instance.

    The provider class is imported lazily — the required SDK
    (e.g. ``openai``, ``anthropic``) is only loaded at call time.

    Parameters
    ----------
    config : PipelineConfig
        Must have ``config.llm.provider`` set to one of the supported
        :class:`~book_to_skills.domain.enums.LLMProvider` values.

    Returns
    -------
    BaseLLMProvider
        An initialised provider instance.

    Raises
    ------
    ValueError
        If the provider string is unknown or unregistered.
    ImportError
        If the required SDK is not installed.
    """

    provider_name = config.llm.provider
    try:
        provider_enum = LLMProvider(provider_name.lower())
    except ValueError:
        supported = list(_REGISTRY.keys())
        msg = f"Unknown LLM provider: '{provider_name}'. Supported: {[p.value for p in supported]}"
        raise ValueError(msg) from None

    entry = _REGISTRY.get(provider_enum)
    if entry is None:
        supported = list(_REGISTRY.keys())
        msg = (
            f"Provider '{provider_name}' is recognised but has no registered "
            f"implementation. Supported: {[p.value for p in supported]}"
        )
        raise ValueError(msg)

    module_path, class_name = entry

    import importlib

    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        msg = (
            f"Failed to import provider module '{module_path}' for "
            f"'{provider_name}': {exc}. "
            f"Make sure the required SDK is installed."
        )
        raise ImportError(msg) from exc

    provider_cls: type[BaseLLMProvider] = getattr(module, class_name)
    return provider_cls(config)


def register_provider(
    enum_value: str,
    module_path: str,
    class_name: str,
) -> None:
    """Register a custom provider at runtime.

    Parameters
    ----------
    enum_value : str
        The string value for the :class:`LLMProvider` enum (e.g. ``"custom"``).
    module_path : str
        Fully-qualified module path (e.g. ``"my_package.my_provider"``).
    class_name : str
        Name of the provider class in that module.
    """
    provider_enum = LLMProvider(enum_value.lower())
    _REGISTRY[provider_enum] = (module_path, class_name)
