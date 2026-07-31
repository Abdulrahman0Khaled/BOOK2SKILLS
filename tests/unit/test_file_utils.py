"""Unit tests for file utility functions."""

from __future__ import annotations

from book_to_skills.utils.file_utils import (
    ensure_dir,
    file_size_mb,
    get_file_extension,
    read_json,
    read_text,
    read_yaml,
    write_json,
    write_text,
    write_yaml,
)


class TestFileUtils:
    """Test file utility functions."""

    def test_ensure_dir_creates(self, tmp_path):
        d = tmp_path / "new" / "deep" / "dir"
        result = ensure_dir(d)
        assert result.exists()
        assert result.is_dir()

    def test_ensure_dir_exists(self, tmp_path):
        d = tmp_path / "existing"
        d.mkdir(parents=True)
        result = ensure_dir(d)
        assert result == d

    def test_write_and_read_text(self, tmp_path):
        f = tmp_path / "test.txt"
        write_text(str(f), "hello world")
        assert read_text(str(f)) == "hello world"

    def test_write_text_creates_dirs(self, tmp_path):
        f = tmp_path / "a" / "b" / "c" / "test.txt"
        write_text(str(f), "content")
        assert f.exists()

    def test_write_and_read_json(self, tmp_path):
        f = tmp_path / "data.json"
        data = {"name": "test", "value": 42}
        write_json(str(f), data)
        result = read_json(str(f))
        assert result == data

    def test_write_and_read_yaml(self, tmp_path):
        f = tmp_path / "config.yaml"
        data = {"name": "test", "items": [1, 2, 3]}
        write_yaml(str(f), data)
        result = read_yaml(str(f))
        assert result == data

    def test_get_file_extension(self):
        assert get_file_extension("test.pdf") == "pdf"
        assert get_file_extension("test.DOCX") == "docx"
        assert get_file_extension("path/to/file.txt") == "txt"

    def test_file_size_mb(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"x" * 1048576)  # 1 MB
        size = file_size_mb(str(f))
        assert 0.99 < size < 1.01  # approximately 1 MB

    def test_file_size_empty(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        assert file_size_mb(str(f)) == 0.0

    def test_write_json_with_complex_types(self, tmp_path):
        f = tmp_path / "complex.json"
        from datetime import datetime

        data = {"timestamp": datetime(2024, 1, 1)}
        write_json(str(f), data)  # should not raise
        result = read_json(str(f))
        assert "timestamp" in result
