"""Command-line entry point for heimdallr."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import click
import humanize
from click_default_group import DefaultGroup
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import (
    AGENTS,
    CACHE_DIR,
    CLAUDE_DIR,
    CLAUDE_IDE_DIR,
    CODEX_DIR,
    DATA_DIR,
    DB_PATH,
    INDEX_DIR,
    LOG_FILE,
    STATE_DIR,
)
from .db import open_db
from .index import TantivyIndex
from .logging_config import setup_logging
from .running import wrapper_path
from .search import SessionSearch
from .tui import run_tui


@click.group(cls=DefaultGroup, default="tui", default_if_no_args=True)
@click.version_option(__version__)
def main() -> None:
    """heimdallr — manage Claude Code and Codex sessions.

    Run `hmd` (no args) to open the TUI. Subcommands: tui, ls, stats, doctor.
    """


@main.command()
@click.argument("query", required=False, default="")
@click.option(
    "-a", "--agent", type=click.Choice(["claude", "codex"]), help="Filter by agent",
)
@click.option("--rebuild", is_flag=True, help="Force rebuild the session index")
@click.option(
    "--yolo", is_flag=True, help="Resume sessions with auto-approve / skip-permissions flags",
)
def tui(query: str, agent: str | None, rebuild: bool, yolo: bool) -> None:
    """Open the TUI (default when no subcommand is given)."""
    setup_logging()
    open_db()

    if rebuild:
        search = SessionSearch()
        search.get_all_sessions(force_refresh=True)
        click.echo("Index rebuilt.")

    resume_cmd, resume_dir, session_id, agent_name = run_tui(
        query=query, agent_filter=agent, yolo=yolo,
    )
    if resume_cmd:
        if resume_dir:
            try:
                os.chdir(resume_dir)
            except OSError as e:
                click.echo(f"Could not chdir to {resume_dir}: {e}", err=True)
        # Wrap the agent invocation through resume_wrapper.sh so its $$ (preserved
        # across exec by POSIX) lands in spawned_pids as the agent's PID.
        # Heimdallr can then identify "this is my session" with high confidence.
        if session_id and agent_name:
            wrapper = str(wrapper_path())
            full = ["/bin/sh", wrapper, str(DB_PATH), session_id, agent_name, *resume_cmd]
            os.execvp(full[0], full)
        else:
            os.execvp(resume_cmd[0], resume_cmd)


@main.command()
def stats() -> None:
    """Show index statistics."""
    setup_logging()
    search = SessionSearch()
    search.get_all_sessions()
    _show_stats()


@main.command()
def doctor() -> None:
    """Diagnose paths, lockfiles, and adapter availability."""
    setup_logging()
    console = Console()

    table = Table(show_header=True, header_style="bold")
    table.add_column("Component")
    table.add_column("Path / Status")
    table.add_column("OK", justify="center")

    def row(label: str, path: Path, *, must_exist: bool = False) -> None:
        ok = path.exists() if must_exist else True
        marker = "✓" if ok else "✗"
        table.add_row(label, str(path), f"[green]{marker}[/green]" if ok else f"[red]{marker}[/red]")

    row("Claude sessions", CLAUDE_DIR, must_exist=True)
    row("Claude IDE locks", CLAUDE_IDE_DIR, must_exist=False)
    row("Codex sessions", CODEX_DIR, must_exist=True)
    row("Cache dir", CACHE_DIR)
    row("Data dir", DATA_DIR)
    row("State dir", STATE_DIR)
    row("Tantivy index", INDEX_DIR)
    row("SQLite state", DB_PATH)
    row("Log file", LOG_FILE)

    sqlite_path = shutil.which("sqlite3")
    table.add_row(
        "sqlite3 binary",
        sqlite_path or "(missing — needed for Phase 3 PID tracking)",
        "[green]✓[/green]" if sqlite_path else "[yellow]![/yellow]",
    )

    console.print(table)


@main.command(name="ls")
@click.argument("query", required=False, default="")
@click.option("-a", "--agent", type=click.Choice(["claude", "codex"]))
@click.option("-d", "--directory")
def ls_cmd(query: str, agent: str | None, directory: str | None) -> None:
    """List sessions in the terminal (no TUI)."""
    setup_logging()
    open_db()
    _list_sessions(query, agent, directory)


def _list_sessions(query: str, agent: str | None, directory: str | None) -> None:
    console = Console()
    search = SessionSearch()
    sessions = search.search(query, agent_filter=agent, directory_filter=directory)
    if not sessions:
        console.print("[dim]No sessions found.[/dim]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Agent", style="bold")
    table.add_column("Title")
    table.add_column("Directory", style="dim")
    table.add_column("ID", style="dim")

    home = os.path.expanduser("~")
    for s in sessions[:50]:
        cfg = AGENTS.get(s.agent, {"color": "white"})
        title = s.title[:50] + "..." if len(s.title) > 50 else s.title
        d = s.directory
        if d.startswith(home):
            d = "~" + d[len(home):]
        if len(d) > 35:
            d = "..." + d[-32:]
        table.add_row(f"[{cfg['color']}]{s.agent}[/{cfg['color']}]", title, d, s.id)
    console.print(table)
    console.print(f"\n[dim]Showing {min(len(sessions), 50)} of {len(sessions)} sessions[/dim]")


def _show_stats() -> None:
    console = Console()
    index = TantivyIndex()
    stats = index.get_stats()

    if stats.total_sessions == 0:
        console.print("[dim]No sessions indexed yet. Run [bold]hmd[/bold] to index sessions.[/dim]")
        return

    console.print("\n[bold]Index Statistics[/bold]\n")
    overview = Table(show_header=False, box=None, padding=(0, 2))
    overview.add_column("Label", style="dim")
    overview.add_column("Value")
    overview.add_row("Total sessions", f"[bold]{stats.total_sessions}[/bold]")
    overview.add_row("Total messages", f"{stats.total_messages:,}")
    overview.add_row("Avg messages/session", f"{stats.avg_messages_per_session:.1f}")
    overview.add_row("Index size", humanize.naturalsize(stats.index_size_bytes))
    overview.add_row("Index location", str(INDEX_DIR))
    if stats.oldest_session and stats.newest_session:
        overview.add_row(
            "Date range",
            f"{stats.oldest_session:%Y-%m-%d} to {stats.newest_session:%Y-%m-%d}",
        )
    console.print(overview)

    console.print("\n[bold]Sessions by agent[/bold]\n")
    agent_table = Table(show_header=True, header_style="bold")
    agent_table.add_column("Agent")
    agent_table.add_column("Sessions", justify="right")
    agent_table.add_column("Messages", justify="right")
    for agent_name, count in stats.sessions_by_agent.items():
        cfg = AGENTS.get(agent_name, {"color": "white"})
        msgs = (stats.messages_by_agent or {}).get(agent_name, 0)
        agent_table.add_row(
            f"[{cfg['color']}]{agent_name}[/{cfg['color']}]",
            str(count),
            f"{msgs:,}",
        )
    console.print(agent_table)


if __name__ == "__main__":
    main()
