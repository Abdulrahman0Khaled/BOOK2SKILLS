"""Text normalization utilities for skill names and content."""

from __future__ import annotations

import re

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_SNAKE_UNDERSCORE = re.compile(r"[_-]+")
_MULTI_SPACE = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-zA-Z0-9\s-]")
_ARTICLES = {"a", "an", "the", "of", "for", "and", "or", "to", "in", "on", "with"}


def normalize_skill_name(raw: str) -> str:
    """Convert a raw LLM title into a clean, kebab-case skill name.

    Handles:
    - CamelCase (``SingleClickAction`` → ``single-click-action``)
    - snake_case (``single_click_action`` → ``single-click-action``)
    - Run-on words (``OverwhelmProspects`` → ``overwhelm-prospects``)
    - Extra whitespace, punctuation, trailing junk

    Args:
        raw: Raw title string from the LLM or heuristics.

    Returns:
        Cleaned kebab-case skill name.
    """
    if not raw:
        return ""

    # Split CamelCase boundaries first
    text = _CAMEL_BOUNDARY.sub(" ", raw)
    # Replace underscores/hyphens with spaces
    text = _SNAKE_UNDERSCORE.sub(" ", text)
    # Remove stray non-alphanumeric (keep spaces and hyphens)
    text = _NON_ALNUM.sub(" ", text)
    # Collapse whitespace
    text = _MULTI_SPACE.sub(" ", text).strip().lower()

    # Remove leading "how to" duplication patterns like "how-to-how-to-..."
    words = text.split()
    if len(words) >= 3 and words[0] == "how" and words[1] == "to" and words[2] == "how":
        words = words[2:]

    # Drop trailing dangling words like "technique", "method" when redundant
    # (keep if the name would be too short without them)
    if len(words) > 2 and words[-1] in {"technique", "method", "strategy", "approach"}:
        words = words[:-1]

    if not words:
        return ""

    # kebab-case
    return "-".join(words)


def normalize_title(raw: str) -> str:
    """Clean a title for display (Title Case, no underscores)."""
    if not raw:
        return ""

    text = _CAMEL_BOUNDARY.sub(" ", raw)
    text = _SNAKE_UNDERSCORE.sub(" ", text)
    text = _MULTI_SPACE.sub(" ", text).strip()

    words = text.split()
    result: list[str] = []
    for i, w in enumerate(words):
        lower = w.lower()
        if i == 0 or lower not in _ARTICLES:
            result.append(w.capitalize() if w.islower() else w)
        else:
            result.append(lower)
    return " ".join(result)


def slugify(text: str, max_len: int = 60) -> str:
    """Convert arbitrary text into a URL/skill slug."""
    clean = _NON_ALNUM.sub(" ", text)
    words = clean.split()
    slug = "-".join(w.lower() for w in words)
    return slug[:max_len].rstrip("-")
