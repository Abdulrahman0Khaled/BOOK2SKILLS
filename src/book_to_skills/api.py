"""FastAPI application for the book-to-skills pipeline.

Provides a REST API for running pipelines, querying skills/books,
and monitoring pipeline health.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile

from book_to_skills import __version__
from book_to_skills.config import PipelineConfig
from book_to_skills.pipeline.orchestrator import PipelineOrchestrator

# ---------------------------------------------------------------------------
# App initialisation
# ---------------------------------------------------------------------------

config = PipelineConfig()
orchestrator = PipelineOrchestrator(config)

app = FastAPI(
    title="Book-to-Skills API",
    description="Convert books into high-quality Hermes Skills via a REST API.",
    version=__version__,
)

# In-memory run tracking
_runs: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/api/v1/health")
async def health() -> dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "ok",
        "version": __version__,
        "timestamp": time.time(),
    }


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


@app.post("/api/v1/pipeline/run", status_code=202)
async def run_pipeline(
    file_path: str,
    stages: str | None = None,
    incremental: bool | None = None,
) -> dict[str, Any]:
    """Start a pipeline run on a single book file.

    Args:
        file_path: Path to the book file (PDF or DOCX).
        stages: Optional comma-separated list of stages to run.
        incremental: Whether to enable incremental mode.
    """
    if not Path(file_path).exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    run_id = uuid4().hex[:12]
    stage_list = stages.split(",") if stages else None

    # Launch in background
    _runs[run_id] = {
        "run_id": run_id,
        "file_path": file_path,
        "status": "running",
        "stages": stage_list or config.stages_enabled,
        "incremental": incremental if incremental is not None else config.incremental_mode,
        "started_at": time.time(),
        "completed_at": None,
        "error": None,
        "skills_count": 0,
    }

    _task = asyncio.create_task(_execute_pipeline(run_id, file_path, stage_list, incremental))
    _runs[run_id]["_task"] = _task

    return {
        "run_id": run_id,
        "status": "accepted",
        "location": f"/api/v1/pipeline/status/{run_id}",
    }


async def _execute_pipeline(
    run_id: str,
    file_path: str,
    stages: list[str] | None,
    incremental: bool | None,
) -> None:
    """Background task that runs the pipeline and updates the run record."""
    try:
        ctx = await orchestrator.run_pipeline(
            file_path=file_path,
            stages=stages,
            incremental=incremental,
        )
        _runs[run_id].update({
            "status": "completed" if not ctx.errors else "completed_with_errors",
            "completed_at": time.time(),
            "duration_s": ctx.total_duration_s,
            "skills_count": len(ctx.skills),
            "errors": [e["message"] for e in ctx.errors],
            "skills": [s.model_dump(mode="json") for s in ctx.skills],
        })
    except Exception as exc:
        _runs[run_id].update({
            "status": "failed",
            "completed_at": time.time(),
            "error": str(exc),
        })


# ---------------------------------------------------------------------------
# Pipeline status
# ---------------------------------------------------------------------------


@app.get("/api/v1/pipeline/status/{run_id}")
async def pipeline_status(run_id: str) -> dict[str, Any]:
    """Get the status of a pipeline run."""
    run = _runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return run


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------


@app.get("/api/v1/skills")
async def list_skills(
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """List all generated skills with optional pagination and status filter."""
    skills = await orchestrator.list_skills()

    if status:
        skills = [s for s in skills if s.status.value == status]

    skills.sort(key=lambda s: s.created_at, reverse=True)
    sliced = skills[offset : offset + limit]

    return [s.model_dump(mode="json") for s in sliced]


@app.get("/api/v1/skills/{skill_id}")
async def get_skill(skill_id: str) -> dict[str, Any]:
    """Get a single skill by its ID."""
    skills = await orchestrator.list_skills()
    for s in skills:
        if s.id == skill_id:
            return s.model_dump(mode="json")
    raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")


@app.get("/api/v1/search")
async def search_skills(
    q: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Keyword search over generated skills (name, tags, content).

    Args:
        q: Space-separated search keywords (all terms must match).
        limit: Maximum number of results to return.

    Returns:
        List of matching skills (JSON) ranked by relevance.
    """
    if not q or not q.strip():
        raise HTTPException(status_code=422, detail="Query parameter 'q' is required")
    skills = await orchestrator.search_skills(q, limit=limit)
    return [s.model_dump(mode="json") for s in skills]


@app.get("/api/v1/stats")
async def stats() -> dict[str, Any]:
    """Aggregate statistics over the skills store.

    Returns:
        Total skill count, distinct source books, per-category and
        per-status breakdowns, and the average quality score.
    """
    skills = await orchestrator.list_skills(limit=100_000)

    categories: dict[str, int] = {}
    statuses: dict[str, int] = {}
    sources: set[str] = set()
    score_sum = 0.0

    for s in skills:
        cat = s.category or "uncategorized"
        categories[cat] = categories.get(cat, 0) + 1
        statuses[s.status.value] = statuses.get(s.status.value, 0) + 1
        if s.source_book:
            sources.add(s.source_book)
        elif s.book_id:
            sources.add(s.book_id)
        score_sum += s.quality_score

    return {
        "total_skills": len(skills),
        "total_books": len(sources),
        "categories": dict(sorted(categories.items(), key=lambda kv: kv[1], reverse=True)),
        "statuses": dict(sorted(statuses.items(), key=lambda kv: kv[1], reverse=True)),
        "approved_count": statuses.get("approved", 0),
        "reviewed_count": statuses.get("reviewed", 0),
        "rejected_count": statuses.get("rejected", 0),
        "draft_count": statuses.get("draft", 0),
        "published_count": statuses.get("published", 0),
        "avg_quality_score": round(score_sum / len(skills), 2) if skills else 0.0,
    }


@app.delete("/api/v1/skills/{skill_id}")
async def delete_skill(skill_id: str) -> dict[str, str]:
    """Delete a skill by its ID."""
    deleted = orchestrator.store.delete_skill(skill_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")
    return {"status": "deleted", "skill_id": skill_id}


# ---------------------------------------------------------------------------
# Books
# ---------------------------------------------------------------------------


@app.get("/api/v1/books")
async def list_books() -> list[dict[str, Any]]:
    """List all available book files in the data directory."""
    return orchestrator.list_books()


@app.post("/api/v1/books/upload", status_code=201)
async def upload_book(file: UploadFile = File()) -> dict[str, Any]:  # ruff: ignore[function-call-in-default-argument]
    """Upload a book file (PDF or DOCX) to the books directory."""
    supported = {".pdf", ".docx", ".doc"}
    ext = Path(file.filename or "").suffix.lower()
    if ext not in supported:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{ext}'. Supported: {supported}",
        )

    books_dir = Path(config.data_dir) / "books"
    books_dir.mkdir(parents=True, exist_ok=True)

    dest = books_dir / (file.filename or f"upload_{uuid4().hex[:8]}{ext}")

    content = await file.read()
    dest.write_bytes(content)

    from book_to_skills.utils.hash_utils import compute_file_hash

    return {
        "status": "uploaded",
        "file_path": str(dest),
        "file_name": dest.name,
        "size_bytes": len(content),
        "hash": compute_file_hash(str(dest)),
    }


# ---------------------------------------------------------------------------
# Run the app
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "book_to_skills.api:app",
        host="0.0.0.0",
        port=8000,
        reload=config.debug,
    )
