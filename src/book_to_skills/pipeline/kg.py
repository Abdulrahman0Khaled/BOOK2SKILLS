"""KnowledgeGraphStage — build a semantic knowledge graph over skills.

Builds a ``KnowledgeGraph`` from a list of skills. The primary signal
for edges is **embedding cosine similarity** (semantic): two skills
with similarity >= 0.7 are linked with a ``related_to`` edge. When
embeddings are unavailable, lexical heuristics (tag overlap, name
similarity via difflib, shared knowledge ids, category match) take over
so the graph still gets built.

Edge types:

- ``related_to`` — semantic similarity >= 0.7 (fallback: tag overlap
  >= 0.4, name similarity >= 0.6, knowledge-id overlap > 0.3, or equal
  category).
- ``extends`` — one skill's name contains the other's (e.g.
  ``Email-Newsletter-Automation`` **extends** ``Email-Basics``). The
  edge points from the specialised skill to its base.
- ``prerequisite`` — one skill's name carries prerequisite keywords
  (``basics``, ``intro``, ``foundation``, ``beginner``, ``prerequisite``,
  ...). The edge points from the prerequisite to the dependent skill.

The reusable entry point is :func:`build_kg_from_skills` — a pure
function that takes skills and returns a ``KnowledgeGraph``.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Callable

from ..config import PipelineConfig
from ..domain.enums import PipelineStage
from ..domain.models import HermesSkill, KnowledgeGraph, PipelineContext
from .base import BaseStage
from .embeddings import cosine_similarity, hash_embed_text, skill_to_text

# Semantic similarity threshold for a "related_to" edge
_SEMANTIC_RELATED_THRESHOLD = 0.7
# Lexical fallback thresholds (kept from the original heuristic stage)
_TAG_OVERLAP_THRESHOLD = 0.4
_NAME_SIM_THRESHOLD = 0.6
_KNOWLEDGE_OVERLAP_THRESHOLD = 0.3
# Minimum length of a name for an "extends" containment match
_MIN_NAME_CONTAIN = 4
# Keywords that mark a skill as a prerequisite
_PREQUISITE_KEYWORDS = [
    "before",
    "prerequisite",
    "pre-requisite",
    "prereq",
    "prep",
    "first",
    "foundation",
    "intro",
    "introduction",
    "beginner",
    "basics",
    "basic",
    "getting started",
    "crash course",
    "101",
    "fundamentals",
]

SimilarityFn = Callable[[HermesSkill, HermesSkill], float | None]


def build_kg_from_skills(skills: list[HermesSkill], dim: int = 384) -> KnowledgeGraph:
    """Build a :class:`KnowledgeGraph` from a list of skills.

    Reusable, side-effect-free entry point — usable from the pipeline
    stage, API handlers, or tests.

    Parameters
    ----------
    skills : list[HermesSkill]
        Skills to build the graph from.
    dim : int
        Dimensionality used for fallback hash embeddings (when a skill
        has no ``embedding`` set).

    Returns
    -------
    KnowledgeGraph
        Graph with one node per skill and typed, weighted edges.

    Example::

        graph = build_kg_from_skills(skills)
        assert len(graph.nodes) == len(skills)
    """
    graph = KnowledgeGraph()
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_edges: set[tuple[str, str, str]] = set()

    emb_cache: dict[str, list[float]] = {}

    def embedding_for(skill: HermesSkill) -> list[float] | None:
        """Return the skill's embedding (cached fallback computation)."""
        if skill.embedding:
            return skill.embedding
        if skill.id not in emb_cache:
            emb_cache[skill.id] = hash_embed_text(skill_to_text(skill), dim)
        return emb_cache[skill.id]

    def semantic_sim(a: HermesSkill, b: HermesSkill) -> float | None:
        """Cosine similarity between two skills, or None if impossible."""
        emb_a, emb_b = embedding_for(a), embedding_for(b)
        if emb_a is None or emb_b is None:
            return None
        try:
            return cosine_similarity(emb_a, emb_b)
        except Exception:
            return None

    for skill in skills:
        nodes.append({
            "id": skill.id,
            "name": skill.name,
            "category": skill.category,
            "tags": skill.tags,
            "quality_score": skill.quality_score,
            "knowledge_ids": skill.knowledge_ids,
            "description": skill.description[:200],
        })

    # ── Build edges ─────────────────────────────────────────────────
    for i, a in enumerate(skills):
        for j, b in enumerate(skills):
            if j <= i:
                continue

            rels = _determine_relationships(a, b, semantic_sim)
            for rel_type, weight, source_side in rels:
                src, tgt = (a, b) if source_side == "a" else (b, a)
                edge_key = (src.id, tgt.id, rel_type)
                if edge_key in seen_edges:
                    continue
                seen_edges.add(edge_key)
                edges.append({
                    "source": src.id,
                    "target": tgt.id,
                    "type": rel_type,
                    "source_name": src.name,
                    "target_name": tgt.name,
                    "weight": weight,
                })

    graph.nodes = nodes
    graph.edges = edges
    return graph


def _determine_relationships(
    a: HermesSkill, b: HermesSkill, semantic_sim: SimilarityFn
) -> list[tuple[str, float, str]]:
    """Return ``(edge_type, weight, source_side)`` for the a/b pair.

    ``source_side`` is ``"a"`` or ``"b"`` and determines the edge
    direction: for ``extends`` the specialised skill is the source and
    its base the target; for ``prerequisite`` the prerequisite skill is
    the source and the dependent skill the target. ``related_to`` is
    undirected (always ``"a"``).
    """
    relationships: list[tuple[str, float, str]] = []

    # ── 1. Semantic similarity → related_to (primary signal) ────────
    sem = semantic_sim(a, b)
    if sem is not None and sem >= _SEMANTIC_RELATED_THRESHOLD:
        relationships.append(("related_to", round(sem, 3), "a"))

    # ── 2. Lexical fallbacks → related_to (only if not already linked) ──
    if not any(t == "related_to" for t, _, _ in relationships):
        tag_overlap = _tag_overlap(a.tags, b.tags)
        if tag_overlap >= _TAG_OVERLAP_THRESHOLD:
            relationships.append(("related_to", round(tag_overlap, 3), "a"))
        else:
            name_sim = difflib.SequenceMatcher(None, a.name.lower(), b.name.lower()).ratio()
            if name_sim >= _NAME_SIM_THRESHOLD:
                relationships.append(("related_to", round(name_sim, 3), "a"))
            elif _knowledge_overlap(a, b) > _KNOWLEDGE_OVERLAP_THRESHOLD:
                relationships.append(("related_to", 0.5, "a"))
            elif a.category and a.category == b.category:
                relationships.append(("related_to", 0.4, "a"))

    # ── 3. Name containment → extends ───────────────────────────────
    # b's name contains a's name → b is a specialisation of a:
    #   source=b (specialised), target=a (base)
    norm_a = _normalise_name(a.name)
    norm_b = _normalise_name(b.name)
    if norm_a and norm_b and len(norm_a) >= _MIN_NAME_CONTAIN and norm_a in norm_b:
        weight = round(len(norm_a) / len(norm_b), 3)
        relationships.append(("extends", weight, "b"))
    elif norm_a and norm_b and len(norm_b) >= _MIN_NAME_CONTAIN and norm_b in norm_a:
        # a's name contains b's name → a is a specialisation of b
        weight = round(len(norm_b) / len(norm_a), 3)
        relationships.append(("extends", weight, "a"))

    # ── 4. Prerequisite keywords → prerequisite (directed) ──────────
    a_is_prereq = _has_prerequisite_keywords(a.name)
    b_is_prereq = _has_prerequisite_keywords(b.name)
    if a_is_prereq and not b_is_prereq:
        # a is the prerequisite of b: source=a, target=b
        relationships.append(("prerequisite", 1.0, "a"))
    elif b_is_prereq and not a_is_prereq:
        # b is the prerequisite of a: source=b, target=a
        relationships.append(("prerequisite", 1.0, "b"))

    return relationships


def _normalise_name(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    norm = re.sub(r"[^a-zA-Z0-9\s]", "", name).lower().strip()
    return re.sub(r"\s+", " ", norm)


def _has_prerequisite_keywords(name: str) -> bool:
    """True when the name carries prerequisite-indicating keywords."""
    norm = _normalise_name(name)
    return any(kw in norm for kw in _PREQUISITE_KEYWORDS)


def _tag_overlap(tags_a: list[str], tags_b: list[str]) -> float:
    """Jaccard index of tag sets."""
    set_a = set(tags_a)
    set_b = set(tags_b)
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _knowledge_overlap(a: HermesSkill, b: HermesSkill) -> float:
    """Fraction of shared knowledge unit ids."""
    ids_a = set(a.knowledge_ids or [])
    ids_b = set(b.knowledge_ids or [])
    if not ids_a or not ids_b:
        return 0.0
    return len(ids_a & ids_b) / len(ids_a | ids_b)


class KnowledgeGraphStage(BaseStage):
    """Pipeline stage that builds a ``KnowledgeGraph`` from skills.

    Wraps :func:`build_kg_from_skills`; the resulting graph is stored
    in ``context.stage_results["knowledge_graph"]["graph"]`` and on
    ``context.knowledge_graph``.

    Example::

        stage = KnowledgeGraphStage(config)
        context = await stage.execute(context)
        graph = context.stage_results["knowledge_graph"]["graph"]
        assert len(graph.nodes) == len(context.skills)
    """

    def __init__(self, config: PipelineConfig) -> None:
        super().__init__(config)
        self.stage = PipelineStage.KNOWLEDGE_GRAPH
        self._dim = config.vector_db.embedding_dim or 384

    async def process(self, context: PipelineContext) -> PipelineContext:
        """Build a knowledge graph from the skills in the context.

        Parameters
        ----------
        context : PipelineContext
            Must have ``context.skills`` populated.

        Returns
        -------
        PipelineContext
            Context with a ``KnowledgeGraph`` in stage results.
        """
        graph = build_kg_from_skills(context.skills, dim=self._dim)

        context.stage_results[self.stage.value] = {
            "nodes": len(graph.nodes),
            "edges": len(graph.edges),
            "graph": graph,
        }
        context.knowledge_graph = graph

        self.record_metric("nodes", len(graph.nodes))
        self.record_metric("edges", len(graph.edges))
        return context

    # ------------------------------------------------------------------
    # Backward-compatible helpers (delegate to module functions)
    # ------------------------------------------------------------------

    @staticmethod
    def _tag_overlap(tags_a: list[str], tags_b: list[str]) -> float:
        """Jaccard index of tag sets."""
        return _tag_overlap(tags_a, tags_b)

    @staticmethod
    def _knowledge_overlap(a: HermesSkill, b: HermesSkill) -> float:
        """Fraction of shared knowledge unit ids."""
        return _knowledge_overlap(a, b)
