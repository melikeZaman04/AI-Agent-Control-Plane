"""Terminal entry point for Architect OS."""

from __future__ import annotations

import sqlite3
import json
import os
import sys
from contextlib import closing
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text
from architect.recorder.recorder import FlightRecorder
from architect.ingest import ingest
from architect.chronicle import ProjectChronicle

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


def _registered_project():
    root, database = _current_project()
    if not database.is_file():
        raise ValueError("Project database missing; run architect init at the project root")
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
        projects = connection.execute("SELECT id, root_path FROM projects").fetchall()
    if len(projects) != 1:
        raise ValueError("Chronicle requires exactly one registered project per database")
    project_id, project_root = projects[0]
    if project_root != str(root):
        raise ValueError("Registered project root does not match the current directory")
    return root, database, project_id


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


@app.command("chronicle")
def chronicle_command(
    run_id: str | None = typer.Option(None, "--run", help="Exact full Architect run ID."),
    event_id: str | None = typer.Option(None, "--event", help="Exact evidence event ID; requires --run."),
    as_json: bool = typer.Option(False, "--json", help="Emit deterministic JSON."),
    view: str = typer.Option("episodes", "--view", help="episodes, changes, decisions, receipts, automations, or failures."),
    revision: str = typer.Option("HEAD", "--revision", help="Git revision for changes/decisions; resolved once to a commit."),
) -> None:
    """Display project history or inspect a run's source evidence (read-only)."""
    if view not in {"episodes", "changes", "decisions", "receipts", "automations", "failures"}:
        raise typer.BadParameter("Unknown Chronicle view")
    if event_id is not None and view != "episodes":
        raise typer.BadParameter("--event requires the episodes view")
    if view in {"changes", "decisions"} and run_id is not None:
        raise typer.BadParameter("Git history cannot be attributed to a run; omit --run")
    if revision != "HEAD" and view not in {"changes", "decisions"}:
        raise typer.BadParameter("--revision requires changes or decisions")
    if event_id is not None and run_id is None:
        raise typer.BadParameter("--event requires --run")
    try:
        root, database, project_id = _registered_project()
        chronicle = ProjectChronicle(database)
        if view != "episodes":
            if view in {"changes", "decisions"}:
                from architect.git_history import GitHistory
                history = GitHistory(root)
                records = history.changes(revision) if view == "changes" else history.decisions(revision)
            else:
                if run_id is not None and not chronicle.query(project_id, run_id=run_id):
                    raise ValueError(f"Unknown run: {run_id}")
                records = (chronicle.failures(project_id, run_id=run_id) if view == "failures"
                           else chronicle.receipts(project_id, run_id=run_id))
                if view == "automations":
                    records = [record for record in records if record['automated'] is True]
            # ASCII escaping preserves arbitrary Git filename bytes in valid JSON.
            output = json.dumps(records, sort_keys=True, ensure_ascii=True,
                                **({"separators": (",", ":")} if as_json else {"indent": 2}))
        elif event_id is not None:
            event = chronicle.evidence(project_id, run_id=run_id, event_id=event_id)
            data = json.loads(event.to_json())
            output = event.to_json() if as_json else "Evidence\n" + json.dumps(
                data, sort_keys=True, ensure_ascii=False, indent=2,
            )
        else:
            episodes = chronicle.query(project_id, run_id=run_id)
            if run_id is not None and not episodes:
                raise ValueError(f"Unknown run: {run_id}")
            if as_json:
                output = "[" + ",".join(episode.to_json() for episode in episodes) + "]"
            else:
                lines = []
                for episode in episodes:
                    lines.extend([
                        f"Episode: {episode.episode_id}",
                        f"Project: {episode.project_root}",
                        f"Run: {episode.run_id}  Status: {episode.run_status}",
                        f"Began: {episode.began_at or 'unknown'}  Ended: {episode.ended_at or 'unknown'}",
                    ])
                    if not episode.facts:
                        lines.append("  No normalized evidence.")
                    for fact in episode.facts:
                        lines.append(f"  {fact.event_type} status={fact.status if fact.status is not None else 'unknown'} "
                                     f"provider={fact.provider if fact.provider is not None else 'unknown'} "
                                     f"fidelity={fact.fidelity if fact.fidelity is not None else 'unknown'} count={fact.count}")
                        lines.append("    Evidence: " + ", ".join(fact.evidence_event_ids))
                output = "\n".join(lines) if lines else "No Chronicle episodes."
    except (OSError, sqlite3.Error, ValueError, TypeError) as error:
        typer.echo(f"Chronicle failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(output)


@app.command("session")
def session_command(
    report: str = typer.Argument(..., help="status, changes, day, resume, or explain"),
    run_id: str | None = typer.Option(None, "--run"),
    event_id: str | None = typer.Option(None, "--event"),
    day: str | None = typer.Option(None, "--date", help="Explicit YYYY-MM-DD for day."),
    timezone: str = typer.Option("UTC", "--timezone"),
    revision: str = typer.Option("HEAD", "--revision"),
    since: str | None = typer.Option(None, "--since", help="Reachable baseline revision, excluded from changes."),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Read deterministic session reports; no agent execution or inferred advice."""
    from architect.session import SessionIntelligence
    from zoneinfo import ZoneInfoNotFoundError
    if report not in {"status", "changes", "day", "resume", "explain"}:
        raise typer.BadParameter("Unknown session report")
    if (report == "day") != (day is not None):
        raise typer.BadParameter("--date is required only for day")
    if report == "explain" and run_id is None:
        raise typer.BadParameter("explain requires --run")
    if event_id is not None and report != "explain":
        raise typer.BadParameter("--event requires explain")
    if run_id is not None and report not in {"resume", "explain"}:
        raise typer.BadParameter("--run requires resume or explain")
    if since is not None and report != "changes":
        raise typer.BadParameter("--since requires changes")
    if revision != "HEAD" and report not in {"changes", "day"}:
        raise typer.BadParameter("--revision requires changes or day")
    if timezone != "UTC" and report != "day":
        raise typer.BadParameter("--timezone requires day")
    try:
        root, database, project_id = _registered_project()
        service = SessionIntelligence(database, project_id)
        if report == "status":
            result = service.status()
        elif report == "changes":
            result = service.changes(root, revision=revision, since=since)
        elif report == "day":
            result = service.day(root, day, timezone=timezone, revision=revision)
        elif report == "resume":
            result = service.resume(run_id)
        else:
            result = service.explain(run_id, event_id=event_id)
        output = json.dumps(result, sort_keys=True, ensure_ascii=True,
                            **({"separators": (",", ":")} if as_json else {"indent": 2}))
    except (OSError, sqlite3.Error, ValueError, TypeError, ZoneInfoNotFoundError) as error:
        typer.echo(f"Session report failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(output)


@app.command("context")
def context_command(
    action: str = typer.Argument(..., help="index, map, search, read, or bootstrap"),
    query: str = typer.Option("", "--query"),
    path: str | None = typer.Option(None, "--path"),
    start: int = typer.Option(1, "--start", min=1),
    end: int | None = typer.Option(None, "--end", min=1),
    limit: int = typer.Option(5, "--limit", min=1),
    max_chars: int = typer.Option(12000, "--max-chars", min=1),
) -> None:
    """Build local source metadata and retrieve provenance-linked context as JSON."""
    from architect.context import LocalContext
    if action not in {"index", "map", "search", "read", "bootstrap"}:
        raise typer.BadParameter("Unknown context action")
    if (action == "read") != (path is not None):
        raise typer.BadParameter("--path is required only for read")
    try:
        root, _, _ = _registered_project()
        provider = LocalContext(root)
        if action == "index":
            result = provider.refresh()
        elif action == "map":
            result = provider.repo_map()
        elif action == "search":
            result = provider.search(query, limit=limit)
        elif action == "read":
            result = provider.read(path, start=start, end=end)
        else:
            result = provider.bootstrap(query, max_chars=max_chars, limit=limit)
        output = json.dumps(result, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as error:
        typer.echo(f"Context failed: {error}", err=True)
        raise typer.Exit(code=1) from error
    typer.echo(output)


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


@app.command("codex-listen")
def codex_listen_command(
    run_id: str = typer.Option(..., "--run", help="Full run ID or unique prefix."),
    host: str = typer.Option("127.0.0.1", help="Loopback only."),
    port: int = typer.Option(14318, min=1, max=65535),
) -> None:
    """Receive binary Codex OTLP logs until Ctrl+C."""
    from architect.otlp import CodexLogServer
    _, database = _current_project()
    try:
        with CodexLogServer((host, port), run_id=run_id, db_path=database) as server:
            console.print(Text(f"Architect Codex listener\nRun: {server.run_id}\n"
                               f"Listening: http://{host}:{port}/v1/logs\nProvider: codex\nPress Ctrl+C to stop."))
            try:
                server.serve_forever(poll_interval=0.2)
            except KeyboardInterrupt:
                pass
            finally:
                console.print(Text(f"Listener stopped. Recorded: {server.recorded}; ignored: {server.ignored}; rejected: {server.rejected}"))
    except (ValueError, OSError, sqlite3.Error) as error:
        typer.echo(f"Codex listener failed: {error}", err=True)
        raise typer.Exit(code=1) from error


if __name__ == "__main__":
    app()
