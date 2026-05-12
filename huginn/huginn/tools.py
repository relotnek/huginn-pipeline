"""Tool definitions, path validation, and execution for the agent loop.

Tools run where Huginn runs (local), not where the model runs (Ollama backend).
Path restrictions enforce that agents can only read from declared inputs and
write to their output directory.
"""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ToolContext:
    """Path restrictions for tool execution within a stage."""

    input_dir: Path
    files_dir: Path | None
    output_dir: Path


TOOL_DEFINITIONS: dict[str, dict] = {
    "file_read": {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": (
                "Read the contents of a file. You can read files from the input "
                "directory and reference files directory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Filename to read (e.g. 'input.md', 'style-guide.md')",
                    }
                },
                "required": ["path"],
            },
        },
    },
    "file_write": {
        "type": "function",
        "function": {
            "name": "file_write",
            "description": (
                "Write content to a file in the output directory. Use this to "
                "produce your results."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Filename to write (e.g. 'output.md', 'analysis.json')",
                    },
                    "content": {
                        "type": "string",
                        "description": "The full content to write to the file",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
}


def get_tool_definitions(tool_names: list[str]) -> list[dict]:
    """Return OpenAI-format tool definitions for the requested tool names."""
    return [TOOL_DEFINITIONS[name] for name in tool_names if name in TOOL_DEFINITIONS]


def validate_read_path(requested: str, ctx: ToolContext) -> Path:
    """Resolve a read path against allowed directories.

    Tries input_dir first, then files_dir. Rejects paths that escape
    the allowed directories via .. traversal or absolute paths.
    """
    if not requested or requested.startswith("/"):
        raise ValueError(f"Invalid path: {requested}")

    # Try input_dir first
    candidate = (ctx.input_dir / requested).resolve()
    if candidate.is_relative_to(ctx.input_dir.resolve()):
        if candidate.exists() and candidate.is_file():
            return candidate

    # Try files_dir if available
    if ctx.files_dir and ctx.files_dir.exists():
        candidate = (ctx.files_dir / requested).resolve()
        if candidate.is_relative_to(ctx.files_dir.resolve()):
            if candidate.exists() and candidate.is_file():
                return candidate

    raise ValueError(
        f"File '{requested}' not found in input or reference files directories"
    )


def validate_write_path(requested: str, ctx: ToolContext) -> Path:
    """Resolve a write path against the output directory only.

    Rejects paths that escape output_dir via .. traversal or absolute paths.
    """
    if not requested or requested.startswith("/"):
        raise ValueError(f"Invalid path: {requested}")

    candidate = (ctx.output_dir / requested).resolve()
    if not candidate.is_relative_to(ctx.output_dir.resolve()):
        raise ValueError(f"Path '{requested}' escapes the output directory")

    return candidate


def file_read(path: str, ctx: ToolContext) -> str:
    """Read a file from input or reference files directory."""
    resolved = validate_read_path(path, ctx)
    return resolved.read_text(encoding="utf-8")


def file_write(path: str, content: str, ctx: ToolContext) -> str:
    """Write a file to the output directory."""
    resolved = validate_write_path(path, ctx)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} bytes to {path}"


def execute_tool_call(name: str, arguments: dict, ctx: ToolContext) -> str:
    """Dispatch a tool call by name. Returns result string or error string."""
    try:
        if name == "file_read":
            return file_read(arguments.get("path", ""), ctx)
        elif name == "file_write":
            return file_write(
                arguments.get("path", ""),
                arguments.get("content", ""),
                ctx,
            )
        else:
            return f"Error: Unknown tool '{name}'"
    except Exception as e:
        return f"Error: {e}"
