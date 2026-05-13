"""Huginn CLI — command-line interface for running and inspecting pipelines."""

import json
import os
import shutil
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
@click.option("--bg", is_flag=True, help="Run in background, return immediately with task ID")
@click.option("--quiet", "-q", is_flag=True, help="Suppress progress output")
def run(pipeline_name: str, input_path: str, backend: str | None, bg: bool, quiet: bool):
    """Run a pipeline on an input file."""
    input_p = Path(input_path)
    if not input_p.exists():
        console.print(f"[red]Input not found: {input_path}[/red]")
        sys.exit(1)

    if bg:
        from .background import launch_background

        try:
            result = launch_background(pipeline_name, input_p, backend)
        except Exception as e:
            console.print(f"[red]Failed to launch background task: {e}[/red]")
            sys.exit(1)

        console.print(f"[green]Task {result['task_id']} launched in background (PID {result['pid']})[/green]")
        console.print(f"  Logs: {result['log_path']}")
        console.print(f"  Check status: huginn status {result['task_id']}")
        console.print(f"  View logs:    huginn logs {result['task_id']}")
        return

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

    # Detect stale "running" status
    if task["status"] == "running" and not _is_task_process_alive(huginn_home, task_id):
        db.update_task(task_id, status="interrupted")
        task = db.get_task(task_id)

    # Task summary
    status_color = {
        "complete": "green",
        "running": "yellow",
        "failed": "red",
        "queued": "blue",
        "cancelled": "dim",
        "interrupted": "magenta",
    }.get(task["status"], "white")

    # Show resume hint for resumable statuses
    resumable = task["status"] in ("interrupted", "cancelled", "failed")

    # Get stages to determine backend(s) used
    stages = db.get_stages(task_id)
    backends_used = sorted(set(s["backend"] for s in stages if s["backend"])) if stages else []
    backend_str = ", ".join(backends_used) if backends_used else "-"

    # F099 — Determine execution mode (background vs local/foreground)
    mode = _get_task_mode(huginn_home, task)
    mode_color = "cyan" if mode == "background" else "blue"

    console.print(f"\n[bold]Task {task_id}[/bold] — [{status_color}]{task['status']}[/{status_color}]")
    console.print(f"  Pipeline: {task['pipeline_name']}")
    console.print(f"  Mode:     [{mode_color}]{mode}[/{mode_color}]")
    console.print(f"  Backend:  {backend_str}")
    console.print(f"  Input:    {task['input_path']}")
    if resumable:
        console.print(f"  [dim]Resume with: huginn resume {task_id}[/dim]")
    if task["started_at"]:
        console.print(f"  Started:  {task['started_at']}")
    if task["completed_at"]:
        console.print(f"  Finished: {task['completed_at']}")
    if task["error_message"]:
        console.print(f"  [red]Error: {task['error_message']}[/red]")

    # Stage details
    if stages:
        console.print()
        table = Table(title="Stages")
        table.add_column("#", style="dim", width=3)
        table.add_column("Name", min_width=15)
        table.add_column("Model", min_width=12)
        table.add_column("Backend", min_width=8)
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
                "cancelled": "dim",
            }.get(s["status"], "white")

            time_str = f"{s['duration_seconds']:.1f}s" if s["duration_seconds"] else "-"
            tokens_str = str(s["tokens_used"]) if s["tokens_used"] else "-"
            verified = "✓" if s["verification_passed"] == 1 else ("✗" if s["verification_passed"] == 0 else "-")

            table.add_row(
                str(s["stage_index"] + 1),
                s["stage_name"],
                s["model"] or "-",
                s["backend"] or "-",
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


def _get_task_mode(huginn_home: Path, task: dict) -> str:
    """Return 'background' or 'local' for the given task record.

    Detection order:
      1. PID file present → background (written by background.py)
      2. metadata JSON contains {"background": true} → background
      3. Otherwise → local (foreground)
    """
    pid_path = huginn_home / "tasks" / task["id"] / "pid"
    if pid_path.exists():
        return "background"
    raw_meta = task.get("metadata")
    if raw_meta:
        try:
            meta = json.loads(raw_meta)
            if meta.get("background"):
                return "background"
        except (json.JSONDecodeError, TypeError):
            pass
    return "local"


@main.command()
@click.option("--limit", "-n", default=20, help="Number of tasks to show")
@click.option("--status", "-s", "filter_status", default=None, help="Filter by status")
@click.option(
    "--mode",
    "-m",
    "filter_mode",
    default=None,
    type=click.Choice(["local", "background"], case_sensitive=False),
    help="Filter by execution mode: local or background",
)
def tasks(limit: int, filter_status: str | None, filter_mode: str | None):
    """List recent tasks.

    Use --mode to filter by execution mode: local (foreground) or background.
    """
    huginn_home = get_huginn_home()
    db = HuginnDB(huginn_home / "huginn.db")

    # Fetch extra rows when mode-filtering so we can trim to --limit after filter
    fetch_limit = limit if not filter_mode else limit * 4
    task_list = db.list_tasks(status=filter_status, limit=fetch_limit)

    if not task_list:
        console.print("[dim]No tasks found.[/dim]")
        db.close()
        return

    # Detect stale "running" tasks whose process is no longer alive
    stale_ids = []
    for t in task_list:
        if t["status"] == "running":
            if not _is_task_process_alive(huginn_home, t["id"]):
                stale_ids.append(t["id"])

    # Update stale tasks in DB
    for stale_id in stale_ids:
        db.update_task(stale_id, status="interrupted")

    # Re-fetch if we changed any statuses
    if stale_ids:
        task_list = db.list_tasks(status=filter_status, limit=fetch_limit)

    # Apply mode filter (local vs background)
    if filter_mode:
        task_list = [t for t in task_list if _get_task_mode(huginn_home, t) == filter_mode.lower()]
        task_list = task_list[:limit]

    if not task_list:
        suffix = f" with mode={filter_mode}" if filter_mode else ""
        console.print(f"[dim]No tasks found{suffix}.[/dim]")
        db.close()
        return

    title = "Recent Tasks"
    if filter_mode:
        title += f" (mode: {filter_mode})"

    table = Table(title=title)
    table.add_column("ID", width=10)
    table.add_column("Pipeline", min_width=15)
    table.add_column("Backend", min_width=8)
    table.add_column("Mode", min_width=12)
    table.add_column("Status", min_width=10)
    table.add_column("Stages")
    table.add_column("Queued", min_width=20)

    for t in task_list:
        s_color = {
            "complete": "green",
            "running": "yellow",
            "failed": "red",
            "queued": "blue",
            "interrupted": "magenta",
            "cancelled": "dim",
        }.get(t["status"], "white")

        stage_str = f"{t['current_stage']}/{t['total_stages']}" if t["total_stages"] else "-"
        queued = t["queued_at"][:19] if t["queued_at"] else "-"
        backends_used = db.get_task_backends(t["id"])
        backend_str = ", ".join(backends_used) if backends_used else "-"
        mode = _get_task_mode(huginn_home, t)
        mode_color = "cyan" if mode == "background" else "blue"

        table.add_row(
            t["id"],
            t["pipeline_name"],
            backend_str,
            f"[{mode_color}]{mode}[/{mode_color}]",
            f"[{s_color}]{t['status']}[/{s_color}]",
            stage_str,
            queued,
        )

    console.print(table)

    if stale_ids:
        console.print(f"\n[dim]{len(stale_ids)} interrupted task(s) detected. Resume with: huginn resume <task-id>[/dim]")

    db.close()


@main.command()
@click.argument("task_id")
@click.option("--backend", "-b", default=None, help="Override backend for resumed stages")
@click.option("--quiet", "-q", is_flag=True, help="Suppress progress output")
def resume(task_id: str, backend: str | None, quiet: bool):
    """Resume an interrupted task from the last completed stage."""
    huginn_home = get_huginn_home()
    db = HuginnDB(huginn_home / "huginn.db")

    task = db.get_task(task_id)
    if not task:
        console.print(f"[red]Task '{task_id}' not found[/red]")
        sys.exit(1)

    if task["status"] == "complete":
        console.print(f"[yellow]Task '{task_id}' is already complete[/yellow]")
        console.print(f"  Output: {task['output_path']}")
        return

    if task["status"] not in ("interrupted", "failed", "cancelled", "running"):
        console.print(f"[yellow]Task '{task_id}' has status '{task['status']}' — nothing to resume[/yellow]")
        return

    if task["status"] == "running" and _is_task_process_alive(huginn_home, task_id):
        console.print(f"[yellow]Task '{task_id}' is still running (PID alive)[/yellow]")
        console.print(f"  Stop it first: huginn stop {task_id}")
        return

    pipeline_name = task["pipeline_name"]
    input_path = Path(task["input_path"])

    if not input_path.exists():
        console.print(f"[red]Original input no longer exists: {input_path}[/red]")
        console.print("[dim]Check if the file was moved or deleted[/dim]")
        sys.exit(1)

    console.print(f"Resuming task {task_id} — pipeline '{pipeline_name}' from stage {task['current_stage'] + 1}")
    db.close()

    try:
        result = execute_pipeline(
            pipeline_name=pipeline_name,
            input_path=input_path,
            backend_override=backend,
            verbose=not quiet,
            task_id=task_id,
        )
    except Exception as e:
        console.print(f"[red]Resume failed: {e}[/red]")
        sys.exit(1)

    if result["status"] == "complete":
        console.print(f"\n[green]✓ Task {task_id} complete[/green]")
        console.print(f"  Output: {result['output_dir']}")
    else:
        console.print(f"\n[red]✗ Task {task_id} failed[/red]")
        console.print(f"  Error: {result.get('error', 'Unknown')}")
        sys.exit(1)


def _is_task_process_alive(huginn_home: Path, task_id: str) -> bool:
    """Check if a task's background process is still running.

    Returns True if the task has no PID file (foreground task still in progress)
    or if the recorded PID is still alive. Only returns False when we have a PID
    file and the process is confirmed dead — that's the only case where we can
    safely mark a task as interrupted.
    """
    pid_path = huginn_home / "tasks" / task_id / "pid"
    if not pid_path.exists():
        # No PID file — this was a foreground task. We can't tell from here
        # whether the foreground process is still running, so assume it is.
        # Foreground tasks will update their own status on completion/failure.
        return True

    try:
        pid = int(pid_path.read_text().strip())
        # signal 0 doesn't kill — just checks if process exists
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, ValueError):
        return False
    except PermissionError:
        # Process exists but we can't signal it (different user) — treat as alive
        return True


@main.command()
@click.argument("task_id")
def stop(task_id: str):
    """Stop a running task. Kills the process and preserves partial output."""
    import signal

    huginn_home = get_huginn_home()
    db = HuginnDB(huginn_home / "huginn.db")

    task = db.get_task(task_id)
    if not task:
        console.print(f"[red]Task '{task_id}' not found[/red]")
        sys.exit(1)

    if task["status"] in ("complete", "failed", "cancelled"):
        console.print(f"[yellow]Task '{task_id}' is already {task['status']}[/yellow]")
        db.close()
        return

    # Try to kill the process
    killed = False
    pid_path = huginn_home / "tasks" / task_id / "pid"
    if pid_path.exists():
        try:
            pid = int(pid_path.read_text().strip())
            # Send SIGTERM first (graceful), then SIGKILL if needed
            os.kill(pid, signal.SIGTERM)
            killed = True
            console.print(f"Sent SIGTERM to PID {pid}")
        except ProcessLookupError:
            console.print(f"[dim]Process {pid} already dead[/dim]")
        except PermissionError:
            console.print(f"[red]Cannot kill PID {pid} — permission denied[/red]")
            db.close()
            sys.exit(1)
        except ValueError:
            console.print(f"[red]Invalid PID file[/red]")
    else:
        console.print("[dim]No PID file — task was run in foreground[/dim]")

    # Update DB status
    from datetime import datetime, timezone
    db.update_task(
        task_id,
        status="cancelled",
        error_message="Stopped by user via huginn stop",
        completed_at=datetime.now(timezone.utc).isoformat(),
    )

    # Also mark any running stages as cancelled
    stages = db.get_stages(task_id)
    for s in stages:
        if s["status"] == "running":
            db.update_stage(
                s["id"],
                status="cancelled",
                error_message="Parent task stopped by user",
                completed_at=datetime.now(timezone.utc).isoformat(),
            )

    db.close()

    console.print(f"[green]Task {task_id} stopped[/green]")
    console.print(f"  Partial output preserved in: {huginn_home / 'tasks' / task_id}")
    if task["current_stage"] and task["current_stage"] > 0:
        console.print(f"  Completed stages: {task['current_stage']}/{task['total_stages']}")
        console.print(f"  [dim]Resume later with: huginn resume {task_id}[/dim]")


@main.command()
@click.argument("task_id")
@click.option("--follow", "-f", is_flag=True, help="Follow log output (like tail -f)")
@click.option("--lines", "-n", default=50, help="Number of lines to show")
def logs(task_id: str, follow: bool, lines: int):
    """Show logs for a background task."""
    import subprocess as sp

    huginn_home = get_huginn_home()
    log_path = huginn_home / "tasks" / task_id / "run.log"

    if not log_path.exists():
        console.print(f"[red]No log file for task '{task_id}'[/red]")
        console.print("[dim]Logs are only created for background tasks (--bg)[/dim]")
        sys.exit(1)

    if follow:
        sp.run(["tail", "-f", "-n", str(lines), str(log_path)])
    else:
        text = log_path.read_text()
        output_lines = text.splitlines()
        for line in output_lines[-lines:]:
            console.print(line)


# ---------------------------------------------------------------------------
# F065 — backends command
# ---------------------------------------------------------------------------


@main.command()
@click.option("--check", is_flag=True, help="Probe each backend to verify reachability")
def backends(check: bool):
    """List all configured backends with type, URL, and reachability."""
    from .ollama_client import check_backend_reachable

    config = load_config()
    backend_map = config.get("backends", {})
    default_name = config.get("default_backend", "")

    if not backend_map:
        console.print("[dim]No backends configured. Edit ~/.huginn/config.yaml[/dim]")
        return

    table = Table(title="Configured Backends")
    table.add_column("Name", min_width=12)
    table.add_column("Type", min_width=10)
    table.add_column("URL", min_width=30)
    if check:
        table.add_column("Reachable", min_width=10)
    table.add_column("Default", min_width=8)

    for name, cfg in backend_map.items():
        backend_type = cfg.get("type", "ollama")
        url = cfg.get("url", "-")
        is_default = "yes" if name == default_name else ""

        row = [name, backend_type, url]

        if check:
            full_cfg = dict(cfg)
            full_cfg.setdefault("type", "ollama")
            full_cfg["name"] = name
            reachable = check_backend_reachable(url, full_cfg)
            reach_str = "[green]yes[/green]" if reachable else "[red]no[/red]"
            row.append(reach_str)

        row.append("[green]yes[/green]" if is_default else "")
        table.add_row(*row)

    console.print(table)
    if not check:
        console.print("[dim]Pass --check to probe backend reachability[/dim]")


# ---------------------------------------------------------------------------
# F088 — cancel command (alias for stop)
# ---------------------------------------------------------------------------


@main.command()
@click.argument("task_id")
def cancel(task_id: str):
    """Cancel a running task. Alias for 'stop'."""
    import signal
    from datetime import datetime, timezone

    huginn_home = get_huginn_home()
    db = HuginnDB(huginn_home / "huginn.db")

    task = db.get_task(task_id)
    if not task:
        console.print(f"[red]Task '{task_id}' not found[/red]")
        sys.exit(1)

    if task["status"] in ("complete", "failed", "cancelled"):
        console.print(f"[yellow]Task '{task_id}' is already {task['status']}[/yellow]")
        db.close()
        return

    pid_path = huginn_home / "tasks" / task_id / "pid"
    if pid_path.exists():
        try:
            pid = int(pid_path.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            console.print(f"Sent SIGTERM to PID {pid}")
        except ProcessLookupError:
            console.print(f"[dim]Process already dead[/dim]")
        except PermissionError:
            console.print(f"[red]Cannot kill process — permission denied[/red]")
            db.close()
            sys.exit(1)
        except ValueError:
            console.print(f"[red]Invalid PID file[/red]")
    else:
        console.print("[dim]No PID file — task was run in foreground[/dim]")

    db.update_task(
        task_id,
        status="cancelled",
        error_message="Stopped by user via huginn cancel",
        completed_at=datetime.now(timezone.utc).isoformat(),
    )

    stages = db.get_stages(task_id)
    for s in stages:
        if s["status"] == "running":
            db.update_stage(
                s["id"],
                status="cancelled",
                error_message="Parent task cancelled by user",
                completed_at=datetime.now(timezone.utc).isoformat(),
            )

    db.close()
    console.print(f"[green]Task {task_id} cancelled[/green]")
    console.print(f"  Partial output preserved in: {huginn_home / 'tasks' / task_id}")
    if task["current_stage"] and task["current_stage"] > 0:
        console.print(f"  Completed stages: {task['current_stage']}/{task['total_stages']}")
        console.print(f"  [dim]Resume later with: huginn resume {task_id}[/dim]")


# ---------------------------------------------------------------------------
# F090 — batch command
# ---------------------------------------------------------------------------


@main.command()
@click.argument("pipeline_name")
@click.option("--input-dir", "-d", required=True, help="Directory of input files to process")
@click.option("--backend", "-b", default=None, help="Override backend for all tasks")
def batch(pipeline_name: str, input_dir: str, backend: str | None):
    """Submit multiple inputs to the same pipeline as background tasks."""
    from .background import launch_background

    input_p = Path(input_dir)
    if not input_p.exists() or not input_p.is_dir():
        console.print(f"[red]Input directory not found: {input_dir}[/red]")
        sys.exit(1)

    input_files = sorted(f for f in input_p.iterdir() if f.is_file())
    if not input_files:
        console.print(f"[yellow]No files found in: {input_dir}[/yellow]")
        return

    launched = []
    failed = []

    for f in input_files:
        try:
            result = launch_background(pipeline_name, f, backend)
            launched.append({"file": f.name, "task_id": result["task_id"], "pid": result["pid"]})
        except Exception as e:
            failed.append({"file": f.name, "error": str(e)})

    if launched:
        table = Table(title=f"Batch: {pipeline_name} — {len(launched)} task(s) launched")
        table.add_column("File", min_width=25)
        table.add_column("Task ID", width=10)
        table.add_column("PID", justify="right")

        for item in launched:
            table.add_row(item["file"], item["task_id"], str(item["pid"]))

        console.print(table)
        console.print(f"\n[green]{len(launched)} task(s) running in background[/green]")
        console.print("  Check status: huginn tasks")
        console.print("  View a task:  huginn status <task_id>")

    if failed:
        console.print(f"\n[red]{len(failed)} file(s) failed to launch:[/red]")
        for item in failed:
            console.print(f"  {item['file']}: {item['error']}")


# ---------------------------------------------------------------------------
# F094 + F095 — output command (with --download flag)
# ---------------------------------------------------------------------------


@main.command()
@click.argument("task_id")
@click.option(
    "--download",
    "-D",
    "download_path",
    default=None,
    is_flag=False,
    flag_value=".",
    help="Copy output files to current directory or specified path",
)
def output(task_id: str, download_path: str | None):
    """Retrieve and display the final output from a completed task.

    Pass --download to copy output files to the current directory,
    or --download /some/path to save to a specific location.
    """
    huginn_home = get_huginn_home()
    db = HuginnDB(huginn_home / "huginn.db")

    task = db.get_task(task_id)
    if not task:
        console.print(f"[red]Task '{task_id}' not found[/red]")
        db.close()
        sys.exit(1)

    db.close()

    if task["status"] != "complete":
        status_color = {
            "running": "yellow",
            "failed": "red",
            "queued": "blue",
            "cancelled": "dim",
            "interrupted": "magenta",
        }.get(task["status"], "white")
        console.print(
            f"[{status_color}]Task '{task_id}' is not complete "
            f"(status: {task['status']})[/{status_color}]"
        )
        if task["status"] == "running":
            console.print(f"  Wait for it to finish, then run: huginn output {task_id}")
        elif task["status"] in ("interrupted", "failed"):
            console.print(f"  Resume with: huginn resume {task_id}")
        return

    output_dir = huginn_home / "tasks" / task_id / "output"
    if not output_dir.exists():
        console.print(f"[red]Output directory not found: {output_dir}[/red]")
        sys.exit(1)

    output_files = sorted(f for f in output_dir.iterdir() if f.is_file())
    if not output_files:
        console.print(f"[yellow]No output files in: {output_dir}[/yellow]")
        return

    if download_path is not None:
        dest = Path(download_path).resolve()
        dest.mkdir(parents=True, exist_ok=True)
        copied = []
        for f in output_files:
            target = dest / f.name
            shutil.copy2(f, target)
            copied.append(str(target))
        console.print(f"[green]Copied {len(copied)} file(s) to {dest}:[/green]")
        for path in copied:
            console.print(f"  {path}")
        return

    # Print the main output file to stdout
    main_file = output_files[0]
    console.print(f"[bold]Output:[/bold] {main_file.name}  [dim]({main_file.stat().st_size:,} bytes)[/dim]")
    console.print()

    try:
        content = main_file.read_text()
        console.print(content)
    except UnicodeDecodeError:
        console.print(f"[dim](Binary file — use --download to save locally)[/dim]")

    if len(output_files) > 1:
        console.print(f"\n[dim]{len(output_files) - 1} additional file(s) in {output_dir}[/dim]")
        for f in output_files[1:]:
            console.print(f"  [dim]{f.name} ({f.stat().st_size:,} bytes)[/dim]")
        console.print(f"[dim]Use --download to copy all output files locally.[/dim]")


if __name__ == "__main__":
    main()
