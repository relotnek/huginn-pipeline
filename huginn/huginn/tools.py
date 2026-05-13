"""Tool definitions, path validation, and execution for the agent loop.

Tools run where Huginn runs (local), not where the model runs (Ollama backend).
Path restrictions enforce that agents can only read from declared inputs and
write to their output directory.
"""

import html.parser
import json
import subprocess
import urllib.request
import urllib.error
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ToolContext:
    """Path restrictions for tool execution within a stage."""

    input_dir: Path
    files_dir: Path | None
    output_dir: Path


# Dangerous command fragments that are never allowed in shell tool
_SHELL_BLOCKLIST = [
    "rm -rf /",
    "mkfs",
    "dd if=",
    ":(){ :|:& };:",
]


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
    "web_search": {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web using DuckDuckGo. Returns titles, URLs, and snippets. "
                "Requires network: true in the skill constraints."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default 5)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    "web_fetch": {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": (
                "Fetch the text content of a URL. HTML is stripped; response is "
                "truncated to 10000 chars. Requires network: true in skill constraints."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch",
                    }
                },
                "required": ["url"],
            },
        },
    },
    "shell": {
        "type": "function",
        "function": {
            "name": "shell",
            "description": (
                "Run a shell command and return stdout + stderr. "
                "Requires shell: true in skill constraints. "
                "Dangerous commands (rm -rf /, mkfs, etc.) are blocked."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to run",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default 30)",
                    },
                },
                "required": ["command"],
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


def web_search(query: str, max_results: int = 5) -> str:
    """Search the web via DuckDuckGo. Returns formatted results."""
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return "Error: duckduckgo-search package not installed. Run: pip install duckduckgo-search"

    if not query or not query.strip():
        return "Error: query must not be empty"

    max_results = max(1, min(int(max_results), 20))

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query.strip(), max_results=max_results))
    except Exception as e:
        return f"Error during search: {e}"

    if not results:
        return "No results found."

    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "(no title)")
        url = r.get("href", "")
        snippet = r.get("body", "")
        lines.append(f"{i}. {title}\n   URL: {url}\n   {snippet}")

    return "\n\n".join(lines)


class _HTMLTextExtractor(html.parser.HTMLParser):
    """Minimal HTML parser that extracts visible text."""

    _SKIP_TAGS = {"script", "style", "noscript", "head"}

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in self._SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)

    def handle_data(self, data):
        if self._skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self._parts.append(stripped)

    def get_text(self) -> str:
        return " ".join(self._parts)


def web_fetch(url: str) -> str:
    """Fetch a URL and return stripped text content, truncated to 10000 chars."""
    if not url or not url.strip():
        return "Error: url must not be empty"

    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return "Error: url must start with http:// or https://"

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Huginn/0.1 (+https://github.com/asgarddev/huginn)"},
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            content_type = response.headers.get("Content-Type", "")
            raw = response.read(200_000)  # cap raw read at 200 KB
    except urllib.error.URLError as e:
        return f"Error fetching URL: {e}"
    except Exception as e:
        return f"Error: {e}"

    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        return "Error: could not decode response"

    # Strip HTML if applicable
    if "html" in content_type.lower() or text.lstrip().startswith("<"):
        extractor = _HTMLTextExtractor()
        try:
            extractor.feed(text)
            text = extractor.get_text()
        except Exception:
            pass  # fall through with raw text

    # Collapse whitespace and truncate
    import re
    text = re.sub(r"\s{3,}", "\n\n", text)
    if len(text) > 10000:
        text = text[:10000] + "\n\n[truncated]"

    return text


def shell(command: str, timeout: int = 30) -> str:
    """Run a shell command and return combined stdout + stderr output."""
    if not command or not command.strip():
        return "Error: command must not be empty"

    # Security: reject known destructive patterns
    for blocked in _SHELL_BLOCKLIST:
        if blocked in command:
            return f"Error: command blocked by security policy (contains '{blocked}')"

    timeout = max(1, min(int(timeout), 300))

    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output_parts = []
        if proc.stdout:
            output_parts.append(proc.stdout)
        if proc.stderr:
            output_parts.append(f"[stderr]\n{proc.stderr}")
        combined = "\n".join(output_parts).strip()
        return combined if combined else f"(exit code {proc.returncode}, no output)"
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout} seconds"
    except Exception as e:
        return f"Error running command: {e}"


def execute_tool_call(name: str, arguments: dict, ctx: ToolContext) -> str:
    """Dispatch a tool call by name. Returns result string or error string.

    Note: network and shell constraint enforcement is handled by ToolRuntime.
    This function executes without constraint checks — callers using ToolRuntime
    will have constraints enforced before reaching here.
    """
    try:
        if name == "file_read":
            return file_read(arguments.get("path", ""), ctx)
        elif name == "file_write":
            return file_write(
                arguments.get("path", ""),
                arguments.get("content", ""),
                ctx,
            )
        elif name == "web_search":
            return web_search(
                arguments.get("query", ""),
                arguments.get("max_results", 5),
            )
        elif name == "web_fetch":
            return web_fetch(arguments.get("url", ""))
        elif name == "shell":
            return shell(
                arguments.get("command", ""),
                arguments.get("timeout", 30),
            )
        else:
            return f"Error: Unknown tool '{name}'"
    except Exception as e:
        return f"Error: {e}"
