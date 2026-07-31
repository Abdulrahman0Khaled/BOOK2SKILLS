"""File utility functions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def ensure_dir(path: str | Path) -> Path:
    """Ensure a directory exists and return it as Path."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_text(file_path: str | Path) -> str:
    """Read a text file."""
    return Path(file_path).read_text(encoding="utf-8")


def write_text(file_path: str | Path, content: str) -> None:
    """Write text to a file, creating parent directories."""
    p = Path(file_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def read_json(file_path: str | Path) -> Any:
    """Read and parse a JSON file."""
    return json.loads(Path(file_path).read_text(encoding="utf-8"))


def write_json(file_path: str | Path, data: Any, indent: int = 2) -> None:
    """Write data as JSON to a file."""
    p = Path(file_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=indent, ensure_ascii=False, default=str), encoding="utf-8")


def read_yaml(file_path: str | Path) -> Any:
    """Read and parse a YAML file."""
    with Path(file_path).open() as f:
        return yaml.safe_load(f)


def write_yaml(file_path: str | Path, data: Any) -> None:
    """Write data as YAML to a file."""
    p = Path(file_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with Path(p).open("w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def get_file_extension(file_path: str) -> str:
    """Get the file extension without dot, lowercased."""
    return Path(file_path).suffix.lstrip(".").lower()


def file_size_mb(file_path: str) -> float:
    """Get file size in megabytes."""
    return Path(file_path).stat().st_size / (1024 * 1024)


async def compute_file_hash(file_path: str | Path, algorithm: str = "sha256") -> str:
    """Compute the hash of a file asynchronously (SHA-256 default).

    Parameters
    ----------
    file_path : str | Path
        Path to the file.
    algorithm : str
        Hash algorithm name (``"sha256"``, ``"md5"``, etc.).

    Returns
    -------
    str
        Hexadecimal digest of the file.
    """
    import hashlib

    h = hashlib.new(algorithm)
    path = Path(file_path)
    with path.open("rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()
