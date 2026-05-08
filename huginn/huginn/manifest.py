"""Pipeline manifest parser — reads manifest.yaml and validates stage wiring."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .skill import parse_skill, Skill


@dataclass
class StageDefinition:
    """A single stage in a pipeline."""

    name: str
    skill_path: str  # Relative to pipeline dir
    model: str
    backend: str | None
    input: str | list[str]  # $pipeline_input or filename(s) from prior stages
    output: str  # Filename this stage produces
    files: list[str] = field(default_factory=list)  # Reference files to mount
    tools: list[str] = field(default_factory=lambda: ["file_read"])
    constraints: dict[str, Any] = field(default_factory=lambda: {"network": False, "shell": False})
    verification: list[str] = field(default_factory=list)
    timeout_minutes: int = 60


@dataclass
class Pipeline:
    """A parsed pipeline definition."""

    name: str
    description: str
    version: str
    pipeline_dir: Path
    defaults: dict[str, Any]
    stages: list[StageDefinition]
    on_complete: dict[str, Any]

    @property
    def default_backend(self) -> str | None:
        return self.defaults.get("backend")

    @property
    def default_timeout(self) -> int:
        return self.defaults.get("timeout_minutes", 60)


def parse_manifest(pipeline_dir: Path) -> Pipeline:
    """Parse a pipeline's manifest.yaml and validate it."""
    manifest_path = pipeline_dir / "manifest.yaml"

    if not manifest_path.exists():
        raise FileNotFoundError(f"No manifest.yaml found in {pipeline_dir}")

    with open(manifest_path) as f:
        raw = yaml.safe_load(f)

    if not raw:
        raise ValueError(f"Empty manifest: {manifest_path}")

    # Parse top-level fields
    name = raw.get("name", pipeline_dir.name)
    description = raw.get("description", "")
    version = raw.get("version", "0.1")
    defaults = raw.get("defaults", {})
    on_complete = raw.get("on_complete", {})

    # Parse stages
    raw_stages = raw.get("stages", [])
    if not raw_stages:
        raise ValueError(f"Pipeline '{name}' has no stages defined")

    stages = []
    for i, s in enumerate(raw_stages):
        if "name" not in s:
            raise ValueError(f"Stage {i + 1} in '{name}' is missing 'name'")
        if "skill" not in s:
            raise ValueError(f"Stage '{s['name']}' is missing 'skill'")

        # Resolve model: stage override > skill file > pipeline default
        model = s.get("model")
        backend = s.get("backend")

        # If model not specified in stage, try to get it from skill file
        if not model:
            skill_path = pipeline_dir / s["skill"]
            if skill_path.exists():
                try:
                    skill = parse_skill(skill_path)
                    model = skill.model
                    if not backend:
                        backend = skill.backend
                except Exception:
                    pass

        if not model:
            raise ValueError(
                f"Stage '{s['name']}' has no model specified "
                f"(not in stage definition or skill file)"
            )

        stage_input = s.get("input", "$pipeline_input" if i == 0 else None)
        if stage_input is None:
            # Default: use previous stage's output
            if i > 0:
                stage_input = stages[i - 1].output
            else:
                stage_input = "$pipeline_input"

        stage = StageDefinition(
            name=s["name"],
            skill_path=s["skill"],
            model=model,
            backend=backend,
            input=stage_input,
            output=s.get("output", f"{s['name']}-output.md"),
            files=s.get("files", []),
            tools=s.get("tools", ["file_read"]),
            constraints=s.get("constraints", {"network": False, "shell": False}),
            verification=s.get("verification", []),
            timeout_minutes=s.get("timeout_minutes", defaults.get("timeout_minutes", 60)),
        )
        stages.append(stage)

    pipeline = Pipeline(
        name=name,
        description=description,
        version=version,
        pipeline_dir=pipeline_dir,
        defaults=defaults,
        stages=stages,
        on_complete=on_complete,
    )

    # Validate
    _validate_pipeline(pipeline)

    return pipeline


def _validate_pipeline(pipeline: Pipeline) -> None:
    """Validate pipeline integrity — skill files exist, wiring makes sense."""
    errors = []

    # Track what outputs are available at each stage
    available_outputs = set()

    for i, stage in enumerate(pipeline.stages):
        # Check skill file exists
        skill_path = pipeline.pipeline_dir / stage.skill_path
        if not skill_path.exists():
            errors.append(f"Stage '{stage.name}': skill file not found: {stage.skill_path}")

        # Check reference files exist
        for f in stage.files:
            file_path = pipeline.pipeline_dir / f
            if not file_path.exists():
                errors.append(f"Stage '{stage.name}': reference file not found: {f}")

        # Check input wiring (skip $pipeline_input — that comes from the user)
        inputs = stage.input if isinstance(stage.input, list) else [stage.input]
        for inp in inputs:
            if inp == "$pipeline_input":
                continue
            if inp not in available_outputs:
                errors.append(
                    f"Stage '{stage.name}': references input '{inp}' "
                    f"which no prior stage produces. "
                    f"Available: {available_outputs or '{none yet}'}"
                )

        # Register this stage's output
        available_outputs.add(stage.output)

    if errors:
        error_text = "\n  ".join(errors)
        raise ValueError(f"Pipeline '{pipeline.name}' validation failed:\n  {error_text}")


def list_pipelines(pipelines_dir: Path) -> list[dict[str, str]]:
    """List all pipelines in a directory."""
    pipelines = []
    if not pipelines_dir.exists():
        return pipelines

    for path in sorted(pipelines_dir.iterdir()):
        manifest = path / "manifest.yaml"
        if path.is_dir() and manifest.exists():
            try:
                p = parse_manifest(path)
                pipelines.append({
                    "name": p.name,
                    "description": p.description,
                    "stages": len(p.stages),
                    "path": str(path),
                })
            except Exception as e:
                pipelines.append({
                    "name": path.name,
                    "description": f"ERROR: {e}",
                    "stages": 0,
                    "path": str(path),
                })

    return pipelines
