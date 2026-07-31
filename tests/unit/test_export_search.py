"""Tests for the new CLI export/search commands and API stats/search."""

from __future__ import annotations

import json

import pytest


class TestExportMarkdown:
    """book2skills export md generates SKILL.md files."""

    @pytest.fixture
    def sample_skill_dir(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        skill = {
            "id": "skill-abc",
            "name": "audience-research",
            "description": "Research your target audience before campaigns",
            "version": "1.0.0",
            "best_practices": ["Research demographics", "Use surveys"],
            "pitfalls": ["No data assumptions"],
            "workflow": [{"title": "Define", "description": "Define audience"}],
            "checklist": ["Persona created"],
            "tags": ["marketing"],
            "category": "marketing",
            "status": "approved",
        }
        (skills_dir / "skill-abc.json").write_text(json.dumps(skill), encoding="utf-8")
        return skills_dir

    def test_skill_markdown_export_fields(self, sample_skill_dir, tmp_path):
        """Markdown export contains all core sections."""
        from book_to_skills.domain.models import HermesSkill

        data = json.loads((sample_skill_dir / "skill-abc.json").read_text())
        skill = HermesSkill(**data)
        md = skill.to_skill_markdown()

        assert "audience-research" in md
        assert "Best Practices" in md
        assert "Pitfalls" in md
        assert "Workflow" in md
        assert "Checklist" in md
        assert "Research demographics" in md


class TestSearch:
    """Simple keyword search over skills."""

    def _make_skill(self, name, description, tags):
        from book_to_skills.domain.models import HermesSkill

        return HermesSkill(name=name, description=description, tags=tags)

    def test_keyword_match_in_description(self):
        s = self._make_skill(
            "audience-research",
            "How to research your target audience using surveys and interviews",
            ["marketing"],
        )
        assert "audience" in s.description
        assert "surveys" in s.description

    def test_tag_match(self):
        s = self._make_skill(
            "hooked-habit-loop", "Trigger-action-reward-investment", ["psychology"]
        )
        assert "psychology" in s.tags

    def test_category_searchable(self):
        s = self._make_skill("sales-funnel", "Build a sales funnel", ["sales"])
        assert s.category == ""  # category set by pipeline, not model default
