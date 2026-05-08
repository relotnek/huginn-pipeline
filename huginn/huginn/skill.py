"""Skill file parser — reads YAML frontmatter + markdown body."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import frontmatter


REQUIRED_FIELDS = ["name", "model"]

OPTIONAL_DEFAULTS = {
    "backend": None,  # Falls back to pipeline default or global default
    "temperature": 0.7,
    "max_iterations": 10,
    "tools": ["file_read"],
    "constraints": {"network": False, "shell": False, "timeout_minutes": 60},
}


@dataclass
class Skill:
    """A parsed skill definition."""

    name: str
    model: str
    backend: str | None
    temperature: float
    max_iterations: int
    tools: list[str]
    constraints: dict[str, Any]
    system_prompt: str  # The markdown body — the actual intelligence
    verification: list[str]  # Verification rules parsed from the body
    source_path: Path | None = None

    @property
    def timeout_minutes(self) -> int:
        return self.constraints.get("timeout_minutes", 60)

    @property
    def network_allowed(self) -> bool:
        return self.constraints.get("network", False)

    @property
    def shell_allowed(self) -> bool:
        return self.constraints.get("shell", False)


def parse_skill(path: Path) -> Skill:
    """Parse a skill markdown file with YAML frontmatter."""
    if not path.exists():
        raise FileNotFoundError(f"Skill file not found: {path}")

    if not path.suffix == ".md":
        raise ValueError(f"Skill file must be .md: {path}")

    post = frontmatter.load(str(path))
    meta = dict(post.metadata)
    body = post.content.strip()

    # Validate required fields
    missing = [f for f in REQUIRED_FIELDS if f not in meta]
    if missing:
        raise ValueError(f"Skill '{path.name}' missing required fields: {', '.join(missing)}")

    # Merge with defaults
    constraints = dict(OPTIONAL_DEFAULTS["constraints"])
    if "constraints" in meta:
        constraints.update(meta["constraints"])

    # Parse verification rules from the body
    verification = _extract_verification(body)

    return Skill(
        name=meta["name"],
        model=meta["model"],
        backend=meta.get("backend"),
        temperature=meta.get("temperature", OPTIONAL_DEFAULTS["temperature"]),
        max_iterations=meta.get("max_iterations", OPTIONAL_DEFAULTS["max_iterations"]),
        tools=meta.get("tools", OPTIONAL_DEFAULTS["tools"]),
        constraints=constraints,
        system_prompt=body,
        verification=verification,
        source_path=path,
    )


def _extract_verification(body: str) -> list[str]:
    """Extract verification rules from the ## Verification section of the skill body."""
    lines = body.split("\n")
    in_verification = False
    rules = []

    for line in lines:
        stripped = line.strip()

        # Start capturing after ## Verification header
        if stripped.lower().startswith("## verification"):
            in_verification = True
            continue

        # Stop at next header
        if in_verification and stripped.startswith("## "):
            break

        # Capture numbered or bulleted items
        if in_verification and stripped:
            # Strip leading numbers, dashes, bullets
            clean = stripped.lstrip("0123456789.-) ").strip()
            if clean:
                rules.append(clean)

    return rules


def list_skills(skills_dir: Path) -> list[dict[str, str]]:
    """List all skill files in a directory with name and model."""
    skills = []
    if not skills_dir.exists():
        return skills

    for path in sorted(skills_dir.glob("*.md")):
        try:
            skill = parse_skill(path)
            skills.append({
                "name": skill.name,
                "model": skill.model,
                "backend": skill.backend or "default",
                "path": str(path),
            })
        except (ValueError, KeyError) as e:
            skills.append({
                "name": path.stem,
                "model": "ERROR",
                "backend": str(e),
                "path": str(path),
            })

    return skills
