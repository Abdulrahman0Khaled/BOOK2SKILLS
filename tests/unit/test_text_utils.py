"""Unit tests for text normalization utilities."""

from __future__ import annotations

from book_to_skills.utils.text_utils import (
    normalize_skill_name,
    normalize_title,
    slugify,
)


class TestNormalizeSkillName:
    """Test skill name normalization."""

    def test_camel_case(self):
        assert normalize_skill_name("SingleClickAction") == "single-click-action"

    def test_snake_case(self):
        assert normalize_skill_name("single_click_action") == "single-click-action"

    def test_already_kebab(self):
        assert normalize_skill_name("single-click-action") == "single-click-action"

    def test_space_separated(self):
        assert normalize_skill_name("Single Click Action") == "single-click-action"

    def test_runon_words(self):
        assert normalize_skill_name("OverwhelmProspects") == "overwhelm-prospects"

    def test_drops_redundant_suffix(self):
        assert normalize_skill_name("Command Attention Technique") == "command-attention"

    def test_how_to_prefix(self):
        assert normalize_skill_name("How to RecordedWebinars") == "how-to-recorded-webinars"

    def test_empty(self):
        assert normalize_skill_name("") == ""
        assert normalize_skill_name("   ") == ""

    def test_punctuation_stripped(self):
        assert normalize_skill_name("Sales Funnel!!!") == "sales-funnel"

    def test_mixed_junk(self):
        result = normalize_skill_name("PleasureQuestionsExample_2")
        assert "pleasure-questions-example" in result


class TestNormalizeTitle:
    """Test display title normalization."""

    def test_camel_case(self):
        assert normalize_title("BufferFoundingStory") == "Buffer Founding Story"

    def test_underscores(self):
        assert normalize_title("external_trigger_examples") == "External Trigger Examples"

    def test_articles_lowercase(self):
        result = normalize_title("The Art of the Sale")
        assert "the" in result.lower()
        assert "of" in result.split()  # 'of' stays lowercase

    def test_empty(self):
        assert normalize_title("") == ""


class TestSlugify:
    """Test slug generation."""

    def test_basic(self):
        assert slugify("Hello World") == "hello-world"

    def test_max_len(self):
        assert len(slugify("A very long title that should be truncated properly", max_len=20)) <= 20

    def test_special_chars(self):
        assert slugify("C++ & Python!") == "c-python"

    def test_empty(self):
        assert slugify("") == ""
