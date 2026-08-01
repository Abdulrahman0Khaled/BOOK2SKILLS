"""Book-to-Skills Studio — interactive terminal UI.

A simple, menu-driven interface that lets anyone run the full
book-to-skills pipeline from the terminal:

    python -m book_to_skills studio

Features:
- Arrow-key menus (questionary)
- Live progress bars during processing (rich)
- Clear tables for skills/books/stats (rich)
- No technical knowledge required
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text

from .config import PipelineConfig
from .pipeline.orchestrator import PipelineOrchestrator

console = Console()

BANNER = r"""
╔═════════════════════════════════════════════════════════════════════════╗
║   📚  BOOK-TO-SKILLS STUDIO                                             ║
║   Turn books into ready-to-use AI Agent Skills (OpenClaw, Claude...)    ║
╚═════════════════════════════════════════════════════════════════════════╝
"""


def _get_orchestrator() -> PipelineOrchestrator:
    return PipelineOrchestrator(PipelineConfig())


def _run_async(coro):
    """Run an async coroutine from the sync TUI context."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor() as pool:
        return pool.submit(asyncio.run, coro).result()


# ---------------------------------------------------------------------------
# Menu helpers
# ---------------------------------------------------------------------------


def show_banner() -> None:
    console.clear()
    console.print(Panel(Text(BANNER, style="bold cyan"), border_style="cyan"))
    console.print()


def main_menu() -> str:
    """Display the main menu and return the selected choice."""
    choices = [
        "🚀  Run pipeline — all books",
        "📄  Run pipeline — one book",
        "📋  List books",
        "📦  List skills",
        "🔍  Search skills",
        "📤  Export SKILL.md",
        "📊  System statistics",
        "🗑️  Clear cache",
        "🚪  Exit",
    ]
    return (
        questionary.select(
            "Choose an action:",
            choices=choices,
            qmark=">>",
            pointer=">>",
            instruction="(use arrow keys ⬆⬇ then Enter)",
        ).ask()
        or "Exit"
    )


def pause() -> None:
    questionary.confirm("Press Enter to continue...", default=True).ask()


# ---------------------------------------------------------------------------
# Progress display
# ---------------------------------------------------------------------------


def run_pipeline_with_progress(
    orchestrator: PipelineOrchestrator,
    file_paths: list[str],
    incremental: bool = True,
) -> list[Any]:
    """Run the pipeline on multiple books with a live progress bar.

    One top-level task per book; stage activity is shown in the
    description column as the pipeline advances.
    """
    total_books = len(file_paths)
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=30),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    )

    results: list[Any] = []
    with progress:
        for idx, fp in enumerate(file_paths, 1):
            name = Path(fp).name
            book_task = progress.add_task(
                f"[cyan]📖 {name[:45]} ({idx}/{total_books})",
                total=100,
            )

            def _on_stage(stage_name: str, _task: Any = book_task, _name: str = name) -> None:
                progress.update(
                    _task,
                    description=f"[cyan]📖 {_name[:35]} — [green]{stage_name}[/green]",
                )

            ctx = asyncio.run(_run_pipeline_single(orchestrator, fp, incremental, _on_stage))
            progress.update(book_task, completed=100)

            if ctx.errors:
                progress.console.print(f"  [red]✗ {name}: {len(ctx.errors)} error(s)[/red]")
            else:
                n = len(ctx.skills)
                progress.console.print(f"  [green]✓ {name}: {n} skill(s) generated[/green]")
            results.append(ctx)

    return results


async def _run_pipeline_single(
    orchestrator: PipelineOrchestrator,
    file_path: str,
    incremental: bool,
    on_stage: Any = None,
):
    """Run one book and mirror stage events to a console for live feedback."""
    ctx = await orchestrator.run_pipeline(
        file_path,
        incremental=incremental,
        progress_callback=on_stage,
    )
    return ctx


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def show_books(orchestrator: PipelineOrchestrator) -> None:
    books = orchestrator.list_books()
    if not books:
        console.print("[yellow]No books found in books/[/yellow]")
        return

    table = Table(title=f"📚 Books ({len(books)})", border_style="cyan")
    table.add_column("#", style="dim")
    table.add_column("File", style="bold")
    table.add_column("Type", style="blue")
    table.add_column("Size", justify="right")

    for i, b in enumerate(books, 1):
        table.add_row(str(i), b["file_name"], b["format"].upper(), f"{b['size_mb']:.1f} MB")

    console.print(table)


def show_skills(orchestrator: PipelineOrchestrator) -> None:
    skills = _run_async(orchestrator.list_skills())
    if not skills:
        console.print("[yellow]No skills yet — run the pipeline first[/yellow]")
        return

    table = Table(title=f"📦 Skills ({len(skills)})", border_style="green")
    table.add_column("#", style="dim")
    table.add_column("Name", style="bold cyan", no_wrap=False)
    table.add_column("Category", style="blue")
    table.add_column("Quality", justify="right")
    table.add_column("Status", justify="center")
    table.add_column("Source", style="dim", no_wrap=False)

    for i, s in enumerate(skills, 1):
        status_style = {
            "approved": "green",
            "reviewed": "yellow",
            "rejected": "red",
            "draft": "dim",
            "published": "green",
        }.get(s.status.value, "white")
        table.add_row(
            str(i),
            s.name,
            s.category or "—",
            f"{s.quality_score:.1f}",
            f"[{status_style}]{s.status.value}[/{status_style}]",
            Path(s.source_book).name if s.source_book else "—",
        )

    console.print(table)


def search_skills(orchestrator: PipelineOrchestrator) -> None:
    query = questionary.text("🔍 Enter search keyword:", qmark=">>").ask()
    if not query or not query.strip():
        return

    skills = _run_async(orchestrator.list_skills())
    query_l = query.strip().lower()
    matches = [
        s
        for s in skills
        if query_l in s.name.lower()
        or query_l in s.description.lower()
        or any(query_l in t.lower() for t in s.tags)
        or query_l in s.category.lower()
    ]

    if not matches:
        console.print(f"[yellow]No results for '{query}'[/yellow]")
        return

    table = Table(title=f"🔍 Search results for '{query}' ({len(matches)})", border_style="magenta")
    table.add_column("Name", style="bold cyan")
    table.add_column("Category", style="blue")
    table.add_column("Quality", justify="right")
    table.add_column("Status", justify="center")
    table.add_column("Description", style="dim", no_wrap=False)

    for s in sorted(matches, key=lambda x: -x.quality_score)[:30]:
        table.add_row(
            s.name,
            s.category or "—",
            f"{s.quality_score:.1f}",
            s.status.value,
            s.description[:80],
        )
    console.print(table)


def export_markdown(orchestrator: PipelineOrchestrator) -> None:

    skills = _run_async(orchestrator.list_skills())
    if not skills:
        console.print("[yellow]No skills to export[/yellow]")
        return

    md_dir = Path("outputs/skills/markdown")
    md_dir.mkdir(parents=True, exist_ok=True)

    exported = 0
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Exporting SKILL.md...", total=len(skills))
        for s in skills:
            try:
                filename = s.name[:60].rstrip("-") + ".md"
                (md_dir / filename).write_text(s.to_skill_markdown(), encoding="utf-8")
                exported += 1
            except Exception:
                pass
            progress.update(task, advance=1)

    console.print(f"[green]✓ Exported {exported} skills to outputs/skills/markdown/[/green]")


def show_stats(orchestrator: PipelineOrchestrator) -> None:
    from collections import Counter

    skills = _run_async(orchestrator.list_skills())
    books = orchestrator.list_books()

    if not skills:
        console.print("[yellow]No skills yet[/yellow]")
        return

    cats = Counter(s.category or "Uncategorized" for s in skills)
    statuses = Counter(s.status.value for s in skills)
    scores = [s.quality_score for s in skills]

    console.print(
        Panel(
            f"[bold cyan]📊 System Statistics[/bold cyan]\n\n"
            f"[white]Books:[/white] {len(books)}  |  "
            f"[white]Skills:[/white] {len(skills)}\n\n"
            f"[bold]Categories:[/bold]\n"
            + "\n".join(f"  • {c}: {n}" for c, n in cats.most_common())
            + "\n\n[bold]Statuses:[/bold]\n"
            + "\n".join(f"  • {st}: {n}" for st, n in statuses.most_common())
            + f"\n\n[bold]Quality:[/bold] "
            f"avg {sum(scores) / len(scores):.1f}/10  |  "
            f"max {max(scores):.1f}  |  "
            f"min {min(scores):.1f}",
            border_style="green",
        )
    )


def clear_cache(orchestrator: PipelineOrchestrator) -> None:
    confirm = questionary.confirm(
        "🗑️ Clear cache? (next run will reprocess everything)",
        default=False,
    ).ask()
    if not confirm:
        return

    with console.status("[cyan]Clearing cache...[/cyan]"):
        _run_async(orchestrator.clear_cache())
    console.print("[green]✓ Cache cleared successfully[/green]")


# ---------------------------------------------------------------------------
# Run actions
# ---------------------------------------------------------------------------


def run_all_books(orchestrator: PipelineOrchestrator) -> None:
    books = orchestrator.list_books()
    if not books:
        console.print("[yellow]No books in books/ — add PDF/DOCX files and try again[/yellow]")
        return

    incremental = questionary.confirm(
        "⚡ Incremental mode (skip already-processed books)?",
        default=True,
    ).ask()

    console.print(f"[cyan]🚀 Processing {len(books)} books... (this may take a while)[/cyan]")
    results = run_pipeline_with_progress(
        orchestrator,
        [b["file_path"] for b in books],
        incremental=bool(incremental),
    )

    ok = sum(1 for r in results if not r.errors)
    console.print(f"\n[green]✓ Done: {ok}/{len(results)} books succeeded[/green]")


def run_one_book(orchestrator: PipelineOrchestrator) -> None:
    books = orchestrator.list_books()
    if not books:
        console.print("[yellow]No books found in books/[/yellow]")
        return

    names = {b["file_name"]: b["file_path"] for b in books}
    choice = questionary.select(
        "📄 Choose a book:",
        choices=list(names.keys()),
        qmark=">>",
        pointer=">>",
        instruction="(use arrow keys ⬆⬇ then Enter)",
    ).ask()
    if not choice:
        return

    incremental = questionary.confirm(
        "⚡ Incremental mode?",
        default=True,
    ).ask()

    console.print(f"[cyan]🚀 Processing {choice}...[/cyan]")
    run_pipeline_with_progress(
        orchestrator,
        [names[choice]],
        incremental=bool(incremental),
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def studio() -> None:
    """Launch the interactive Book-to-Skills Studio."""
    orchestrator = _get_orchestrator()

    while True:
        show_banner()
        choice = main_menu()

        if choice.startswith("🚀"):
            run_all_books(orchestrator)
        elif choice.startswith("📄"):
            run_one_book(orchestrator)
        elif choice.startswith("📋"):
            show_books(orchestrator)
        elif choice.startswith("📦"):
            show_skills(orchestrator)
        elif choice.startswith("🔍"):
            search_skills(orchestrator)
        elif choice.startswith("📤"):
            export_markdown(orchestrator)
        elif choice.startswith("📊"):
            show_stats(orchestrator)
        elif choice.startswith("🗑️"):
            clear_cache(orchestrator)
        elif choice.startswith("🚪") or choice is None:
            console.print("[cyan]Goodbye! 👋[/cyan]")
            break

        if not choice.startswith("🚪"):
            pause()


if __name__ == "__main__":
    studio()
