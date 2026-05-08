"""Agent loop — the generic worker that runs inside each stage.

This is the same code for every skill. The skill prompt is what makes
each stage behave differently. The loop implements:
observe → think → act → verify → checkpoint
"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ollama_client import CompletionResult, complete, get_client


@dataclass
class AgentContext:
    """Everything the agent needs to run a stage."""

    skill_prompt: str
    model: str
    backend_url: str
    temperature: float
    max_iterations: int
    input_dir: Path
    output_dir: Path
    files_dir: Path | None  # Reference files (read-only)
    verification_rules: list[str]
    timeout_minutes: int = 60

    # State tracking
    iterations: int = 0
    total_tokens: int = 0
    history: list[dict] = field(default_factory=list)


@dataclass
class AgentResult:
    """Result of running the agent loop."""

    success: bool
    output_files: list[str]
    iterations: int
    total_tokens: int
    duration_seconds: float
    verification_passed: bool | None
    error: str | None = None


def run_agent(ctx: AgentContext) -> AgentResult:
    """Run the agent loop for a single pipeline stage."""
    start_time = time.time()
    client = get_client(ctx.backend_url)

    # Check for checkpoint (resume support)
    checkpoint = _load_checkpoint(ctx.output_dir)
    if checkpoint:
        ctx.iterations = checkpoint.get("iterations", 0)
        ctx.total_tokens = checkpoint.get("total_tokens", 0)
        ctx.history = checkpoint.get("history", [])

    # Read inputs
    input_content = _read_directory(ctx.input_dir)
    files_content = _read_directory(ctx.files_dir) if ctx.files_dir else ""

    # Build the initial user message
    user_message = _build_user_message(input_content, files_content, ctx)

    verification_passed = None
    last_output = ""

    while ctx.iterations < ctx.max_iterations:
        # Check timeout
        elapsed = time.time() - start_time
        if elapsed > ctx.timeout_minutes * 60:
            return AgentResult(
                success=False,
                output_files=_list_output_files(ctx.output_dir),
                iterations=ctx.iterations,
                total_tokens=ctx.total_tokens,
                duration_seconds=round(elapsed, 2),
                verification_passed=verification_passed,
                error=f"Timed out after {ctx.timeout_minutes} minutes",
            )

        ctx.iterations += 1

        # THINK: Call the model
        result = complete(
            client=client,
            model=ctx.model,
            system_prompt=ctx.skill_prompt,
            user_message=user_message,
            temperature=ctx.temperature,
        )

        if not result.success:
            # Retry logic: try up to 3 times on failure
            retries = 0
            while not result.success and retries < 3:
                retries += 1
                time.sleep(2 ** retries)  # Exponential backoff
                result = complete(
                    client=client,
                    model=ctx.model,
                    system_prompt=ctx.skill_prompt,
                    user_message=user_message,
                    temperature=ctx.temperature,
                )

            if not result.success:
                return AgentResult(
                    success=False,
                    output_files=_list_output_files(ctx.output_dir),
                    iterations=ctx.iterations,
                    total_tokens=ctx.total_tokens,
                    duration_seconds=round(time.time() - start_time, 2),
                    verification_passed=None,
                    error=f"Model call failed after retries: {result.error}",
                )

        ctx.total_tokens += result.tokens_used
        last_output = result.content

        # ACT: Write the output
        _write_output(ctx.output_dir, last_output, ctx)

        # Record in history
        ctx.history.append({
            "iteration": ctx.iterations,
            "tokens": result.tokens_used,
            "seconds": result.duration_seconds,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "output_preview": last_output[:200],
        })

        # VERIFY: Check against verification rules
        if ctx.verification_rules:
            verification_passed, failures = _verify_output(last_output, ctx.verification_rules)

            if verification_passed:
                _save_checkpoint(ctx)
                break
            else:
                # Feed failures back into next iteration
                user_message = _build_revision_message(
                    input_content, files_content, last_output, failures, ctx
                )
                _save_checkpoint(ctx)
                continue
        else:
            # No verification rules — one pass and done
            verification_passed = None
            _save_checkpoint(ctx)
            break

    elapsed = time.time() - start_time

    return AgentResult(
        success=True,
        output_files=_list_output_files(ctx.output_dir),
        iterations=ctx.iterations,
        total_tokens=ctx.total_tokens,
        duration_seconds=round(elapsed, 2),
        verification_passed=verification_passed,
    )


def _read_directory(dir_path: Path) -> str:
    """Read all text files in a directory into a combined string."""
    if not dir_path or not dir_path.exists():
        return ""

    parts = []
    for f in sorted(dir_path.iterdir()):
        if f.is_file() and f.suffix in (".md", ".txt", ".json", ".yaml", ".yml", ".py", ".csv"):
            try:
                content = f.read_text(encoding="utf-8")
                parts.append(f"--- {f.name} ---\n{content}")
            except (UnicodeDecodeError, PermissionError):
                parts.append(f"--- {f.name} ---\n[Could not read file]")

    return "\n\n".join(parts)


def _build_user_message(
    input_content: str, files_content: str, ctx: AgentContext
) -> str:
    """Build the user message for the first iteration."""
    parts = []

    if input_content:
        parts.append(f"## Input\n\n{input_content}")

    if files_content:
        parts.append(f"## Reference Files\n\n{files_content}")

    parts.append("Please complete the task as described in your instructions.")

    return "\n\n".join(parts)


def _build_revision_message(
    input_content: str,
    files_content: str,
    last_output: str,
    failures: list[str],
    ctx: AgentContext,
) -> str:
    """Build a revision message when verification fails."""
    failure_text = "\n".join(f"- {f}" for f in failures)

    parts = [
        f"## Input\n\n{input_content}",
        f"## Your Previous Output\n\n{last_output}",
        f"## Verification Failures\n\nYour output failed these checks:\n{failure_text}",
        "Please revise your output to address all verification failures. "
        "Produce the complete revised output, not just the changes.",
    ]

    if files_content:
        parts.insert(1, f"## Reference Files\n\n{files_content}")

    return "\n\n".join(parts)


def _write_output(output_dir: Path, content: str, ctx: AgentContext) -> None:
    """Write agent output to the output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Determine output filename from context or default
    # The stage executor will have set up the expected output filename
    # For now, write to output.md as a default
    output_file = output_dir / "output.md"

    # If the content looks like JSON, use .json extension
    stripped = content.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
            output_file = output_dir / "output.json"
            content = json.dumps(parsed, indent=2)
        except json.JSONDecodeError:
            pass

    output_file.write_text(content, encoding="utf-8")


def _verify_output(output: str, rules: list[str]) -> tuple[bool, list[str]]:
    """Check output against verification rules. Returns (passed, failures)."""
    failures = []

    for rule in rules:
        rule_lower = rule.lower()

        # Word count checks
        if "words" in rule_lower and any(c.isdigit() for c in rule):
            words = len(output.split())
            # Extract number range from rule
            import re
            numbers = re.findall(r"\d+", rule)
            if len(numbers) >= 2:
                low, high = int(numbers[0]), int(numbers[1])
                if not (low <= words <= high):
                    failures.append(f"{rule} (actual: {words} words)")
            elif len(numbers) == 1:
                target = int(numbers[0])
                if "fewer" in rule_lower or "under" in rule_lower or "less" in rule_lower:
                    if words >= target:
                        failures.append(f"{rule} (actual: {words} words)")
                elif "more" in rule_lower or "over" in rule_lower or "at least" in rule_lower:
                    if words < target:
                        failures.append(f"{rule} (actual: {words} words)")

        # Banned phrase checks
        elif "no banned" in rule_lower or "banned phrase" in rule_lower:
            banned = [
                "leverage", "best practices", "robust", "seamless", "unlock value",
                "stakeholders", "at the end of the day", "delve", "straightforward",
                "genuinely", "game-changer", "navigate", "landscape",
            ]
            found = [w for w in banned if w.lower() in output.lower()]
            if found:
                failures.append(f"{rule} (found: {', '.join(found)})")

        # JSON validity check
        elif "valid json" in rule_lower:
            try:
                json.loads(output.strip())
            except json.JSONDecodeError:
                failures.append(f"{rule} (output is not valid JSON)")

        # Generic containment check
        elif "must contain" in rule_lower:
            # Extract what should be contained
            import re
            match = re.search(r"must contain ['\"](.+?)['\"]", rule, re.IGNORECASE)
            if match:
                expected = match.group(1)
                if expected.lower() not in output.lower():
                    failures.append(f"{rule}")

    passed = len(failures) == 0
    return passed, failures


def _save_checkpoint(ctx: AgentContext) -> None:
    """Save agent progress for resume."""
    checkpoint = {
        "iterations": ctx.iterations,
        "total_tokens": ctx.total_tokens,
        "history": ctx.history,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    checkpoint_path = ctx.output_dir / "checkpoint.json"
    ctx.output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")


def _load_checkpoint(output_dir: Path) -> dict | None:
    """Load checkpoint if it exists."""
    checkpoint_path = output_dir / "checkpoint.json"
    if checkpoint_path.exists():
        try:
            return json.loads(checkpoint_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, PermissionError):
            return None
    return None


def _list_output_files(output_dir: Path) -> list[str]:
    """List files in the output directory."""
    if not output_dir.exists():
        return []
    return [f.name for f in output_dir.iterdir() if f.is_file() and f.name != "checkpoint.json"]
