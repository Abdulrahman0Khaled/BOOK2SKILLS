"""ReviewStage — smart review and classification of generated HermesSkills.

Each skill is reviewed against five quality criteria:

- Description clarity (concise, actionable, substantive)
- Presence of concrete examples
- Presence of a structured workflow
- Presence of pitfalls / anti-patterns
- Fit of tags and category

The stage first attempts an **LLM review**: a lazy-loaded provider is
asked to return a JSON verdict ``{"quality_score": 1-10, "feedback": str,
"notes": [str]}``. If no provider is configured/available or the call
fails, a deterministic **heuristic** scores the skill instead:

    description > 50 chars      +3.0
    best_practices present      +2.0
    workflow present            +2.0
    pitfalls present            +1.5
    examples present            +1.5
                                ------
    maximum                    10.0

The resulting score (0-10 scale) drives the status:

- ``>= 7``   → ``APPROVED``
- ``4 - 6.9``→ ``REVIEWED``
- ``< 4``    → ``REJECTED``

``review_feedback`` and ``review_notes`` are populated on each skill,
and results are stored in ``context.stage_results["review"]``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from ..config import PipelineConfig
from ..domain.enums import LLMProvider, PipelineStage, SkillStatus
from ..domain.models import HermesSkill, PipelineContext
from .base import BaseStage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scoring constants (0-10 scale)
# ---------------------------------------------------------------------------

APPROVED_THRESHOLD = 7.0
REJECTED_THRESHOLD = 4.0

_DESCRIPTION_MIN_CHARS = 50
_DESCRIPTION_WEIGHT = 3.0
_BEST_PRACTICES_WEIGHT = 2.0
_WORKFLOW_WEIGHT = 2.0
_PITFALLS_WEIGHT = 1.5
_EXAMPLES_WEIGHT = 1.5

_REVIEW_SYSTEM_PROMPT = (
    "You are a meticulous reviewer for a skills marketplace. "
    "Evaluate each skill strictly and constructively. "
    "Always respond with valid JSON only."
)


class ReviewResult(BaseModel):
    """Structured LLM verdict for a single skill."""

    quality_score: int = Field(
        ge=0,
        le=10,
        description="Overall quality score from 1 (poor) to 10 (excellent); 0 only for empty skills.",
    )
    feedback: str = Field(
        default="", description="Short, actionable feedback for improving the skill."
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Bullet notes on strengths/weaknesses per criterion.",
    )


class ReviewStage(BaseStage):
    """Pipeline stage that reviews and classifies generated skills.

    Uses an LLM review when available (lazy-loaded), falling back to a
    deterministic heuristic. Populates ``review_feedback``,
    ``review_notes``, ``quality_score`` (0-10) and ``status``
    (``APPROVED`` / ``REVIEWED`` / ``REJECTED``) on each skill.

    Example::

        stage = ReviewStage(config)
        context = await stage.execute(context)
        assert context.skills[0].status in (
            SkillStatus.APPROVED, SkillStatus.REVIEWED, SkillStatus.REJECTED
        )
    """

    def __init__(self, config: PipelineConfig) -> None:
        super().__init__(config)
        self.stage = PipelineStage.REVIEW
        self._llm: Any | None = None
        self._llm_attempted = False

    async def process(self, context: PipelineContext) -> PipelineContext:
        """Review all skills in the context.

        Parameters
        ----------
        context : PipelineContext
            Must have ``context.skills`` populated.

        Returns
        -------
        PipelineContext
            Context with each skill reviewed and status set.

        Raises
        ------
        ValueError
            If no skills exist.
        """
        if not context.skills:
            msg = "No skills to review"
            raise ValueError(msg)

        reviews: list[dict[str, Any]] = []
        llm_reviewed = 0
        heuristic_reviewed = 0

        for skill in context.skills:
            result, used_llm = await self._review_skill(skill)
            if used_llm:
                llm_reviewed += 1
            else:
                heuristic_reviewed += 1
            self._apply_result(skill, result)

            reviews.append({
                "skill_id": skill.id,
                "name": skill.name,
                "status": skill.status.value,
                "quality_score": skill.quality_score,
                "review_method": "llm" if used_llm else "heuristic",
                "feedback": skill.review_feedback,
                "notes": skill.review_notes,
            })

        context.stage_results[self.stage.value] = {
            "total_reviewed": len(context.skills),
            "approved": sum(1 for r in reviews if r["status"] == SkillStatus.APPROVED.value),
            "reviewed": sum(1 for r in reviews if r["status"] == SkillStatus.REVIEWED.value),
            "rejected": sum(1 for r in reviews if r["status"] == SkillStatus.REJECTED.value),
            "llm_reviewed": llm_reviewed,
            "heuristic_reviewed": heuristic_reviewed,
            "reviews": reviews,
        }

        self.record_metric("total_reviewed", len(context.skills))
        self.record_metric(
            "approved", sum(1 for r in reviews if r["status"] == SkillStatus.APPROVED.value)
        )
        self.record_metric("llm_reviewed", llm_reviewed)
        return context

    # ------------------------------------------------------------------
    # Review logic
    # ------------------------------------------------------------------

    async def _review_skill(self, skill: HermesSkill) -> tuple[ReviewResult, bool]:
        """Review a single skill, preferring the LLM with heuristic fallback.

        Returns a ``(result, used_llm)`` tuple.
        """
        llm = self._get_llm()
        if llm is not None:
            try:
                result = await self._review_with_llm(llm, skill)
                if result is not None:
                    return result, True
            except Exception as exc:
                logger.warning("LLM review failed for skill '%s': %s", skill.name, exc)

        return self._heuristic_review(skill), False

    def _get_llm(self) -> Any | None:
        """Lazily resolve the configured LLM provider.

        Returns ``None`` (and never raises) when the provider SDK is
        missing, no API key is configured for a key-based provider, or
        the provider fails to initialise. The provider is resolved at
        most once per stage run.
        """
        if self._llm_attempted:
            return self._llm
        self._llm_attempted = True

        provider_name = self.config.llm.provider
        try:
            provider_enum = LLMProvider(provider_name.lower())
        except ValueError:
            provider_enum = None

        # Key-based providers without an API key would only fail at call
        # time — skip the attempt entirely and use the heuristic.
        if provider_enum is not None and provider_enum.requires_api_key:
            if not self.config.llm.api_key:
                return None

        try:
            # Lazy import: the provider module / SDK is only loaded here,
            # so missing SDKs degrade gracefully to heuristics.
            from ..llm.provider_factory import get_llm_provider

            self._llm = get_llm_provider(self.config)
        except Exception as exc:
            logger.warning("LLM provider unavailable (%s) — using heuristic review", exc)
            self._llm = None
        return self._llm

    async def _review_with_llm(self, llm: Any, skill: HermesSkill) -> ReviewResult | None:
        """Ask the LLM for a structured JSON review of one skill."""
        prompt = self._build_review_prompt(skill)
        try:
            raw = await llm.generate_structured(
                prompt=prompt,
                output_schema=ReviewResult,
                system_prompt=_REVIEW_SYSTEM_PROMPT,
                temperature=0.2,
            )
        except Exception as exc:
            logger.warning("LLM generate_structured failed: %s", exc)
            return None

        if not isinstance(raw, ReviewResult):
            return None
        # Normalise int score into the float 0-10 scale used by the stage.
        return ReviewResult(
            quality_score=raw.quality_score,
            feedback=raw.feedback or "",
            notes=raw.notes or [],
        )

    @staticmethod
    def _build_review_prompt(skill: HermesSkill) -> str:
        """Build the LLM prompt describing the skill and the criteria."""
        payload = {
            "name": skill.name,
            "description": skill.description,
            "best_practices": skill.best_practices,
            "workflow": skill.workflow,
            "pitfalls": skill.pitfalls,
            "examples": skill.examples,
            "checklist": skill.checklist,
            "tags": skill.tags,
            "category": skill.category,
        }
        criteria = (
            "Evaluate the skill on these criteria:\n"
            "1. Description clarity: concise, actionable, substantive (> 50 chars).\n"
            "2. Examples: concrete and useful.\n"
            "3. Workflow: clear, ordered steps.\n"
            "4. Pitfalls: practical warnings / anti-patterns.\n"
            "5. Tags & category: relevant and fitting.\n\n"
            'Respond with valid JSON: {"quality_score": 1-10, "feedback": str, '
            '"notes": [str]}'
        )
        return (
            f"Review this generated AI Agent Skill (compatible with OpenClaw, Claude, Codex, Hermes, etc.):\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n{criteria}"
        )

    def _heuristic_review(self, skill: HermesSkill) -> ReviewResult:
        """Deterministic quality scoring used when no LLM is available."""
        if not skill.name.strip():
            return ReviewResult(
                quality_score=0,
                feedback="Skill name is empty; cannot be approved.",
                notes=["name is empty"],
            )

        score = 0.0
        notes: list[str] = []

        if len(skill.description.strip()) > _DESCRIPTION_MIN_CHARS:
            score += _DESCRIPTION_WEIGHT
        else:
            notes.append(f"description is too short (<= {_DESCRIPTION_MIN_CHARS} chars)")

        if skill.best_practices:
            score += _BEST_PRACTICES_WEIGHT
        else:
            notes.append("no best practices")

        if skill.workflow:
            score += _WORKFLOW_WEIGHT
        else:
            notes.append("no workflow")

        if skill.pitfalls:
            score += _PITFALLS_WEIGHT
        else:
            notes.append("no pitfalls")

        if skill.examples:
            score += _EXAMPLES_WEIGHT
        else:
            notes.append("no examples")

        if not skill.tags or not skill.category:
            notes.append("tags/category missing or sparse")

        if not notes:
            notes.append(
                "all criteria met: description, examples, workflow, pitfalls, tags/category"
            )

        score = round(min(max(score, 0.0), 10.0), 1)

        if score >= APPROVED_THRESHOLD:
            feedback = "Skill is well-structured and ready for approval."
        elif score >= REJECTED_THRESHOLD:
            feedback = "Skill is acceptable but needs improvements before approval."
        else:
            feedback = "Skill lacks essential sections; needs rework or rejection."

        return ReviewResult(
            quality_score=int(score),
            feedback=feedback,
            notes=notes,
        )

    def _apply_result(self, skill: HermesSkill, result: ReviewResult) -> None:
        """Write the review verdict onto the skill and derive its status."""
        skill.quality_score = round(min(max(float(result.quality_score), 0.0), 10.0), 1)
        skill.review_feedback = result.feedback or ""
        skill.review_notes = list(result.notes or [])
        skill.status = self.status_for_score(skill.quality_score)

    @staticmethod
    def status_for_score(score: float) -> SkillStatus:
        """Map a 0-10 quality score to a skill status.

        ``>= 7`` → ``APPROVED``; ``4 - 6.9`` → ``REVIEWED``; ``< 4`` → ``REJECTED``.
        """
        if score >= APPROVED_THRESHOLD:
            return SkillStatus.APPROVED
        if score >= REJECTED_THRESHOLD:
            return SkillStatus.REVIEWED
        return SkillStatus.REJECTED
