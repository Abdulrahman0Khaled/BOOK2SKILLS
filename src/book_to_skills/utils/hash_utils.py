"""Hash utilities for incremental processing and caching."""

from __future__ import annotations

import hashlib
import pathlib


def compute_file_hash(file_path: str, algorithm: str = "sha256") -> str:
    """Compute a secure hash of a file for change detection."""
    h = hashlib.new(algorithm)
    with pathlib.Path(file_path).open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def compute_text_hash(text: str) -> str:
    """Compute a hash of text content."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_chunk_hash(chunks: list[dict]) -> str:
    """Compute a combined hash of multiple chunks."""
    h = hashlib.sha256()
    for c in chunks:
        h.update(str(c).encode("utf-8"))
    return h.hexdigest()
