"""Tool runtime abstraction: separates tool execution from model inference.

ToolRegistry maps tool names to their OpenAI-format definitions and handler
functions. ToolRuntime wraps the registry with constraint enforcement and
optional database logging so each tool invocation is recorded.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .tools import (
    TOOL_DEFINITIONS,
    ToolContext,
    execute_tool_call,
    file_read,
    file_write,
    git,
    json_parse,
    shell,
    skill_invoke,
    web_fetch,
    web_search,
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

@dataclass
class _ToolEntry:
    name: str
    definition: dict          # OpenAI function-calling format
    handler: Callable         # callable(arguments: dict, ctx: ToolContext) -> str


class ToolRegistry:
    """Maps tool names to their definitions and handler callables."""

    def __init__(self):
        self._tools: dict[str, _ToolEntry] = {}

    def register_tool(
        self,
        name: str,
        definition: dict,
        handler: Callable,
    ) -> None:
        """Register a tool by name with its OpenAI-format definition and handler."""
        self._tools[name] = _ToolEntry(name=name, definition=definition, handler=handler)

    def get_tool(self, name: str) -> _ToolEntry | None:
        """Look up a registered tool by name. Returns None if not found."""
        return self._tools.get(name)

    def get_available_tools(self, tool_names: list[str]) -> list[dict]:
        """Return OpenAI-format tool definitions for the requested names."""
        return [
            self._tools[name].definition
            for name in tool_names
            if name in self._tools
        ]


def _make_file_read_handler(ctx_ref: list[ToolContext]) -> Callable:
    """Return a file_read handler that uses a ToolContext stored by reference."""
    def handler(arguments: dict, ctx: ToolContext) -> str:
        return file_read(arguments.get("path", ""), ctx)
    return handler


# Build the default global registry pre-populated with all known tools.
_DEFAULT_REGISTRY = ToolRegistry()

_DEFAULT_REGISTRY.register_tool(
    "file_read",
    TOOL_DEFINITIONS["file_read"],
    lambda args, ctx: file_read(args.get("path", ""), ctx),
)
_DEFAULT_REGISTRY.register_tool(
    "file_write",
    TOOL_DEFINITIONS["file_write"],
    lambda args, ctx: file_write(args.get("path", ""), args.get("content", ""), ctx),
)
_DEFAULT_REGISTRY.register_tool(
    "web_search",
    TOOL_DEFINITIONS["web_search"],
    lambda args, ctx: web_search(args.get("query", ""), args.get("max_results", 5)),
)
_DEFAULT_REGISTRY.register_tool(
    "web_fetch",
    TOOL_DEFINITIONS["web_fetch"],
    lambda args, ctx: web_fetch(args.get("url", "")),
)
_DEFAULT_REGISTRY.register_tool(
    "shell",
    TOOL_DEFINITIONS["shell"],
    lambda args, ctx: shell(args.get("command", ""), args.get("timeout", 30)),
)
_DEFAULT_REGISTRY.register_tool(
    "git",
    TOOL_DEFINITIONS["git"],
    lambda args, ctx: git(args.get("command", ""), args.get("repo_path")),
)
_DEFAULT_REGISTRY.register_tool(
    "json_parse",
    TOOL_DEFINITIONS["json_parse"],
    lambda args, ctx: json_parse(args.get("json_string", ""), args.get("path")),
)
_DEFAULT_REGISTRY.register_tool(
    "skill_invoke",
    TOOL_DEFINITIONS["skill_invoke"],
    lambda args, ctx: skill_invoke(args.get("skill_name", ""), args.get("input_text", ""), ctx),
)

# Public accessor so callers can grab the singleton registry.
tool_registry: ToolRegistry = _DEFAULT_REGISTRY


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------

# Tools that require network: true (includes skill_invoke since it calls a backend)
_NETWORK_TOOLS = {"web_search", "web_fetch", "skill_invoke"}
# Tools that require shell: true
_SHELL_TOOLS = {"shell", "git"}


@dataclass
class SkillConstraints:
    """Parsed skill-level permission flags."""

    network_allowed: bool = False
    shell_allowed: bool = False


def _check_constraint(
    tool_name: str,
    constraints: SkillConstraints,
) -> str | None:
    """Return an error string if the tool is blocked, else None (allowed)."""
    if tool_name in _NETWORK_TOOLS and not constraints.network_allowed:
        return (
            f"Permission denied: tool '{tool_name}' requires 'network: true' "
            "in the skill constraints but network access is not allowed."
        )
    if tool_name in _SHELL_TOOLS and not constraints.shell_allowed:
        return (
            f"Permission denied: tool '{tool_name}' requires 'shell: true' "
            "in the skill constraints but shell access is not allowed."
        )
    return None


# ---------------------------------------------------------------------------
# ToolRuntime
# ---------------------------------------------------------------------------

class ToolRuntime:
    """Executes tools with constraint enforcement and optional DB logging.

    Usage::

        runtime = ToolRuntime(
            tool_ctx=ctx,
            constraints=SkillConstraints(network_allowed=True),
            db=huginn_db,          # optional — pass None to skip logging
            stage_id="abc123",     # required when db is provided
        )
        result = runtime.execute("web_search", {"query": "python type hints"})
    """

    def __init__(
        self,
        tool_ctx: ToolContext,
        constraints: SkillConstraints | None = None,
        registry: ToolRegistry | None = None,
        db: Any | None = None,
        stage_id: str | None = None,
        iteration: int = 0,
    ) -> None:
        self._tool_ctx = tool_ctx
        self._constraints = constraints or SkillConstraints()
        self._registry = registry or tool_registry
        self._db = db
        self._stage_id = stage_id
        self._iteration = iteration

    def execute(self, tool_name: str, arguments: dict) -> str:
        """Execute a tool call, enforcing constraints and logging the result."""
        # --- Constraint enforcement ---
        denied = _check_constraint(tool_name, self._constraints)
        if denied:
            self._record_tool_log(tool_name, arguments, denied, 0.0)
            return denied

        entry = self._registry.get_tool(tool_name)
        if entry is None:
            error = f"Error: Unknown tool '{tool_name}'"
            self._record_tool_log(tool_name, arguments, error, 0.0)
            return error

        # --- Execute with timing ---
        start = time.monotonic()
        try:
            result = entry.handler(arguments, self._tool_ctx)
        except Exception as exc:
            result = f"Error: {exc}"
        duration = time.monotonic() - start

        # --- Log run to DB ---
        self._record_tool_log(tool_name, arguments, result, duration)

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _record_tool_log(
        self,
        tool_name: str,
        arguments: dict,
        result: str,
        duration: float,
    ) -> None:
        """Persist a tool_log entry to the runs table when a DB is available."""
        if self._db is None or self._stage_id is None:
            return

        import json as _json

        # Truncate large results to avoid bloating the DB
        _MAX_RESULT = 2000
        logged_result = result if len(result) <= _MAX_RESULT else result[:_MAX_RESULT] + "…[truncated]"

        try:
            args_str = _json.dumps(arguments, ensure_ascii=False)
        except Exception:
            args_str = str(arguments)

        action = f"tool:{tool_name} args={args_str}"

        try:
            self._db.log_run(
                stage_id=self._stage_id,
                iteration=self._iteration,
                action=action,
                result=logged_result,
                tokens_used=0,
                duration_seconds=round(duration, 4),
            )
        except Exception:
            # Never let logging errors break tool execution
            pass
