"""SkillGenStage — generate HermesSkills from knowledge units.

Takes the KnowledgeUnits accumulated in the context, groups them by
topic (connected components over shared tags), and compiles each group
into a fully-formed HermesSkill.

When an LLM provider is configured, each group is sent to the LLM with
a strict JSON schema to produce a professional skill name, a rich
description, a category from a fixed list, and specific tags.  The name
is then normalised with
:func:`~book_to_skills.utils.text_utils.normalize_skill_name` (clean
kebab-case).  If the LLM is unavailable, a heuristic fallback assembles
the skill from the units directly.

Every generated skill has its structured sections (best practices,
pitfalls, workflow, checklist, examples) populated from the available
units whenever possible, carries provenance (``book_id``,
``source_book``, ``source_chapters``), and is exported as a
Hermes-compatible ``SKILL.md`` file under
``{storage.skills_dir}/markdown/``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..config import PipelineConfig
from ..domain.enums import PipelineStage, SkillStatus
from ..domain.models import HermesSkill, KnowledgeUnit, PipelineContext
from ..utils.text_utils import normalize_skill_name, normalize_title, slugify
from .base import BaseStage

# Fixed category vocabulary the LLM must pick from.
CATEGORIES: list[str] = [
    "marketing",
    "sales",
    "product",
    "business",
    "personal-development",
    "psychology",
    "finance",
    "technology",
    "writing",
    "leadership",
]

# Tag keyword stems -> category (heuristic fallback only).
_CATEGORY_KEYWORDS: dict[str, str] = {
    "marketing": "marketing",
    "advertis": "marketing",
    "brand": "marketing",
    "seo": "marketing",
    "funnel": "marketing",
    "social-media": "marketing",
    "email-marketing": "marketing",
    "lead-generation": "marketing",
    "copywriting": "writing",
    "storytell": "writing",
    "sales": "sales",
    "negotiat": "sales",
    "prospect": "sales",
    "closing": "sales",
    "pricing": "product",
    "product": "product",
    "ux": "product",
    "entrepreneur": "business",
    "startup": "business",
    "business": "business",
    "strategy": "business",
    "operations": "business",
    "finance": "finance",
    "invest": "finance",
    "budget": "finance",
    "accounting": "finance",
    "productivity": "personal-development",
    "habit": "personal-development",
    "discipline": "personal-development",
    "mindset": "personal-development",
    "time-management": "personal-development",
    "goals": "personal-development",
    "persuas": "psychology",
    "psycholog": "psychology",
    "influence": "psychology",
    "behavior": "psychology",
    "leadership": "leadership",
    "teamwork": "leadership",
    "hiring": "leadership",
    "communication": "leadership",
    "management": "leadership",
    "technology": "technology",
    "software": "technology",
    "automation": "technology",
    "api": "technology",
    "coding": "technology",
    "ai": "technology",
}


class SkillSchema(BaseModel):
    """Strict JSON schema for LLM-generated skill metadata."""

    name: str = Field(
        default="", description="Short professional skill name, 3-6 words, Title Case"
    )
    description: str = Field(
        default="",
        description="2-4 rich, actionable sentences grounded in the units",
    )
    category: str = Field(default="", description=f"Exactly one of: {', '.join(CATEGORIES)}")
    tags: list[str] = Field(default_factory=list, description="4-8 specific lowercase tags")


_SYSTEM_PROMPT = (
    "You are a senior skill architect. Given knowledge units extracted "
    "from a book, design ONE professional, actionable AI agent skill "
    "(compatible with OpenClaw, Claude, Codex, Hermes, and other AI agents). "
    "Ground every statement in the provided units — never invent. "
    "Respond with valid JSON only, no markdown fences, no commentary."
)


class SkillGenStage(BaseStage):
    """Pipeline stage that generates ``HermesSkill`` objects from knowledge.

    Groups knowledge units by topic (shared tags) and assembles each
    group into a single skill with best practices, pitfalls, examples,
    workflow steps, and a checklist derived from the available units.
    Uses the LLM to name and describe each skill when available.

    Skills are stored in ``context.skills`` and exported as
    ``SKILL.md`` files under ``{storage.skills_dir}/markdown/``.

    Example::

        stage = SkillGenStage(config)
        context = await stage.execute(context)
        assert len(context.skills) > 0
    """

    def __init__(self, config: PipelineConfig) -> None:
        super().__init__(config)
        self.stage = PipelineStage.SKILL_GEN
        self._sg_config = config.skill_gen

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def process(self, context: PipelineContext) -> PipelineContext:
        """Transform knowledge units into HermesSkill objects.

        Parameters
        ----------
        context : PipelineContext
            Must have ``context.knowledge_units`` populated.

        Returns
        -------
        PipelineContext
            Context with ``skills`` populated (or appended to existing),
            and each new skill exported as a ``SKILL.md`` file.

        Raises
        ------
        ValueError
            If no knowledge units exist.
        """
        units = context.knowledge_units
        if not units:
            msg = "No knowledge units to generate skills from"
            raise ValueError(msg)

        # Group units by tag-based topic (connected components)
        groups = self._group_by_topic(units)

        provider = self._get_provider()
        model_used = self._resolve_model_used(provider)

        skills: list[HermesSkill] = list(context.skills)  # preserve any pre-existing
        used_names = {s.name for s in skills if s.name}
        method = "llm" if provider is not None else "heuristic"
        markdown_saved = 0

        for group in groups:
            skill: HermesSkill | None = None
            if provider is not None:
                skill = await self._build_skill_with_llm(group, provider)
            if skill is None:
                skill = self._build_skill_heuristic(group)
            if skill is None:
                continue

            skill.model_used = skill.model_used or model_used
            skill.name = self._unique_name(skill.name, used_names)
            used_names.add(skill.name)
            skills.append(skill)

            # Export the skill as a Hermes-compatible SKILL.md file
            try:
                if self.save_skill_markdown(skill) is not None:
                    markdown_saved += 1
            except Exception:
                pass  # markdown export is best-effort

        # Cap total skills if configured
        max_skills = self._sg_config.max_skills_per_book
        if max_skills > 0 and len(skills) > max_skills:
            skills = skills[:max_skills]

        context.skills = skills
        context.stage_results[self.stage.value] = {
            "skills_generated": len(skills),
            "groups_merged": len(groups),
            "total_units_consumed": len(units),
            "method": method,
            "markdown_saved": markdown_saved,
        }

        self.record_metric("skills_generated", len(skills))
        self.record_metric("groups_merged", len(groups))
        return context

    # ------------------------------------------------------------------
    # Topic grouping (connected components over shared tags)
    # ------------------------------------------------------------------

    @staticmethod
    def _group_by_topic(units: list[KnowledgeUnit]) -> list[list[KnowledgeUnit]]:
        """Group knowledge units into connected components by tag overlap.

        Two units belong to the same group when they share at least one
        tag.  Groups are ordered by total confidence (strongest first).
        """
        by_id = {u.id: u for u in units}
        tags_of = {u.id: {t.lower() for t in u.tags} for u in units}

        # Union-find over tag-overlap edges
        parent = {uid: uid for uid in by_id}
        rank = dict.fromkeys(by_id, 0)

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra == rb:
                return
            if rank[ra] < rank[rb]:
                ra, rb = rb, ra
            parent[rb] = ra
            if rank[ra] == rank[rb]:
                rank[ra] += 1

        ids = list(by_id)
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                if tags_of[ids[i]] and tags_of[ids[i]] & tags_of[ids[j]]:
                    union(ids[i], ids[j])

        groups_map: dict[str, list[KnowledgeUnit]] = {}
        for u in units:
            groups_map.setdefault(find(u.id), []).append(u)

        groups = [sorted(group, key=units.index) for group in groups_map.values()]
        groups.sort(key=lambda g: sum(x.confidence for x in g), reverse=True)
        return groups

    # ------------------------------------------------------------------
    # LLM-based skill generation (strict JSON schema)
    # ------------------------------------------------------------------

    def _get_provider(self) -> Any | None:
        """Resolve the configured LLM provider, or ``None`` if unavailable."""
        try:
            from ..llm.provider_factory import get_llm_provider

            return get_llm_provider(self.config)
        except Exception:
            return None

    def _resolve_model_used(self, provider: Any | None) -> str:
        """Return the provider name for ``model_used`` provenance."""
        if provider is not None:
            provider_type = getattr(provider, "provider_type", None)
            if provider_type is not None:
                return str(provider_type.value)
        return self.config.llm.provider

    async def _build_skill_with_llm(
        self,
        units: list[KnowledgeUnit],
        provider: Any,
    ) -> HermesSkill | None:
        """Ask the LLM for name/description/category/tags, then assemble.

        Returns ``None`` when the LLM output is unusable so the caller
        can fall back to the heuristic builder.
        """
        prompt = f"""Design a single AI agent skill (compatible with OpenClaw, Claude, Codex, Hermes, and other AI systems) from the knowledge units below.

KNOWLEDGE UNITS:
{self._format_units_for_prompt(units)}

REQUIREMENTS:
- "name": a short professional skill name (3-6 words, Title Case, no "How to", no quotes, no trailing "Technique"/"Method")
- "description": 2-4 rich, actionable sentences grounded ONLY in the units
- "category": exactly one of: {", ".join(CATEGORIES)}
- "tags": 4-8 specific lowercase tags (not generic words)

Respond with ONLY valid JSON, e.g.:
{{"name": "Audience Research", "description": "...", "category": "marketing", "tags": ["audience", "research"]}}
"""
        data: dict[str, Any] | None = None
        try:
            result = await provider.generate_structured(
                prompt,
                SkillSchema,
                system_prompt=_SYSTEM_PROMPT,
                temperature=0.3,
            )
            if hasattr(result, "model_dump"):
                data = result.model_dump()
            elif isinstance(result, dict):
                data = result
        except Exception:
            # Fallback: explicit-JSON prompt parsed with json.loads
            try:
                resp = await provider.generate(
                    prompt=prompt,
                    system_prompt=_SYSTEM_PROMPT,
                    temperature=0.3,
                    max_tokens=800,
                    model=self.config.llm.model_large,
                )
            except Exception:
                return None
            parsed = self._parse_json_response(resp.content)
            if isinstance(parsed, dict):
                data = parsed

        if not data or not data.get("name"):
            return None

        sections = self._extract_sections(units)

        # Clean professional name -> kebab-case
        name = normalize_skill_name(str(data.get("name", "")))
        if not name:
            name = normalize_skill_name(self._pick_skill_name(units))
        if not name:
            name = slugify(units[0].title) or "generated-skill"

        description = str(data.get("description", "")).strip()
        if len(description) < 20:
            description = self._pick_description(units, sections["best_practices"])

        category = str(data.get("category", "")).strip()
        if category not in CATEGORIES:
            category = self._pick_category(sections["all_tags"])

        # Skill tags: LLM tags first, topped up with unit tags
        llm_tags = self._clean_tags(data.get("tags", []))
        skill_tags = list(dict.fromkeys([*llm_tags, *sorted(sections["all_tags"])]))[:10]

        skill = self._assemble(
            units=units,
            name=name,
            description=description,
            category=category,
            tags=skill_tags,
            sections=sections,
            llm_used=True,
        )
        return skill

    def _build_skill_heuristic(self, units: list[KnowledgeUnit]) -> HermesSkill | None:
        """Assemble a skill without the LLM (fallback path)."""
        if not units:
            return None
        sections = self._extract_sections(units)
        name = normalize_skill_name(self._pick_skill_name(units))
        if not name:
            name = slugify(units[0].title) or "generated-skill"
        description = self._pick_description(units, sections["best_practices"])
        category = self._pick_category(sections["all_tags"])
        tags = list(dict.fromkeys(sorted(sections["all_tags"])))[:10]
        return self._assemble(
            units=units,
            name=name,
            description=description,
            category=category,
            tags=tags,
            sections=sections,
            llm_used=False,
        )

    def _assemble(
        self,
        units: list[KnowledgeUnit],
        name: str,
        description: str,
        category: str,
        tags: list[str],
        sections: dict[str, Any],
        llm_used: bool,
    ) -> HermesSkill:
        """Build the final HermesSkill from sections + metadata."""
        best_practices = sections["best_practices"]
        pitfalls = sections["pitfalls"]
        examples = sections["examples"]
        workflow = sections["workflow"]
        checklist = sections["checklist"]
        references = sections["references"]

        # Fill empty sections from other units whenever possible
        if not best_practices and sections["rules"]:
            best_practices = list(sections["rules"])
        if not best_practices and sections["skill_contents"]:
            best_practices = list(sections["skill_contents"])
        if not workflow:
            if sections["rules"]:
                workflow = [
                    {"title": f"Step {i + 1}", "description": r}
                    for i, r in enumerate(sections["rules"])
                ]
            elif checklist:
                workflow = [
                    {"title": f"Step {i + 1}", "description": c} for i, c in enumerate(checklist)
                ]
            elif len(best_practices) >= 2:
                workflow = [
                    {"title": f"Step {i + 1}", "description": bp}
                    for i, bp in enumerate(best_practices)
                ]
        if not checklist and (sections["rules"] or best_practices):
            checklist = list(sections["rules"]) or list(best_practices)

        # Respect config flags
        if not self._sg_config.include_examples:
            examples = []
        if not self._sg_config.include_best_practices:
            best_practices = []
        if not self._sg_config.include_pitfalls:
            pitfalls = []
        if not self._sg_config.include_workflow:
            workflow = []
        if not self._sg_config.include_checklist:
            checklist = []

        quality = min(self._compute_quality(units) + (0.1 if llm_used else 0.0), 1.0)

        return HermesSkill(
            knowledge_ids=[u.id for u in units],
            book_id=units[0].book_id,
            source_book=units[0].source_book,
            source_chapters=sorted({u.source_reference for u in units if u.source_reference}),
            name=name,
            description=description[:500],
            best_practices=best_practices[:10],
            pitfalls=pitfalls[:10],
            examples=examples[:10],
            workflow=workflow[:10],
            checklist=checklist[:10],
            references=list(dict.fromkeys(references))[:10],
            tags=tags,
            category=category,
            status=SkillStatus.DRAFT,
            quality_score=round(quality, 2),
            model_used="",
        )

    # ------------------------------------------------------------------
    # Section extraction from units
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_sections(units: list[KnowledgeUnit]) -> dict[str, Any]:
        """Partition units into skill sections by unit type."""
        best_practices: list[str] = []
        pitfalls: list[str] = []
        examples: list[dict[str, str]] = []
        workflow: list[dict[str, str]] = []
        checklist: list[str] = []
        references: list[str] = []
        rules: list[str] = []
        skill_contents: list[str] = []
        all_tags: set[str] = set()

        for u in units:
            all_tags.update(u.tags)
            t = u.unit_type
            if t == "best_practice":
                best_practices.append(u.content)
            elif t in ("anti_pattern", "common_mistake"):
                pitfalls.append(f"🚫 {u.title}: {u.content}")
            elif t in ("example", "template"):
                examples.append({"title": u.title, "code": u.content})
            elif t == "workflow":
                workflow.append({"title": u.title, "description": u.content})
            elif t == "checklist":
                checklist.append(u.content)
            elif t == "reference":
                references.append(u.content)
            elif t == "rule":
                rules.append(u.content)
            elif t == "skill":
                skill_contents.append(u.content)

        return {
            "best_practices": best_practices,
            "pitfalls": pitfalls,
            "examples": examples,
            "workflow": workflow,
            "checklist": checklist,
            "references": references,
            "rules": rules,
            "skill_contents": skill_contents,
            "all_tags": all_tags,
        }

    # ------------------------------------------------------------------
    # Naming / description / category helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_units_for_prompt(units: list[KnowledgeUnit], max_units: int = 12) -> str:
        """Render the group's units as a compact numbered prompt block."""
        ordered = sorted(units, key=lambda u: u.confidence, reverse=True)[:max_units]
        lines: list[str] = []
        for i, u in enumerate(ordered, 1):
            content = " ".join(u.content.split())[:300]
            lines.append(f"{i}. [{u.unit_type}] {u.title}\n   {content}")
        return "\n".join(lines)

    @staticmethod
    def _pick_skill_name(units: list[KnowledgeUnit]) -> str:
        """Choose the best raw name for the skill (heuristic fallback)."""
        for u in units:
            if u.unit_type == "skill":
                return normalize_title(u.title)
            if u.unit_type in ("best_practice", "framework"):
                return normalize_title(u.title)
        best = max(units, key=lambda x: x.confidence)
        return normalize_title(best.title)

    @staticmethod
    def _pick_description(units: list[KnowledgeUnit], best_practices: list[str]) -> str:
        """Build a concise description (heuristic fallback)."""
        if best_practices:
            return best_practices[0][:300]
        for u in units:
            if len(u.content) > 30:
                return u.content[:300]
        return f"Skill derived from {len(units)} knowledge units."

    @classmethod
    def _pick_category(cls, tags: set[str]) -> str:
        """Map tags to one of the fixed categories (heuristic fallback)."""
        for tag in tags:
            for keyword, category in _CATEGORY_KEYWORDS.items():
                if keyword in tag:
                    return category
        return "business"

    @staticmethod
    def _clean_tags(raw: Any) -> list[str]:
        """Normalise tags to lowercase kebab tokens, max 10."""
        if isinstance(raw, str):
            raw = [t.strip() for t in re.split(r"[,\s]+", raw) if t.strip()]
        if not isinstance(raw, list):
            return []
        tags: list[str] = []
        for t in raw:
            tag = re.sub(r"[^a-z0-9]+", "-", str(t).strip().lower()).strip("-")
            if tag and len(tag) <= 30 and tag not in tags:
                tags.append(tag)
            if len(tags) >= 10:
                break
        return tags

    @staticmethod
    def _parse_json_response(raw: str) -> Any | None:
        """Best-effort JSON extraction from an LLM response."""
        text = raw.strip()
        if not text:
            return None
        fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if fence:
            text = fence.group(1).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        for start, end in (("{", "}"), ("[", "]")):
            idx = text.find(start)
            if idx == -1:
                continue
            try:
                return json.loads(text[idx : text.rfind(end) + 1])
            except json.JSONDecodeError:
                continue
        # Last resort: some models emit Python-style literals (single quotes)
        import ast

        for start, end in (("{", "}"), ("[", "]")):
            idx = text.find(start)
            if idx == -1:
                continue
            try:
                return ast.literal_eval(text[idx : text.rfind(end) + 1])
            except (ValueError, SyntaxError):
                continue
        return None

    @staticmethod
    def _unique_name(name: str, used: set[str]) -> str:
        """Make the skill name unique within this run."""
        candidate = name
        n = 2
        while candidate in used:
            candidate = f"{name}-{n}"
            n += 1
        return candidate

    @staticmethod
    def _compute_quality(units: list[KnowledgeUnit]) -> float:
        """Heuristic quality score for the assembled skill."""
        if not units:
            return 0.0
        avg_conf = sum(u.confidence for u in units) / len(units)
        diversity = len({u.unit_type for u in units}) / 6.0  # max 6 types
        return round(min((avg_conf * 0.6 + diversity * 0.4), 1.0), 2)

    # ------------------------------------------------------------------
    # SKILL.md export
    # ------------------------------------------------------------------

    def save_skill_markdown(
        self,
        skill: HermesSkill,
        output_dir: str | Path | None = None,
    ) -> Path | None:
        """Export a skill as a Hermes-compatible ``SKILL.md`` file.

        The file is written to ``{output_dir}/{skill.name}.md``; when
        ``output_dir`` is omitted it defaults to
        ``{storage.skills_dir}/markdown/``.

        Parameters
        ----------
        skill : HermesSkill
            The skill to export.
        output_dir : str | Path | None
            Optional target directory override.

        Returns
        -------
        Path | None
            The written file path, or ``None`` when the skill has no name.
        """
        if not skill or not skill.name:
            return None
        base = (
            Path(output_dir)
            if output_dir is not None
            else Path(self.config.storage.skills_dir) / "markdown"
        )
        base.mkdir(parents=True, exist_ok=True)
        path = base / f"{skill.name}.md"
        path.write_text(skill.to_skill_markdown(), encoding="utf-8")
        return path
