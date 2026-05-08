"""Huginn CLI — command-line interface for running and inspecting pipelines."""

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from .config import get_huginn_home, load_config
from .db import HuginnDB
from .executor import execute_pipeline
from .manifest import list_pipelines
from .skill import list_skills

console = Console()


@click.group()
@click.version_option(version="0.1.0")
def main():
    """Huginn — Send out the ravens. They come back with results."""
    pass


@main.command()
@click.argument("pipeline_name")
@click.option("--input", "-i", "input_path", required=True, help="Input file or directory")
@click.option("--backend", "-b", default=None, help="Override backend (e.g., i3, mac)")
@click.option("--quiet", "-q", is_flag=True, help="Suppress progress output")
def run(pipeline_name: str, input_path: str, backend: str | None, quiet: bool):
    """Run a pipeline on an input file."""
    input_p = Path(input_path)
    if not input_p.exists():
        console.print(f"[red]Input not found: {input_path}[/red]")
        sys.exit(1)

    try:
        result = execute_pipeline(
            pipeline_name=pipeline_name,
            input_path=input_p,
            backend_override=backend,
            verbose=not quiet,
        )
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)
    except ValueError as e:
        console.print(f"[red]Pipeline error: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        sys.exit(1)

    if result["status"] == "complete":
        console.print(f"\n[green]✓ Task {result['task_id']} complete[/green]")
        console.print(f"  Output: {result['output_dir']}")
    else:
        console.print(f"\n[red]✗ Task {result['task_id']} failed[/red]")
        console.print(f"  Error: {result.get('error', 'Unknown')}")
        sys.exit(1)


@main.command()
@click.argument("task_id")
def status(task_id: str):
    """Show the status of a task."""
    huginn_home = get_huginn_home()
    db = HuginnDB(huginn_home / "huginn.db")

    task = db.get_task(task_id)
    if not task:
        console.print(f"[red]Task '{task_id}' not found[/red]")
        sys.exit(1)

    # Task summary
    status_color = {
        "complete": "green",
        "running": "yellow",
        "failed": "red",
        "queued": "blue",
        "cancelled": "dim",
    }.get(task["status"], "white")

    console.print(f"\n[bold]Task {task_id}[/bold] — [{status_color}]{task['status']}[/{status_color}]")
    console.print(f"  Pipeline: {task['pipeline_name']}")
    console.print(f"  Input:    {task['input_path']}")
    if task["started_at"]:
        console.print(f"  Started:  {task['started_at']}")
    if task["completed_at"]:
        console.print(f"  Finished: {task['completed_at']}")
    if task["error_message"]:
        console.print(f"  [red]Error: {task['error_message']}[/red]")

    # Stage details
    stages = db.get_stages(task_id)
    if stages:
        console.print()
        table = Table(title="Stages")
        table.add_column("#", style="dim", width=3)
        table.add_column("Name", min_width=15)
        table.add_column("Model", min_width=15)
        table.add_column("Status", min_width=10)
        table.add_column("Time", justify="right")
        table.add_column("Tokens", justify="right")
        table.add_column("Verified")

        for s in stages:
            s_color = {
                "complete": "green",
                "running": "yellow",
                "failed": "red",
                "pending": "dim",
            }.get(s["status"], "white")

            time_str = f"{s['duration_seconds']:.1f}s" if s["duration_seconds"] else "-"
            tokens_str = str(s["tokens_used"]) if s["tokens_used"] else "-"
            verified = "✓" if s["verification_passed"] == 1 else ("✗" if s["verification_passed"] == 0 else "-")

            table.add_row(
                str(s["stage_index"] + 1),
                s["stage_name"],
                s["model"] or "-",
                f"[{s_color}]{s['status']}[/{s_color}]",
                time_str,
                tokens_str,
                verified,
            )

        console.print(table)

    # Show output preview
    task_dir = huginn_home / "tasks" / task_id / "output"
    if task_dir.exists():
        output_files = [f for f in task_dir.iterdir() if f.is_file()]
        if output_files:
            console.print(f"\n[bold]Output files:[/bold]")
            for f in output_files:
                size = f.stat().st_size
                console.print(f"  {f.name} ({size:,} bytes)")

                # Preview first file
                if f == output_files[0] and f.suffix in (".md", ".txt", ".json"):
                    content = f.read_text()[:500]
                    console.print(f"\n[dim]--- Preview ---[/dim]")
                    console.print(content)
                    if len(f.read_text()) > 500:
                        console.print("[dim]...(truncated)[/dim]")

    db.close()


@main.command(name="pipelines")
def list_pipelines_cmd():
    """List available pipelines."""
    huginn_home = get_huginn_home()
    pipelines = list_pipelines(huginn_home / "pipelines")

    if not pipelines:
        console.print("[dim]No pipelines found. Create one in ~/.huginn/pipelines/[/dim]")
        return

    table = Table(title="Available Pipelines")
    table.add_column("Name", min_width=20)
    table.add_column("Stages", justify="center", width=8)
    table.add_column("Description")

    for p in pipelines:
        table.add_row(p["name"], str(p["stages"]), p["description"])

    console.print(table)


@main.command(name="skills")
def list_skills_cmd():
    """List available global skills."""
    huginn_home = get_huginn_home()
    skills = list_skills(huginn_home / "skills")

    if not skills:
        console.print("[dim]No global skills found. Add .md files to ~/.huginn/skills/[/dim]")
        return

    table = Table(title="Global Skills Library")
    table.add_column("Name", min_width=20)
    table.add_column("Model", min_width=15)
    table.add_column("Backend")

    for s in skills:
        table.add_row(s["name"], s["model"], s["backend"])

    console.print(table)


@main.command()
@click.option("--limit", "-n", default=20, help="Number of tasks to show")
@click.option("--status", "-s", "filter_status", default=None, help="Filter by status")
def tasks(limit: int, filter_status: str | None):
    """List recent tasks."""
    huginn_home = get_huginn_home()
    db = HuginnDB(huginn_home / "huginn.db")

    task_list = db.list_tasks(status=filter_status, limit=limit)

    if not task_list:
        console.print("[dim]No tasks found.[/dim]")
        return

    table = Table(title="Recent Tasks")
    table.add_column("ID", width=10)
    table.add_column("Pipeline", min_width=15)
    table.add_column("Status", min_width=10)
    table.add_column("Stages")
    table.add_column("Queued", min_width=20)

    for t in task_list:
        s_color = {
            "complete": "green",
            "running": "yellow",
            "failed": "red",
            "queued": "blue",
        }.get(t["status"], "white")

        stage_str = f"{t['current_stage']}/{t['total_stages']}" if t["total_stages"] else "-"
        queued = t["queued_at"][:19] if t["queued_at"] else "-"

        table.add_row(
            t["id"],
            t["pipeline_name"],
            f"[{s_color}]{t['status']}[/{s_color}]",
            stage_str,
            queued,
        )

    console.print(table)
    db.close()


if __name__ == "__main__":
    main()
