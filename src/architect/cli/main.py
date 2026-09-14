"""Terminal entry point for Architect OS."""

from __future__ import annotations

import sqlite3
import json
import os
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text
from architect.recorder.recorder import FlightRecorder
from architect.ingest import ingest

from architect.storage.db import (
    FIDELITY_LEVELS,
    count_runs_by_status,
    create_run,
    ensure_project,
    get_run,
    list_recent_runs,
    project_database_path,
)


app = typer.Typer(
    name="architect",
    help="Local-first control plane for AI coding agents.",
    no_args_is_help=True,
)
console = Console()

STATUS_STYLES = {
    "RUNNING": "bold yellow",
    "SUCCESS": "bold green",
    "FAILED": "bold red",
}


def _current_project() -> tuple[Path, Path]:
    root = Path.cwd().resolve()
    return root, project_database_path(root)


@app.command("init")
def init_command() -> None:
    """Initialize Architect OS state for the current project."""
    root, database = _current_project()
    try:
        ensure_project(root, db_path=database)
    except (OSError, sqlite3.Error) as error:
        console.print(f"[bold red]Initialization failed:[/bold red] {error}")
        raise typer.Exit(code=1) from error

    console.print("[bold green]Architect OS initialized[/bold green]")
    console.print(f"\n[bold]Project:[/bold]\n{root}")
    console.print(f"\n[bold]Database:[/bold]\n{database}")
    console.print("\n[bold]Status:[/bold]\nready")


@app.command("run")
def run_command(
    task_description: str = typer.Argument(..., help="Task assigned to the agent."),
    agent: str = typer.Option(..., "--agent", help="Agent name, such as codex."),
    fidelity: str = typer.Option(
        ...,
        "--fidelity",
        help="Observer fidelity: NATIVE, SESSION_LOG, or PASSIVE.",
    ),
) -> None:
    """Register a new agent run in the flight recorder."""
    try:
        root, database = _current_project()
        ensure_project(root, db_path=database)
        run_id = create_run(
            agent_name=agent,
            fidelity_level=fidelity,
            task_description=task_description,
            db_path=database,
        )
    except ValueError as error:
        choices = ", ".join(sorted(FIDELITY_LEVELS))
        raise typer.BadParameter(str(error), param_hint=f"--fidelity ({choices})") from error
    except sqlite3.Error as error:
        console.print(f"[bold red]Run kaydedilemedi:[/bold red] {error}")
        raise typer.Exit(code=1) from error

    console.print("[bold green]Run kaydedildi.[/bold green]")
    console.print(f"Run ID: [cyan]{run_id}[/cyan]")


@app.command("status")
def status_command(
    limit: int = typer.Option(10, "--limit", min=1, help="Number of recent runs."),
) -> None:
    """Show overall status and the most recent agent runs."""
    try:
        _, database = _current_project()
        runs = list_recent_runs(limit=limit, db_path=database)
        counts = count_runs_by_status(db_path=database)
    except (OSError, sqlite3.Error) as error:
        console.print(f"[bold red]Durum okunamadı:[/bold red] {error}")
        raise typer.Exit(code=1) from error

    total = sum(counts.values())
    summary = "  ".join(
        f"[{STATUS_STYLES.get(name, 'white')}]{name}: {count}[/]"
        for name, count in counts.items()
    )
    console.print(f"[bold]Toplam run:[/bold] {total}" + (f"  {summary}" if summary else ""))

    if not runs:
        console.print("[yellow]Henüz kaydedilmiş bir run yok.[/yellow]")
        return

    table = Table(title="Son Agent Run'ları", header_style="bold cyan")
    table.add_column("Run ID", no_wrap=True, width=8)
    table.add_column("Agent")
    table.add_column("Fidelity")
    table.add_column("Status")
    table.add_column("Başlangıç", no_wrap=True)
    table.add_column("Task", overflow="fold")

    for run in runs:
        run_status = str(run["status"])
        table.add_row(
            Text(str(run["run_id"])[:8]),
            Text(str(run["agent_name"])),
            Text(str(run["fidelity_level"])),
            Text(run_status, style=STATUS_STYLES.get(run_status, "white")),
            Text(str(run["started_at"])),
            Text(str(run["task_description"])),
        )

    console.print(table)


@app.command("inspect")
def inspect_command(run_id: str = typer.Argument(..., help="Full Architect run ID or unique prefix.")) -> None:
    """Inspect run metadata and its normalized event timeline."""
    _, database = _current_project()
    try:
        run = get_run(run_id, db_path=database)
        if run is None:
            console.print(Text(f"Unknown run: {run_id}", style="red"))
            raise typer.Exit(code=1)
        events = FlightRecorder(database).timeline(run["run_id"])
    except (OSError, sqlite3.Error, ValueError) as error:
        console.print(Text(f"Inspection failed: {error}", style="red"))
        raise typer.Exit(code=1) from error
    console.print("[bold]Architect Run[/bold]")
    for label, key in (("Run ID", "run_id"), ("Agent", "agent_name"),
                       ("Fidelity", "fidelity_level"), ("Status", "status"),
                       ("Task", "task_description"), ("Started", "started_at"),
                       ("Ended", "ended_at")):
        console.print(Text(f"{label}: {run[key] or '—'}"))
    console.print("[bold]Timeline[/bold]")
    if not events:
        console.print("No normalized events recorded. Legacy M0 events remain in storage.")
    for event in events:
        console.print(Text(f"{event.timestamp}  {event.event_type.upper()}  {event.status or ''}"))
        if event.tool or event.target:
            console.print(Text(f"  {event.tool or ''} {event.target or ''}"))
        if event.metadata:
            import json
            console.print(Text("  " + json.dumps(event.metadata, sort_keys=True, ensure_ascii=False)))


@app.command("ingest")
def ingest_command(provider: str = typer.Argument(..., help="Hook provider (claude).")) -> None:
    """Consume one live hook JSON object from stdin; successful ingestion is quiet."""
    try:
        payload = json.load(sys.stdin)
        # Config invokes us from the fixed project root, never from payload cwd.
        _, database = _current_project()
        if not database.is_file():
            raise ValueError("Project database missing; run architect init at the project root")
        ingest(provider, payload, db_path=database, live=True,
               run_id=os.environ.get("ARCHITECT_RUN_ID"))
    except (OSError, ValueError, TypeError, sqlite3.Error) as error:
        typer.echo(f"Architect ingest failed: {error}", err=True)
        raise typer.Exit(code=1) from error


if __name__ == "__main__":
    app()
