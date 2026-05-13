"""Tool definitions, path validation, and execution for the agent loop.

Tools run where Huginn runs (local), not where the model runs (Ollama backend).
Path restrictions enforce that agents can only read from declared inputs and
write to their output directory.
"""

import html.parser
import json
import re
import subprocess
import urllib.request
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
    "git": {
        "type": "function",
        "function": {
            "name": "git",
            "description": (
                "Run a read-only git command in a repository. Supports: log, diff, show, "
                "status, blame, shortlog, rev-parse, branch --list, tag --list. "
                "Write operations (commit, push, checkout, reset) are blocked. "
                "Requires shell: true in skill constraints."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Git subcommand and arguments (e.g., 'log --oneline -20', 'diff HEAD~1', 'blame src/main.py')",
                    },
                    "repo_path": {
                        "type": "string",
                        "description": "Path to the git repository (default: current working directory)",
                    },
                },
                "required": ["command"],
            },
        },
    },
    "json_parse": {
        "type": "function",
        "function": {
            "name": "json_parse",
            "description": (
                "Parse a JSON string and extract data using a dot-notation path. "
                "Useful for extracting fields from JSON files or API responses. "
                "Returns the extracted value as a formatted string."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "json_string": {
                        "type": "string",
                        "description": "The JSON string to parse",
                    },
                    "path": {
                        "type": "string",
                        "description": "Dot-notation path to extract (e.g., 'data.items', 'results[0].name', '.' for root). Supports array indexing with [N].",
                    },
                },
                "required": ["json_string"],
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


# ---------------------------------------------------------------------------
# Git tool — read-only git operations
# ---------------------------------------------------------------------------

# Git subcommands that are safe (read-only)
_GIT_ALLOWED_SUBCOMMANDS = {
    "log", "diff", "show", "status", "blame", "shortlog",
    "rev-parse", "branch", "tag", "ls-files", "ls-tree",
    "cat-file", "describe", "name-rev", "rev-list",
}

# Git subcommands that mutate state — always blocked
_GIT_BLOCKED_SUBCOMMANDS = {
    "commit", "push", "pull", "fetch", "merge", "rebase", "reset",
    "checkout", "switch", "restore", "cherry-pick", "revert",
    "clean", "rm", "mv", "init", "clone", "remote", "stash",
    "bisect", "gc", "prune", "reflog", "filter-branch",
}


def git(command: str, repo_path: str | None = None) -> str:
    """Run a read-only git command and return output."""
    if not command or not command.strip():
        return "Error: git command must not be empty"

    parts = command.strip().split()
    subcommand = parts[0].lower()

    # Check subcommand allowlist
    if subcommand in _GIT_BLOCKED_SUBCOMMANDS:
        return f"Error: git {subcommand} is blocked — only read-only git operations are allowed"

    if subcommand not in _GIT_ALLOWED_SUBCOMMANDS:
        return (
            f"Error: git {subcommand} is not in the allowed list. "
            f"Allowed: {', '.join(sorted(_GIT_ALLOWED_SUBCOMMANDS))}"
        )

    # Block --exec and -c flags that could run arbitrary commands
    for arg in parts[1:]:
        if arg.startswith("--exec") or arg == "-c":
            return f"Error: flag '{arg}' is blocked for security"

    full_cmd = ["git"]
    if repo_path:
        full_cmd.extend(["-C", repo_path])
    full_cmd.extend(parts)

    try:
        proc = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = proc.stdout
        if proc.stderr:
            output += f"\n[stderr]\n{proc.stderr}"
        output = output.strip()
        if not output:
            return f"(git {subcommand} returned no output, exit code {proc.returncode})"
        # Truncate large outputs
        if len(output) > 15000:
            output = output[:15000] + "\n\n[truncated — output exceeded 15000 chars]"
        return output
    except subprocess.TimeoutExpired:
        return "Error: git command timed out after 30 seconds"
    except FileNotFoundError:
        return "Error: git is not installed or not in PATH"
    except Exception as e:
        return f"Error running git: {e}"


# ---------------------------------------------------------------------------
# JSON parse tool — extract data from JSON strings
# ---------------------------------------------------------------------------

def json_parse(json_string: str, path: str | None = None) -> str:
    """Parse JSON and optionally extract a value at a dot-notation path."""
    if not json_string or not json_string.strip():
        return "Error: json_string must not be empty"

    try:
        data = json.loads(json_string.strip())
    except json.JSONDecodeError as e:
        return f"Error: invalid JSON — {e}"

    if not path or path.strip() == "." or path.strip() == "":
        # Return the whole thing, formatted
        return json.dumps(data, indent=2, ensure_ascii=False)

    # Navigate the path: supports dot notation and array indexing
    # e.g., "data.items[0].name" → data → items → [0] → name
    current = data
    segments = _parse_json_path(path.strip())

    for segment in segments:
        try:
            if isinstance(segment, int):
                current = current[segment]
            elif isinstance(current, dict):
                if segment not in current:
                    available = ", ".join(current.keys()) if isinstance(current, dict) else str(type(current))
                    return f"Error: key '{segment}' not found. Available keys: {available}"
                current = current[segment]
            elif isinstance(current, list):
                return f"Error: expected dict at '{segment}' but got list with {len(current)} items"
            else:
                return f"Error: cannot navigate into {type(current).__name__} at '{segment}'"
        except (IndexError, KeyError, TypeError) as e:
            return f"Error: path navigation failed at '{segment}' — {e}"

    if isinstance(current, (dict, list)):
        return json.dumps(current, indent=2, ensure_ascii=False)
    return str(current)


def _parse_json_path(path: str) -> list[str | int]:
    """Parse a dot-notation path like 'data.items[0].name' into segments."""
    segments: list[str | int] = []
    for part in path.split("."):
        if not part:
            continue
        # Check for array indexing: items[0]
        match = re.match(r'^(\w+)\[(\d+)\]$', part)
        if match:
            segments.append(match.group(1))
            segments.append(int(match.group(2)))
        elif re.match(r'^\[\d+\]$', part):
            segments.append(int(part[1:-1]))
        else:
            segments.append(part)
    return segments


# ---------------------------------------------------------------------------
# Skill invoke tool — run a skill as a sub-agent
# ---------------------------------------------------------------------------

def skill_invoke(
    skill_name: str,
    input_text: str,
    ctx: ToolContext,
    backend_url: str | None = None,
    backend_config: dict | None = None,
) -> str:
    """Invoke a global skill as a sub-agent and return its output.

    Finds the skill in ~/.huginn/skills/, runs one iteration of the agent
    loop with the provided input_text, and returns the model's response.
    This is a lightweight sub-raven — no stage directory, no DB tracking.
    """
    from .config import get_huginn_home, load_config, get_backend_config, resolve_model_name
    from .ollama_client import complete, get_client

    if not skill_name or not skill_name.strip():
        return "Error: skill_name must not be empty"

    if not input_text or not input_text.strip():
        return "Error: input_text must not be empty"

    # Find the skill file
    huginn_home = get_huginn_home()
    skill_path = huginn_home / "skills" / f"{skill_name.strip()}.md"

    if not skill_path.exists():
        # Try without .md extension already in name
        skill_path = huginn_home / "skills" / skill_name.strip()
        if not skill_path.exists():
            available = [f.stem for f in (huginn_home / "skills").glob("*.md")]
            avail_str = ", ".join(available) if available else "(none)"
            return f"Error: skill '{skill_name}' not found in ~/.huginn/skills/. Available: {avail_str}"

    try:
        from .skill import parse_skill
        skill = parse_skill(skill_path)
    except Exception as e:
        return f"Error parsing skill '{skill_name}': {e}"

    # Resolve backend and model
    config = load_config()
    if backend_config is None:
        try:
            backend_name = skill.backend or config["default_backend"]
            backend_config = get_backend_config(config, backend_name)
        except Exception as e:
            return f"Error resolving backend: {e}"

    resolved_model = resolve_model_name(skill.model, backend_config)
    b_url = backend_url or backend_config.get("url", "")

    try:
        client = get_client(b_url, backend_config)
    except Exception as e:
        return f"Error creating client for skill backend: {e}"

    # Single-shot completion — no tool loop for sub-skills (keep it simple)
    result = complete(
        client=client,
        model=resolved_model,
        system_prompt=skill.system_prompt,
        user_message=input_text.strip(),
        temperature=skill.temperature,
    )

    if not result.success:
        return f"Error invoking skill '{skill_name}': {result.error}"

    return result.content


# Add skill_invoke to TOOL_DEFINITIONS
TOOL_DEFINITIONS["skill_invoke"] = {
    "type": "function",
    "function": {
        "name": "skill_invoke",
        "description": (
            "Invoke a global Huginn skill as a sub-agent. Sends input text to the "
            "skill's model with the skill's system prompt and returns the response. "
            "Skills are located in ~/.huginn/skills/. Use this to delegate subtasks "
            "to specialized skills without creating a full pipeline stage."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "Name of the skill file (without .md extension) in ~/.huginn/skills/",
                },
                "input_text": {
                    "type": "string",
                    "description": "The input text to send to the skill",
                },
            },
            "required": ["skill_name", "input_text"],
        },
    },
}


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
        elif name == "git":
            return git(
                arguments.get("command", ""),
                arguments.get("repo_path"),
            )
        elif name == "json_parse":
            return json_parse(
                arguments.get("json_string", ""),
                arguments.get("path"),
            )
        elif name == "skill_invoke":
            return skill_invoke(
                arguments.get("skill_name", ""),
                arguments.get("input_text", ""),
                ctx,
            )
        else:
            return f"Error: Unknown tool '{name}'"
    except Exception as e:
        return f"Error: {e}"
