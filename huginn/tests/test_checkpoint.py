"""Unit tests for checkpoint save/load and resume logic in huginn.agent.

Tests verify that:
- _save_checkpoint writes a valid checkpoint.json to the output directory
- _load_checkpoint reads and returns the checkpoint data
- checkpoint/resume cycle preserves agent state (iterations, tokens, history)
- _stage_completed (in executor) correctly detects completed vs incomplete stages
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest

from huginn.agent import AgentContext, _load_checkpoint, _save_checkpoint
from huginn.executor import _stage_completed


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def output_dir(tmp_path):
    """A temporary output directory for each test."""
    d = tmp_path / "stage_output"
    d.mkdir()
    return d


@pytest.fixture()
def agent_ctx(output_dir):
    """A minimal AgentContext suitable for checkpoint tests."""
    return AgentContext(
        skill_prompt="Do the thing.",
        model="qwen3:8b",
        backend_url="http://localhost:11434",
        temperature=0.7,
        max_iterations=10,
        input_dir=output_dir / "input",
        output_dir=output_dir,
        files_dir=None,
        verification_rules=[],
        tools=[],
        iterations=0,
        total_tokens=0,
        history=[],
    )


# ---------------------------------------------------------------------------
# _save_checkpoint — writes checkpoint.json
# ---------------------------------------------------------------------------


class TestSaveCheckpoint:
    def test_checkpoint_file_created(self, agent_ctx, output_dir):
        """_save_checkpoint must write checkpoint.json to the output directory."""
        _save_checkpoint(agent_ctx)
        assert (output_dir / "checkpoint.json").exists()

    def test_checkpoint_is_valid_json(self, agent_ctx, output_dir):
        """The written file must be parseable JSON."""
        _save_checkpoint(agent_ctx)
        raw = (output_dir / "checkpoint.json").read_text(encoding="utf-8")
        data = json.loads(raw)
        assert isinstance(data, dict)

    def test_checkpoint_contains_iterations(self, agent_ctx, output_dir):
        agent_ctx.iterations = 3
        _save_checkpoint(agent_ctx)
        data = json.loads((output_dir / "checkpoint.json").read_text(encoding="utf-8"))
        assert data["iterations"] == 3

    def test_checkpoint_contains_total_tokens(self, agent_ctx, output_dir):
        agent_ctx.total_tokens = 512
        _save_checkpoint(agent_ctx)
        data = json.loads((output_dir / "checkpoint.json").read_text(encoding="utf-8"))
        assert data["total_tokens"] == 512

    def test_checkpoint_contains_history(self, agent_ctx, output_dir):
        agent_ctx.history = [{"iteration": 1, "tokens": 100}]
        _save_checkpoint(agent_ctx)
        data = json.loads((output_dir / "checkpoint.json").read_text(encoding="utf-8"))
        assert len(data["history"]) == 1

    def test_checkpoint_contains_saved_at_timestamp(self, agent_ctx, output_dir):
        _save_checkpoint(agent_ctx)
        data = json.loads((output_dir / "checkpoint.json").read_text(encoding="utf-8"))
        assert "saved_at" in data
        # Should be parseable as ISO timestamp
        datetime.fromisoformat(data["saved_at"])

    def test_checkpoint_creates_output_dir_if_missing(self, tmp_path):
        """_save_checkpoint should create output_dir if it does not yet exist."""
        nonexistent = tmp_path / "does_not_exist"
        ctx = AgentContext(
            skill_prompt="x",
            model="m",
            backend_url="http://localhost:11434",
            temperature=0.7,
            max_iterations=5,
            input_dir=nonexistent / "input",
            output_dir=nonexistent,
            files_dir=None,
            verification_rules=[],
        )
        _save_checkpoint(ctx)
        assert (nonexistent / "checkpoint.json").exists()

    def test_checkpoint_overwrites_previous_on_second_save(self, agent_ctx, output_dir):
        agent_ctx.iterations = 1
        _save_checkpoint(agent_ctx)
        agent_ctx.iterations = 5
        _save_checkpoint(agent_ctx)
        data = json.loads((output_dir / "checkpoint.json").read_text(encoding="utf-8"))
        assert data["iterations"] == 5


# ---------------------------------------------------------------------------
# _load_checkpoint — reads checkpoint.json back
# ---------------------------------------------------------------------------


class TestLoadCheckpoint:
    def test_returns_none_when_no_checkpoint(self, output_dir):
        """_load_checkpoint returns None when checkpoint.json is absent."""
        result = _load_checkpoint(output_dir)
        assert result is None

    def test_returns_dict_when_checkpoint_exists(self, output_dir):
        checkpoint_data = {"iterations": 2, "total_tokens": 300, "history": []}
        (output_dir / "checkpoint.json").write_text(
            json.dumps(checkpoint_data), encoding="utf-8"
        )
        result = _load_checkpoint(output_dir)
        assert isinstance(result, dict)

    def test_round_trip_preserves_iterations(self, agent_ctx, output_dir):
        """Checkpoint round-trip: save then load preserves iteration count."""
        agent_ctx.iterations = 7
        _save_checkpoint(agent_ctx)
        loaded = _load_checkpoint(output_dir)
        assert loaded["iterations"] == 7

    def test_round_trip_preserves_tokens(self, agent_ctx, output_dir):
        """Checkpoint round-trip: save then load preserves token count."""
        agent_ctx.total_tokens = 9999
        _save_checkpoint(agent_ctx)
        loaded = _load_checkpoint(output_dir)
        assert loaded["total_tokens"] == 9999

    def test_round_trip_preserves_history(self, agent_ctx, output_dir):
        """Checkpoint round-trip: save then load preserves conversation history."""
        agent_ctx.history = [
            {"iteration": 1, "tokens": 200, "output_preview": "Draft one"},
            {"iteration": 2, "tokens": 350, "output_preview": "Draft two"},
        ]
        _save_checkpoint(agent_ctx)
        loaded = _load_checkpoint(output_dir)
        assert len(loaded["history"]) == 2
        assert loaded["history"][0]["output_preview"] == "Draft one"

    def test_returns_none_for_corrupt_checkpoint(self, output_dir):
        """_load_checkpoint returns None rather than raising on corrupt JSON."""
        (output_dir / "checkpoint.json").write_text("{{not valid json}}", encoding="utf-8")
        result = _load_checkpoint(output_dir)
        assert result is None


# ---------------------------------------------------------------------------
# Resume logic — checkpoint restores state into AgentContext
# ---------------------------------------------------------------------------


class TestResumeFromCheckpoint:
    """
    These tests verify the resume behavior: when a checkpoint exists,
    the agent should restore iterations, tokens, and history from it.
    This mirrors what run_agent() does at startup.
    """

    def test_resume_restores_iterations(self, agent_ctx, output_dir):
        """After loading a checkpoint, the agent picks up from the saved iteration."""
        agent_ctx.iterations = 4
        agent_ctx.total_tokens = 800
        _save_checkpoint(agent_ctx)

        # Simulate what run_agent() does at startup with a fresh context
        fresh_ctx = AgentContext(
            skill_prompt="Do the thing.",
            model="qwen3:8b",
            backend_url="http://localhost:11434",
            temperature=0.7,
            max_iterations=10,
            input_dir=output_dir / "input",
            output_dir=output_dir,
            files_dir=None,
            verification_rules=[],
        )
        checkpoint = _load_checkpoint(fresh_ctx.output_dir)
        assert checkpoint is not None
        fresh_ctx.iterations = checkpoint.get("iterations", 0)
        fresh_ctx.total_tokens = checkpoint.get("total_tokens", 0)
        fresh_ctx.history = checkpoint.get("history", [])

        assert fresh_ctx.iterations == 4
        assert fresh_ctx.total_tokens == 800

    def test_resume_without_checkpoint_starts_at_zero(self, tmp_path):
        """When no checkpoint exists, agent state starts at zero (no resume)."""
        empty_dir = tmp_path / "empty_output"
        empty_dir.mkdir()
        checkpoint = _load_checkpoint(empty_dir)
        assert checkpoint is None


# ---------------------------------------------------------------------------
# _stage_completed detection
# ---------------------------------------------------------------------------


class TestStageCompleted:
    def test_empty_dir_is_not_completed(self, tmp_path):
        d = tmp_path / "stage_out"
        d.mkdir()
        assert _stage_completed(d) is False

    def test_nonexistent_dir_is_not_completed(self, tmp_path):
        assert _stage_completed(tmp_path / "ghost") is False

    def test_checkpoint_only_is_not_completed(self, tmp_path):
        """A directory with only checkpoint.json is not considered complete."""
        d = tmp_path / "stage_out"
        d.mkdir()
        (d / "checkpoint.json").write_text('{"iterations": 1}', encoding="utf-8")
        assert _stage_completed(d) is False

    def test_output_file_marks_stage_complete(self, tmp_path):
        """A directory with an output file (besides checkpoint.json) is complete."""
        d = tmp_path / "stage_out"
        d.mkdir()
        (d / "output.md").write_text("Final output here.", encoding="utf-8")
        assert _stage_completed(d) is True

    def test_output_and_checkpoint_is_complete(self, tmp_path):
        """Both output.md and checkpoint.json present — stage is complete."""
        d = tmp_path / "stage_out"
        d.mkdir()
        (d / "output.md").write_text("Done.", encoding="utf-8")
        (d / "checkpoint.json").write_text('{"iterations": 3}', encoding="utf-8")
        assert _stage_completed(d) is True
