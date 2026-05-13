"""Unit tests for huginn.tools — path validation, file_read, file_write."""

from pathlib import Path

import pytest

from huginn.tools import (
    ToolContext,
    execute_tool_call,
    file_read,
    file_write,
    validate_read_path,
    validate_write_path,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def dirs(tmp_path):
    """Create isolated input, files, and output directories."""
    input_dir = tmp_path / "input"
    files_dir = tmp_path / "files"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    files_dir.mkdir()
    output_dir.mkdir()
    return input_dir, files_dir, output_dir


@pytest.fixture()
def ctx(dirs):
    input_dir, files_dir, output_dir = dirs
    return ToolContext(
        input_dir=input_dir,
        files_dir=files_dir,
        output_dir=output_dir,
    )


# ---------------------------------------------------------------------------
# validate_read_path
# ---------------------------------------------------------------------------


class TestValidateReadPath:
    def test_rejects_empty_string(self, ctx):
        with pytest.raises(ValueError):
            validate_read_path("", ctx)

    def test_rejects_absolute_path(self, ctx):
        with pytest.raises(ValueError):
            validate_read_path("/etc/passwd", ctx)

    def test_rejects_dotdot_escape(self, ctx):
        """Path traversal via .. must be rejected."""
        with pytest.raises(ValueError):
            validate_read_path("../secret.txt", ctx)

    def test_rejects_nested_dotdot_escape(self, ctx):
        with pytest.raises(ValueError):
            validate_read_path("subdir/../../secret.txt", ctx)

    def test_resolves_file_in_input_dir(self, ctx, dirs):
        input_dir, _, _ = dirs
        (input_dir / "note.md").write_text("hello", encoding="utf-8")
        result = validate_read_path("note.md", ctx)
        assert result.name == "note.md"
        assert result.is_relative_to(input_dir)

    def test_resolves_file_in_files_dir(self, ctx, dirs):
        _, files_dir, _ = dirs
        (files_dir / "style.md").write_text("rules", encoding="utf-8")
        result = validate_read_path("style.md", ctx)
        assert result.name == "style.md"
        assert result.is_relative_to(files_dir)

    def test_raises_when_file_not_found_anywhere(self, ctx):
        with pytest.raises(ValueError, match="not found"):
            validate_read_path("missing.md", ctx)

    def test_input_dir_takes_priority_over_files_dir(self, ctx, dirs):
        """When the same filename exists in both dirs, input_dir wins."""
        input_dir, files_dir, _ = dirs
        (input_dir / "shared.md").write_text("from input", encoding="utf-8")
        (files_dir / "shared.md").write_text("from files", encoding="utf-8")
        result = validate_read_path("shared.md", ctx)
        assert result.is_relative_to(input_dir)

    def test_read_path_without_files_dir(self, dirs):
        input_dir, _, output_dir = dirs
        ctx_no_files = ToolContext(input_dir=input_dir, files_dir=None, output_dir=output_dir)
        (input_dir / "data.txt").write_text("data", encoding="utf-8")
        result = validate_read_path("data.txt", ctx_no_files)
        assert result.name == "data.txt"


# ---------------------------------------------------------------------------
# validate_write_path
# ---------------------------------------------------------------------------


class TestValidateWritePath:
    def test_rejects_empty_string(self, ctx):
        with pytest.raises(ValueError):
            validate_write_path("", ctx)

    def test_rejects_absolute_path(self, ctx):
        with pytest.raises(ValueError):
            validate_write_path("/tmp/evil.txt", ctx)

    def test_rejects_dotdot_escape(self, ctx):
        with pytest.raises(ValueError):
            validate_write_path("../escape.txt", ctx)

    def test_rejects_double_escape(self, ctx):
        with pytest.raises(ValueError):
            validate_write_path("subdir/../../escape.txt", ctx)

    def test_accepts_simple_filename(self, ctx, dirs):
        _, _, output_dir = dirs
        result = validate_write_path("output.md", ctx)
        # Should resolve inside output_dir
        assert result.is_relative_to(output_dir)

    def test_accepts_nested_filename(self, ctx, dirs):
        _, _, output_dir = dirs
        result = validate_write_path("subdir/output.json", ctx)
        assert result.is_relative_to(output_dir)

    def test_does_not_write_file(self, ctx):
        """validate_write_path only validates — it must not create the file."""
        result = validate_write_path("new-file.md", ctx)
        assert not result.exists()


# ---------------------------------------------------------------------------
# file_read
# ---------------------------------------------------------------------------


class TestFileRead:
    def test_reads_file_from_input_dir(self, ctx, dirs):
        input_dir, _, _ = dirs
        (input_dir / "data.md").write_text("hello world", encoding="utf-8")
        content = file_read("data.md", ctx)
        assert content == "hello world"

    def test_reads_file_from_files_dir(self, ctx, dirs):
        _, files_dir, _ = dirs
        (files_dir / "ref.md").write_text("reference content", encoding="utf-8")
        content = file_read("ref.md", ctx)
        assert content == "reference content"

    def test_raises_for_missing_file(self, ctx):
        with pytest.raises(ValueError):
            file_read("ghost.md", ctx)

    def test_raises_for_path_traversal(self, ctx):
        with pytest.raises(ValueError):
            file_read("../../etc/passwd", ctx)

    def test_raises_for_absolute_path(self, ctx):
        with pytest.raises(ValueError):
            file_read("/etc/passwd", ctx)


# ---------------------------------------------------------------------------
# file_write
# ---------------------------------------------------------------------------


class TestFileWrite:
    def test_writes_content_to_output_dir(self, ctx, dirs):
        _, _, output_dir = dirs
        result_msg = file_write("result.md", "my output", ctx)
        assert (output_dir / "result.md").read_text(encoding="utf-8") == "my output"

    def test_returns_confirmation_message(self, ctx):
        msg = file_write("out.txt", "data", ctx)
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_message_includes_byte_count(self, ctx):
        content = "hello"
        msg = file_write("out.txt", content, ctx)
        assert str(len(content)) in msg

    def test_raises_for_absolute_path(self, ctx):
        with pytest.raises(ValueError):
            file_write("/tmp/evil.txt", "bad", ctx)

    def test_raises_for_path_traversal(self, ctx):
        with pytest.raises(ValueError):
            file_write("../escape.txt", "bad", ctx)

    def test_creates_parent_subdirectory(self, ctx, dirs):
        _, _, output_dir = dirs
        file_write("subdir/output.json", '{"ok": true}', ctx)
        assert (output_dir / "subdir" / "output.json").exists()

    def test_overwrites_existing_file(self, ctx, dirs):
        _, _, output_dir = dirs
        (output_dir / "existing.txt").write_text("old content", encoding="utf-8")
        file_write("existing.txt", "new content", ctx)
        assert (output_dir / "existing.txt").read_text(encoding="utf-8") == "new content"


# ---------------------------------------------------------------------------
# execute_tool_call dispatch
# ---------------------------------------------------------------------------


class TestExecuteToolCall:
    def test_file_read_dispatch(self, ctx, dirs):
        input_dir, _, _ = dirs
        (input_dir / "hello.md").write_text("world", encoding="utf-8")
        result = execute_tool_call("file_read", {"path": "hello.md"}, ctx)
        assert result == "world"

    def test_file_write_dispatch(self, ctx, dirs):
        _, _, output_dir = dirs
        execute_tool_call("file_write", {"path": "out.md", "content": "written"}, ctx)
        assert (output_dir / "out.md").read_text(encoding="utf-8") == "written"

    def test_unknown_tool_returns_error_string(self, ctx):
        result = execute_tool_call("nonexistent_tool", {}, ctx)
        assert "Error" in result

    def test_path_traversal_returns_error_string(self, ctx):
        """execute_tool_call catches exceptions and returns error strings, not raises."""
        result = execute_tool_call("file_read", {"path": "/etc/passwd"}, ctx)
        assert "Error" in result

    def test_file_read_missing_file_returns_error_string(self, ctx):
        result = execute_tool_call("file_read", {"path": "missing.md"}, ctx)
        assert "Error" in result
