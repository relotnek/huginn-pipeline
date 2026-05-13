"""Unit tests for huginn.manifest — pipeline manifest parsing and validation."""

from pathlib import Path

import pytest
import yaml

from huginn.manifest import Pipeline, StageDefinition, _validate_pipeline, list_pipelines, parse_manifest


# Path to the real post-generator pipeline
REPO_ROOT = Path(__file__).parent.parent
POST_GENERATOR_DIR = REPO_ROOT / "pipelines" / "post-generator"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_manifest(directory: Path, data: dict) -> None:
    (directory / "manifest.yaml").write_text(yaml.dump(data), encoding="utf-8")


def _write_skill(directory: Path, relative_path: str, name: str, model: str) -> None:
    skill_file = directory / relative_path
    skill_file.parent.mkdir(parents=True, exist_ok=True)
    skill_file.write_text(
        f"---\nname: {name}\nmodel: {model}\n---\n\nDo the task.\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# parse_manifest — real post-generator pipeline
# ---------------------------------------------------------------------------


class TestParseManifestRealPipeline:
    def test_pipeline_dir_exists(self):
        assert POST_GENERATOR_DIR.exists(), f"Pipeline dir missing: {POST_GENERATOR_DIR}"

    def test_parses_pipeline_name(self):
        pipeline = parse_manifest(POST_GENERATOR_DIR)
        assert pipeline.name == "post-generator"

    def test_parses_description(self):
        pipeline = parse_manifest(POST_GENERATOR_DIR)
        assert len(pipeline.description) > 0

    def test_correct_stage_count(self):
        pipeline = parse_manifest(POST_GENERATOR_DIR)
        # post-generator has 4 stages: analyze, draft, slop-filter, revise
        assert len(pipeline.stages) == 4

    def test_stage_names(self):
        pipeline = parse_manifest(POST_GENERATOR_DIR)
        names = [s.name for s in pipeline.stages]
        assert "analyze" in names
        assert "draft" in names
        assert "revise" in names

    def test_first_stage_input_is_pipeline_input(self):
        pipeline = parse_manifest(POST_GENERATOR_DIR)
        assert pipeline.stages[0].input == "$pipeline_input"

    def test_last_stage_has_list_input(self):
        """Stage 4 (revise) takes multiple inputs — draft.md and slop-report.json."""
        pipeline = parse_manifest(POST_GENERATOR_DIR)
        revise = pipeline.stages[3]
        assert isinstance(revise.input, list)
        assert len(revise.input) == 2

    def test_last_stage_input_contains_draft(self):
        pipeline = parse_manifest(POST_GENERATOR_DIR)
        revise = pipeline.stages[3]
        assert "draft.md" in revise.input

    def test_last_stage_input_contains_slop_report(self):
        pipeline = parse_manifest(POST_GENERATOR_DIR)
        revise = pipeline.stages[3]
        assert "slop-report.json" in revise.input

    def test_default_backend_set(self):
        pipeline = parse_manifest(POST_GENERATOR_DIR)
        assert pipeline.default_backend == "i3"

    def test_on_complete_output_file(self):
        pipeline = parse_manifest(POST_GENERATOR_DIR)
        assert pipeline.on_complete.get("output_file") == "final-post.md"

    def test_stage_models_resolved(self):
        pipeline = parse_manifest(POST_GENERATOR_DIR)
        for stage in pipeline.stages:
            assert stage.model  # No stage should have an empty model


# ---------------------------------------------------------------------------
# parse_manifest — synthetic pipeline in tmp_path
# ---------------------------------------------------------------------------


class TestParseManifestSynthetic:
    def test_parses_minimal_pipeline(self, tmp_path):
        _write_skill(tmp_path, "skills/stage1.md", "stage-one", "qwen3:8b")
        _write_manifest(tmp_path, {
            "name": "my-pipeline",
            "description": "Test pipeline",
            "version": "0.1",
            "stages": [
                {"name": "stage1", "skill": "skills/stage1.md", "model": "qwen3:8b",
                 "input": "$pipeline_input", "output": "out.md"},
            ],
        })
        pipeline = parse_manifest(tmp_path)
        assert pipeline.name == "my-pipeline"
        assert len(pipeline.stages) == 1

    def test_raises_for_missing_manifest(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_manifest(tmp_path)

    def test_raises_for_empty_manifest(self, tmp_path):
        (tmp_path / "manifest.yaml").write_text("", encoding="utf-8")
        with pytest.raises(ValueError, match="Empty manifest"):
            parse_manifest(tmp_path)

    def test_raises_for_no_stages(self, tmp_path):
        _write_manifest(tmp_path, {"name": "empty", "stages": []})
        with pytest.raises(ValueError, match="no stages"):
            parse_manifest(tmp_path)

    def test_raises_for_stage_missing_name(self, tmp_path):
        _write_manifest(tmp_path, {
            "name": "bad",
            "stages": [{"skill": "skills/s.md", "model": "qwen3:8b"}],
        })
        with pytest.raises(ValueError, match="missing 'name'"):
            parse_manifest(tmp_path)

    def test_raises_for_stage_missing_skill(self, tmp_path):
        _write_manifest(tmp_path, {
            "name": "bad",
            "stages": [{"name": "stage1", "model": "qwen3:8b"}],
        })
        with pytest.raises(ValueError, match="missing 'skill'"):
            parse_manifest(tmp_path)


# ---------------------------------------------------------------------------
# _validate_pipeline — wiring validation
# ---------------------------------------------------------------------------


class TestValidatePipelineWiring:
    def _make_pipeline(self, tmp_path, stages_data):
        """Helper: build a minimal Pipeline object without full parse."""
        skill_path = tmp_path / "skills" / "s.md"
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text("---\nname: s\nmodel: qwen3:8b\n---\n\nDo it.\n", encoding="utf-8")

        stages = []
        for sd in stages_data:
            stages.append(StageDefinition(
                name=sd["name"],
                skill_path="skills/s.md",
                model="qwen3:8b",
                backend=None,
                input=sd["input"],
                output=sd["output"],
            ))

        return Pipeline(
            name="test-pipe",
            description="",
            version="0.1",
            pipeline_dir=tmp_path,
            defaults={},
            stages=stages,
            on_complete={},
        )

    def test_valid_linear_wiring_passes(self, tmp_path):
        pipeline = self._make_pipeline(tmp_path, [
            {"name": "s1", "input": "$pipeline_input", "output": "s1-out.md"},
            {"name": "s2", "input": "s1-out.md", "output": "s2-out.md"},
        ])
        # Should not raise
        _validate_pipeline(pipeline)

    def test_bad_wiring_raises(self, tmp_path):
        """Stage 2 references a file that stage 1 does not produce."""
        pipeline = self._make_pipeline(tmp_path, [
            {"name": "s1", "input": "$pipeline_input", "output": "s1-out.md"},
            {"name": "s2", "input": "nonexistent-file.md", "output": "s2-out.md"},
        ])
        with pytest.raises(ValueError, match="validation failed"):
            _validate_pipeline(pipeline)

    def test_bad_wiring_error_names_missing_file(self, tmp_path):
        pipeline = self._make_pipeline(tmp_path, [
            {"name": "s1", "input": "$pipeline_input", "output": "s1-out.md"},
            {"name": "s2", "input": "ghost.md", "output": "s2-out.md"},
        ])
        with pytest.raises(ValueError, match="ghost.md"):
            _validate_pipeline(pipeline)


# ---------------------------------------------------------------------------
# list_pipelines
# ---------------------------------------------------------------------------


class TestListPipelines:
    def test_empty_dir_returns_empty(self, tmp_path):
        result = list_pipelines(tmp_path / "nonexistent")
        assert result == []

    def test_lists_valid_pipeline(self, tmp_path):
        pipe_dir = tmp_path / "my-pipe"
        pipe_dir.mkdir()
        _write_skill(pipe_dir, "skills/s.md", "s", "qwen3:8b")
        _write_manifest(pipe_dir, {
            "name": "my-pipe",
            "description": "A test pipeline",
            "stages": [
                {"name": "s", "skill": "skills/s.md", "model": "qwen3:8b",
                 "input": "$pipeline_input", "output": "out.md"},
            ],
        })
        result = list_pipelines(tmp_path)
        assert len(result) == 1
        assert result[0]["name"] == "my-pipe"

    def test_invalid_pipeline_returned_with_error(self, tmp_path):
        bad_dir = tmp_path / "broken"
        bad_dir.mkdir()
        (bad_dir / "manifest.yaml").write_text("", encoding="utf-8")
        result = list_pipelines(tmp_path)
        assert "ERROR" in result[0]["description"]
