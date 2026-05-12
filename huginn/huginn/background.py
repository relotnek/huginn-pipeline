"""Background pipeline execution — spawn detached subprocess."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .config import get_huginn_home
from .db import HuginnDB


def launch_background(
    pipeline_name: str,
    input_path: Path,
    backend_override: str | None = None,
) -> dict[str, Any]:
    """Create task record and spawn detached subprocess.

    Returns dict with task_id, log_path, and pid.
    """
    huginn_home = get_huginn_home()
    db = HuginnDB(huginn_home / "huginn.db")

    # Pre-create task so we have an ID before spawning
    task_id = db.create_task(
        pipeline_name=pipeline_name,
        input_path=str(input_path.resolve()),
        output_path="",
        total_stages=0,  # Updated by subprocess when it parses the manifest
        metadata=json.dumps({"background": True}),
    )
    db.close()

    # Set up task directory and log file
    task_dir = huginn_home / "tasks" / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    log_path = task_dir / "run.log"

    # Build subprocess command
    cmd = [
        sys.executable, "-m", "huginn.background",
        "--task-id", task_id,
        "--pipeline", pipeline_name,
        "--input", str(input_path.resolve()),
    ]
    if backend_override:
        cmd.extend(["--backend", backend_override])

    # Spawn fully detached — survives parent exit
    log_file = open(log_path, "w")
    proc = subprocess.Popen(
        cmd,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    # Write PID for status/cancel
    (task_dir / "pid").write_text(str(proc.pid))

    return {"task_id": task_id, "log_path": str(log_path), "pid": proc.pid}


def run_background_entry(
    task_id: str,
    pipeline_name: str,
    input_path: str,
    backend_override: str | None = None,
) -> None:
    """Entry point for the background subprocess. Runs pipeline to completion."""
    from .executor import execute_pipeline

    input_p = Path(input_path)
    try:
        result = execute_pipeline(
            pipeline_name=pipeline_name,
            input_path=input_p,
            backend_override=backend_override,
            verbose=True,
            task_id=task_id,
        )
        print(f"Pipeline complete: {result['status']}")
    except Exception as e:
        print(f"Pipeline failed: {e}")
        huginn_home = get_huginn_home()
        db = HuginnDB(huginn_home / "huginn.db")
        from datetime import datetime, timezone
        db.update_task(
            task_id,
            status="failed",
            error_message=str(e),
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Huginn background pipeline runner")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--pipeline", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--backend", default=None)
    args = parser.parse_args()

    run_background_entry(args.task_id, args.pipeline, args.input, args.backend)
