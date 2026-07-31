"""Unit tests for hash utilities."""

from __future__ import annotations

from book_to_skills.utils.hash_utils import compute_file_hash, compute_text_hash


class TestHashUtils:
    """Test hash utility functions."""

    def test_text_hash_consistency(self):
        h1 = compute_text_hash("hello world")
        h2 = compute_text_hash("hello world")
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_text_hash_different(self):
        h1 = compute_text_hash("hello world")
        h2 = compute_text_hash("hello world!")
        assert h1 != h2

    def test_text_hash_empty(self):
        h = compute_text_hash("")
        assert len(h) == 64

    def test_file_hash_consistency(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        h1 = compute_file_hash(str(f))
        h2 = compute_file_hash(str(f))
        assert h1 == h2

    def test_file_hash_changes_with_content(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        h1 = compute_file_hash(str(f))

        f.write_text("hello world!")
        h2 = compute_file_hash(str(f))
        assert h1 != h2

    def test_file_hash_algorithm(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("data")
        h = compute_file_hash(str(f), algorithm="sha256")
        assert len(h) == 64

    def test_file_hash_large_file(self, tmp_path):
        f = tmp_path / "large.txt"
        f.write_bytes(b"x" * 100000)  # >64KB to test chunking
        h = compute_file_hash(str(f))
        assert len(h) == 64
