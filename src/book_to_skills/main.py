"""CLI entrypoint for book-to-skills using Typer.

Usage:
    book2skills run pipeline <file_path> [OPTIONS]
    book2skills run all [OPTIONS]
    book2skills run stage <stage_name> <file_path>
    book2skills list books
    book2skills list skills
    book2skills search "query" [OPTIONS]
    book2skills export md [OPTIONS]
    book2skills show config
    book2skills clear cache
    book2skills version
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Annotated

import typer

from book_to_skills import __version__
from book_to_skills.config import PipelineConfig
from book_to_skills.pipeline.orchestrator import PipelineOrchestrator

app = typer.Typer(
    name="book2skills",
    help="Convert books into high-quality Hermes Skills.",
    no_args_is_help=True,
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _get_orchestrator(config_path: str | None = None) -> PipelineOrchestrator:
    """Build a PipelineOrchestrator, optionally loading a specific config."""
    cfg = PipelineConfig()
    if config_path:
        from book_to_skills.utils.file_utils import read_yaml

        overrides = read_yaml(config_path)
        if isinstance(overrides, dict):
            for key, val in overrides.items():
                if hasattr(cfg, key):
                    setattr(cfg, key, val)
    return PipelineOrchestrator(cfg)


def _run_async(coro):
    """Run an async coroutine from a sync CLI context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor() as pool:
        return pool.submit(asyncio.run, coro).result()


# ---------------------------------------------------------------------------
# Run sub-command group
# ---------------------------------------------------------------------------


run_app = typer.Typer(help="Run pipeline stages.")
app.add_typer(run_app, name="run")


@run_app.command("pipeline")
def run_pipeline(
    file_path: str = typer.Argument(..., help="Path to the book file"),
    stages: Annotated[
        str | None,
        typer.Option(help="Comma-separated list of stages (e.g. extract,clean,chunk)"),
    ] = None,
    incremental: Annotated[
        bool | None,
        typer.Option("--incremental/--full", help="Enable incremental mode"),
    ] = None,
    config: Annotated[
        str | None,
        typer.Option("--config", "-c", help="Path to YAML config file"),
    ] = None,
) -> None:
    """Run the full pipeline on a single book file."""
    if not Path(file_path).exists():
        typer.secho(f"File not found: {file_path}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    stage_list = stages.split(",") if stages else None
    orch = _get_orchestrator(config)
    ctx = _run_async(orch.run_pipeline(file_path, stages=stage_list, incremental=incremental))
    _print_pipeline_result(ctx)


@run_app.command("all")
def run_all(
    stages: Annotated[
        str | None,
        typer.Option(help="Comma-separated list of stages (e.g. extract,clean,chunk)"),
    ] = None,
    incremental: Annotated[
        bool | None,
        typer.Option("--incremental/--full", help="Enable incremental mode"),
    ] = None,
    config: Annotated[
        str | None,
        typer.Option("--config", "-c", help="Path to YAML config file"),
    ] = None,
) -> None:
    """Run the pipeline on all books in the data directory."""
    stage_list = stages.split(",") if stages else None
    orch = _get_orchestrator(config)
    results = _run_async(orch.run_all(stages=stage_list, incremental=incremental))

    typer.echo(f"\nProcessed {len(results)} book(s):\n")
    for r in results:
        status = typer.colors.GREEN if not r.errors else typer.colors.RED
        label = "OK" if not r.errors else f"{len(r.errors)} error(s)"
        typer.secho(
            f"  [{label}] {r.book.file_path if r.book else '?'} — {r.total_duration_s:.1f}s",
            fg=status,
        )


@run_app.command("stage")
def run_stage(
    stage_name: str = typer.Argument(..., help="Stage name to run"),
    file_path: str = typer.Argument(..., help="Path to the book file"),
    config: Annotated[
        str | None,
        typer.Option("--config", "-c", help="Path to YAML config file"),
    ] = None,
) -> None:
    """Run a single pipeline stage on a book file."""
    if not Path(file_path).exists():
        typer.secho(f"File not found: {file_path}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    orch = _get_orchestrator(config)
    result = _run_async(orch.run_stage(stage_name, file_path))

    status = typer.colors.GREEN if result.success else typer.colors.RED
    typer.secho(
        f"\nStage: {result.stage.value}"
        f"\n  Status:     {'✓ success' if result.success else '✗ failed'}"
        f"\n  Duration:   {result.duration_s:.2f}s"
        f"\n  Error:      {result.error or '—'}"
        f"\n  Context ID: {result.context_id}",
        fg=status,
    )


# ---------------------------------------------------------------------------
# List sub-command group
# ---------------------------------------------------------------------------

list_app = typer.Typer(help="List books or skills.")
app.add_typer(list_app, name="list")


@list_app.command("books")
def list_books_cmd() -> None:
    """List all book files in the data directory."""
    orch = _get_orchestrator()
    books = orch.list_books()

    if not books:
        typer.echo("No book files found in the data directory.")
        return

    typer.echo(f"\n{'File':<50} {'Format':<8} {'Size':<10} {'Hash':<20}")
    typer.echo("-" * 88)
    for b in books:
        typer.echo(
            f"{b['file_name']:<50} {b['format']:<8} {b['size_mb']:<10.2f}MB {b['hash'][:20]:<20}"
        )
    typer.echo(f"\nTotal: {len(books)} book(s)")


@list_app.command("skills")
def list_skills_cmd() -> None:
    """List all generated skills."""
    orch = _get_orchestrator()
    skills = _run_async(orch.list_skills())

    if not skills:
        typer.echo("No skills found. Run a pipeline first.")
        return

    typer.echo(f"\n{'Name':<40} {'Category':<20} {'Status':<12} {'ID':<16}")
    typer.echo("-" * 88)
    for s in skills:
        typer.echo(f"{s.name:<40} {s.category or '—':<20} {s.status.value:<12} {s.id:<16}")
    typer.echo(f"\nTotal: {len(skills)} skill(s)")


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


@app.command()
def studio() -> None:
    """Launch the interactive Book-to-Skills Studio (menu-driven UI)."""
    from .tui import studio as run_studio

    run_studio()


@app.command()
def version() -> None:
    """Show the installed version."""
    typer.echo(f"book-to-skills v{__version__}")


# ---------------------------------------------------------------------------
# show config
# ---------------------------------------------------------------------------


@app.command()
def show(
    config: Annotated[
        str | None,
        typer.Option("--config", "-c", help="Path to YAML config file"),
    ] = None,
) -> None:
    """Show the current pipeline configuration."""
    cfg = _get_orchestrator(config).config
    from rich.console import Console
    from rich.table import Table

    console = Console()

    table = Table(title="Pipeline Configuration", title_style="bold")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="white")

    for section in [
        ("project_name", cfg.project_name),
        ("version", cfg.version),
        ("debug", cfg.debug),
        ("data_dir", cfg.data_dir),
        ("max_workers", cfg.max_workers),
        ("stages_enabled", ", ".join(cfg.stages_enabled)),
        ("run_parallel_stages", cfg.run_parallel_stages),
        ("incremental_mode", cfg.incremental_mode),
        ("skip_on_error", cfg.skip_on_error),
        ("llm.provider", cfg.llm.provider),
        ("llm.model_small", cfg.llm.model_small),
        ("llm.model_large", cfg.llm.model_large),
        ("cache.backend", cfg.cache.backend),
        ("cache.cache_dir", cfg.cache.cache_dir),
        ("storage.skills_dir", cfg.storage.skills_dir),
        ("storage.format", cfg.storage.format),
        ("extractor.pdf_extraction_mode", cfg.extractor.pdf_extraction_mode),
        ("chunk.strategy", cfg.chunk.strategy),
        ("queue.max_concurrent_jobs", cfg.queue.max_concurrent_jobs),
        ("monitoring.log_level", cfg.monitoring.log_level),
    ]:
        table.add_row(str(section[0]), str(section[1]))

    console.print(table)


# ---------------------------------------------------------------------------
# clear cache
# ---------------------------------------------------------------------------


@app.command()
def clear(
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """Clear all cached pipeline results."""
    if not yes:
        typer.confirm("Clear all cached pipeline results?", abort=True)

    orch = _get_orchestrator()
    _run_async(orch.clear_cache())
    typer.secho("Cache cleared successfully.", fg=typer.colors.GREEN)


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


@app.command()
def search(
    query: str = typer.Argument(..., help="Space-separated search keywords"),
    limit: Annotated[
        int | None,
        typer.Option("--limit", "-n", help="Maximum number of results"),
    ] = 20,
    config: Annotated[
        str | None,
        typer.Option("--config", "-c", help="Path to YAML config file"),
    ] = None,
) -> None:
    """Search generated skills by keywords (name, tags, content)."""
    orch = _get_orchestrator(config)
    skills = _run_async(orch.search_skills(query, limit=limit or 20))

    if not skills:
        typer.secho(f"No skills match '{query}'.", fg=typer.colors.YELLOW)
        return

    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(title=f"Search results for '{query}' ({len(skills)})")
    table.add_column("Name", style="cyan")
    table.add_column("Category")
    table.add_column("Status")
    table.add_column("Score")
    table.add_column("Source")

    for s in skills:
        table.add_row(
            s.name,
            s.category or "—",
            s.status.value,
            f"{s.quality_score:.1f}",
            s.source_book or s.book_id or "—",
        )
    console.print(table)


# ---------------------------------------------------------------------------
# export md
# ---------------------------------------------------------------------------

export_app = typer.Typer(help="Export generated skills to files.")
app.add_typer(export_app, name="export")


@export_app.command("md")
def export_md(
    out_dir: Annotated[
        str | None,
        typer.Option("--out", "-o", help="Output directory for SKILL.md files"),
    ] = None,
    config: Annotated[
        str | None,
        typer.Option("--config", "-c", help="Path to YAML config file"),
    ] = None,
) -> None:
    """Export all skills as Hermes SKILL.md files.

    Files are written to ``{storage.skills_dir}/markdown/`` by default
    (or the directory given with ``--out``), one ``SKILL.md``-compatible
    file per skill, named after the skill (slugified).
    """
    orch = _get_orchestrator(config)
    skills = _run_async(orch.list_skills(limit=100_000))

    if not skills:
        typer.secho("No skills found. Run a pipeline first.", fg=typer.colors.YELLOW)
        return

    if out_dir:
        target = Path(out_dir)
    else:
        target = Path(orch.config.storage.skills_dir) / "markdown"
    target.mkdir(parents=True, exist_ok=True)

    used_names: set[str] = set()
    exported = 0
    for skill in skills:
        slug = _slugify(skill.name) or skill.id
        if slug in used_names:
            slug = f"{slug}-{skill.id}"
        used_names.add(slug)
        (target / f"{slug}.md").write_text(skill.to_skill_markdown(), encoding="utf-8")
        exported += 1

    typer.secho(
        f"Exported {exported} skill(s) to {target}",
        fg=typer.colors.GREEN,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _slugify(name: str) -> str:
    """Convert a skill name into a safe filesystem slug.

    Lowercases, strips non-alphanumeric characters, and collapses runs
    of spaces/underscores into single hyphens.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower())
    return slug.strip("-")


def _print_pipeline_result(ctx) -> None:
    """Pretty-print a pipeline result to the console."""
    from rich.console import Console
    from rich.table import Table

    console = Console()

    if ctx.book:
        console.print(
            f"\n[bold]Book:[/bold] {Path(ctx.book.file_path).name}  [dim]({ctx.book.id})[/dim]"
        )

    if ctx.errors:
        console.print(f"\n[red]Errors ({len(ctx.errors)}):[/red]")
        for err in ctx.errors:
            console.print(f"  [{err['stage']}] {err['message']}")

    console.print(f"\n[bold]Total duration:[/bold] {ctx.total_duration_s:.2f}s")

    if ctx.skills:
        table = Table(title=f"Generated Skills ({len(ctx.skills)})")
        table.add_column("Name", style="cyan")
        table.add_column("Category")
        table.add_column("Status")
        table.add_column("ID")

        for skill in ctx.skills:
            table.add_row(
                skill.name,
                skill.category or "—",
                skill.status.value,
                skill.id,
            )
        console.print(table)
    else:
        console.print("[dim]No skills generated in this run.[/dim]")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
