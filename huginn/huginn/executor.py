"""Pipeline executor — runs stages in sequence, wires outputs to inputs."""

import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agent import AgentContext, AgentResult, run_agent
from .config import get_backend_url, get_huginn_home, load_config
from .db import HuginnDB
from .manifest import Pipeline, StageDefinition, parse_manifest
from .ollama_client import check_backend_reachable, check_model_available, get_client
from .skill import parse_skill


def execute_pipeline(
    pipeline_name: str,
    input_path: Path,
    backend_override: str | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """Execute a pipeline end-to-end. Returns task result dict."""
    config = load_config()
    huginn_home = get_huginn_home()
    db = HuginnDB(huginn_home / "huginn.db")

    # Find and parse pipeline
    pipeline_dir = huginn_home / "pipelines" / pipeline_name
    if not pipeline_dir.exists():
        raise FileNotFoundError(
            f"Pipeline '{pipeline_name}' not found at {pipeline_dir}"
        )

    pipeline = parse_manifest(pipeline_dir)

    # Create task directory
    task_id = db.create_task(
        pipeline_name=pipeline.name,
        input_path=str(input_path),
        output_path="",  # Set after creation
        total_stages=len(pipeline.stages),
    )

    task_dir = huginn_home / "tasks" / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "input").mkdir(exist_ok=True)
    (task_dir / "output").mkdir(exist_ok=True)
    (task_dir / "stages").mkdir(exist_ok=True)

    # Copy input file(s) to task input directory
    if input_path.is_file():
        shutil.copy2(input_path, task_dir / "input" / input_path.name)
    elif input_path.is_dir():
        shutil.copytree(input_path, task_dir / "input", dirs_exist_ok=True)

    db.update_task(task_id, output_path=str(task_dir / "output"))

    # Write task metadata
    meta = {
        "task_id": task_id,
        "pipeline": pipeline.name,
        "input": str(input_path),
        "total_stages": len(pipeline.stages),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "stages": [],
    }

    _log(f"Task {task_id} — running pipeline '{pipeline.name}' ({len(pipeline.stages)} stages)", verbose)
    db.update_task(task_id, status="running", started_at=datetime.now(timezone.utc).isoformat())

    # Execute stages
    start_time = time.time()

    for i, stage_def in enumerate(pipeline.stages):
        stage_dir = task_dir / "stages" / f"{i:02d}-{stage_def.name}"
        stage_input_dir = stage_dir / "input"
        stage_output_dir = stage_dir / "output"
        stage_files_dir = stage_dir / "files"

        stage_input_dir.mkdir(parents=True, exist_ok=True)
        stage_output_dir.mkdir(parents=True, exist_ok=True)

        # Check if stage already completed (resume support)
        if _stage_completed(stage_output_dir):
            _log(f"  Stage {i + 1}/{len(pipeline.stages)} '{stage_def.name}' — already complete, skipping", verbose)
            meta["stages"].append({"name": stage_def.name, "status": "skipped (cached)"})
            db.update_task(task_id, current_stage=i + 1)
            continue

        _log(f"  Stage {i + 1}/{len(pipeline.stages)} '{stage_def.name}' ({stage_def.model})...", verbose)

        # Resolve backend
        backend_name = backend_override or stage_def.backend or pipeline.default_backend or config["default_backend"]
        backend_url = get_backend_url(config, backend_name)

        # Check backend reachability
        if not check_backend_reachable(backend_url):
            error = f"Backend '{backend_name}' ({backend_url}) is unreachable"
            _fail_task(db, task_id, meta, task_dir, error)
            return {"task_id": task_id, "status": "failed", "error": error}

        # Check model availability
        client = get_client(backend_url)
        if not check_model_available(client, stage_def.model):
            error = (
                f"Model '{stage_def.model}' not available on '{backend_name}'. "
                f"Pull it with: docker exec -it ollama ollama pull {stage_def.model}"
            )
            _fail_task(db, task_id, meta, task_dir, error)
            return {"task_id": task_id, "status": "failed", "error": error}

        # Wire inputs
        _wire_stage_inputs(stage_def, stage_input_dir, task_dir, pipeline, i)

        # Mount reference files
        if stage_def.files:
            stage_files_dir.mkdir(parents=True, exist_ok=True)
            for f in stage_def.files:
                src = pipeline.pipeline_dir / f
                if src.exists():
                    shutil.copy2(src, stage_files_dir / src.name)

        # Parse skill
        skill_path = pipeline.pipeline_dir / stage_def.skill_path
        skill = parse_skill(skill_path)

        # Create stage record in DB
        stage_id = db.create_stage(
            task_id=task_id,
            stage_index=i,
            stage_name=stage_def.name,
            skill_name=skill.name,
            model=stage_def.model,
            backend=backend_name,
        )
        db.update_stage(stage_id, status="running", started_at=datetime.now(timezone.utc).isoformat())

        # Merge verification rules from both manifest and skill
        verification = stage_def.verification + skill.verification

        # Build agent context and run
        ctx = AgentContext(
            skill_prompt=skill.system_prompt,
            model=stage_def.model,
            backend_url=backend_url,
            temperature=skill.temperature,
            max_iterations=skill.max_iterations,
            input_dir=stage_input_dir,
            output_dir=stage_output_dir,
            files_dir=stage_files_dir if stage_def.files else None,
            verification_rules=verification,
            timeout_minutes=stage_def.timeout_minutes,
        )

        result = run_agent(ctx)

        # Update DB
        db.update_stage(
            stage_id,
            status="complete" if result.success else "failed",
            completed_at=datetime.now(timezone.utc).isoformat(),
            iterations=result.iterations,
            verification_passed=1 if result.verification_passed else (0 if result.verification_passed is False else None),
            tokens_used=result.total_tokens,
            duration_seconds=result.duration_seconds,
            error_message=result.error,
        )

        stage_meta = {
            "name": stage_def.name,
            "model": stage_def.model,
            "backend": backend_name,
            "status": "complete" if result.success else "failed",
            "iterations": result.iterations,
            "tokens_used": result.total_tokens,
            "duration_seconds": result.duration_seconds,
            "verification_passed": result.verification_passed,
            "output_files": result.output_files,
            "error": result.error,
        }
        meta["stages"].append(stage_meta)

        if result.success:
            _log(
                f"    ✓ {result.duration_seconds}s, {result.iterations} iterations, "
                f"{result.total_tokens} tokens",
                verbose,
            )
        else:
            error = f"Stage '{stage_def.name}' failed: {result.error}"
            _log(f"    ✗ {error}", verbose)
            _fail_task(db, task_id, meta, task_dir, error)
            return {"task_id": task_id, "status": "failed", "error": error}

        db.update_task(task_id, current_stage=i + 1)

    # Pipeline complete — copy final output
    final_stage_dir = task_dir / "stages" / f"{len(pipeline.stages) - 1:02d}-{pipeline.stages[-1].name}"
    final_output_dir = final_stage_dir / "output"

    if final_output_dir.exists():
        for f in final_output_dir.iterdir():
            if f.is_file() and f.name != "checkpoint.json":
                shutil.copy2(f, task_dir / "output" / f.name)

    # Also copy the specific on_complete output if specified
    if pipeline.on_complete.get("output_file"):
        target = pipeline.on_complete["output_file"]
        # Search backwards through stages for the file
        for stage_def in reversed(pipeline.stages):
            idx = pipeline.stages.index(stage_def)
            candidate = task_dir / "stages" / f"{idx:02d}-{stage_def.name}" / "output" / target
            if candidate.exists():
                shutil.copy2(candidate, task_dir / "output" / target)
                break

    elapsed = time.time() - start_time
    meta["completed_at"] = datetime.now(timezone.utc).isoformat()
    meta["total_duration_seconds"] = round(elapsed, 2)
    meta["status"] = "complete"
    _save_meta(task_dir, meta)

    db.update_task(
        task_id,
        status="complete",
        completed_at=datetime.now(timezone.utc).isoformat(),
    )

    _log(f"  ✓ Pipeline complete in {round(elapsed, 1)}s — output at {task_dir / 'output'}", verbose)

    db.close()
    return {"task_id": task_id, "status": "complete", "output_dir": str(task_dir / "output")}


def _wire_stage_inputs(
    stage_def: StageDefinition,
    stage_input_dir: Path,
    task_dir: Path,
    pipeline: Pipeline,
    stage_index: int,
) -> None:
    """Copy the right files into a stage's input directory."""
    inputs = stage_def.input if isinstance(stage_def.input, list) else [stage_def.input]

    for inp in inputs:
        if inp == "$pipeline_input":
            # Copy from task input directory
            for f in (task_dir / "input").iterdir():
                if f.is_file():
                    shutil.copy2(f, stage_input_dir / f.name)
        else:
            # Find this file in a prior stage's output
            found = False
            for j in range(stage_index):
                prior_stage = pipeline.stages[j]
                prior_output_dir = task_dir / "stages" / f"{j:02d}-{prior_stage.name}" / "output"

                # Check for exact filename match
                candidate = prior_output_dir / inp
                if candidate.exists():
                    shutil.copy2(candidate, stage_input_dir / inp)
                    found = True
                    break

                # Also check for output.md/output.json (default agent output names)
                for default_name in ["output.md", "output.json"]:
                    candidate = prior_output_dir / default_name
                    if candidate.exists() and prior_stage.output == inp:
                        shutil.copy2(candidate, stage_input_dir / inp)
                        found = True
                        break
                if found:
                    break

            if not found:
                # Copy whatever the prior stage produced as a fallback
                if stage_index > 0:
                    prior_stage = pipeline.stages[stage_index - 1]
                    prior_output_dir = task_dir / "stages" / f"{stage_index - 1:02d}-{prior_stage.name}" / "output"
                    if prior_output_dir.exists():
                        for f in prior_output_dir.iterdir():
                            if f.is_file() and f.name != "checkpoint.json":
                                shutil.copy2(f, stage_input_dir / f.name)


def _stage_completed(output_dir: Path) -> bool:
    """Check if a stage has already completed (has output files beyond checkpoint)."""
    if not output_dir.exists():
        return False
    output_files = [f for f in output_dir.iterdir() if f.is_file() and f.name != "checkpoint.json"]
    return len(output_files) > 0


def _fail_task(db: HuginnDB, task_id: str, meta: dict, task_dir: Path, error: str) -> None:
    """Mark a task as failed."""
    meta["status"] = "failed"
    meta["error"] = error
    meta["completed_at"] = datetime.now(timezone.utc).isoformat()
    _save_meta(task_dir, meta)
    db.update_task(
        task_id,
        status="failed",
        error_message=error,
        completed_at=datetime.now(timezone.utc).isoformat(),
    )


def _save_meta(task_dir: Path, meta: dict) -> None:
    """Write task metadata to meta.json."""
    meta_path = task_dir / "meta.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _log(msg: str, verbose: bool) -> None:
    """Print if verbose."""
    if verbose:
        print(msg)
