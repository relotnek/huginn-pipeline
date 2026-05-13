# Tools Reference

Tools are capabilities that agents can use during stage execution. The model generates tool calls (via the OpenAI function-calling protocol), Huginn executes them locally, and feeds results back to the model.

## Key Principle: Brain/Hands Separation

Tools run **where Huginn runs** (local machine), not where the model runs (backend). This means:

- Using OpenRouter? File reads/writes happen on your machine, not in the cloud.
- Using a remote Ollama server? Tools still execute locally.
- Your data stays on your hardware regardless of which backend does inference.

## Available Tools

### file_read

Read the contents of a file from the input directory or reference files directory.

```json
{
  "name": "file_read",
  "parameters": {
    "path": "input.md"
  }
}
```

**Path resolution order:**

1. Input directory (`stages/NN/input/`) — files wired from prior stages
2. Files directory (`stages/NN/files/`) — reference files declared in manifest

**Security:** Paths are validated against allowed directories. Absolute paths and `..` traversal are rejected.

### file_write

Write content to a file in the output directory.

```json
{
  "name": "file_write",
  "parameters": {
    "path": "analysis.json",
    "content": "{\"key\": \"value\"}"
  }
}
```

**Security:** Writes are restricted to the stage's output directory only. Absolute paths and `..` traversal are rejected.

### web_search

Search the web using DuckDuckGo. Returns titles, URLs, and snippets.

```json
{
  "name": "web_search",
  "parameters": {
    "query": "OpenSea SEC enforcement 2026",
    "max_results": 5
  }
}
```

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `query` | Yes | | The search query |
| `max_results` | No | 5 | Maximum number of results to return |

!!! warning "Requires `network: true`"
    The skill's constraints must allow network access. Stages with `network: false` (the default) cannot use web_search.

### web_fetch

Fetch a URL and return its text content with HTML stripped.

```json
{
  "name": "web_fetch",
  "parameters": {
    "url": "https://example.com/article"
  }
}
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `url` | Yes | The URL to fetch |

Returns the page content as plain text with HTML tags removed. Useful for reading articles, documentation, or API responses found via web_search.

!!! warning "Requires `network: true`"
    The skill's constraints must allow network access.

### shell

Execute a shell command and return its stdout/stderr.

```json
{
  "name": "shell",
  "parameters": {
    "command": "wc -l input.md"
  }
}
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `command` | Yes | The shell command to execute |

!!! danger "Requires `shell: true`"
    The skill's constraints must explicitly allow shell access. Stages with `shell: false` (the default) cannot use shell. Dangerous commands (e.g., `rm -rf /`, `mkfs`) are blocked regardless of constraint settings.

## How Tool Calling Works

The agent loop implements a multi-turn conversation with tool use:

```
1. Huginn sends system prompt + user message + tool definitions to model
2. Model responds with text and/or tool calls
3. For each tool call:
   a. Huginn validates the path/arguments
   b. Huginn checks the call against skill constraints
   c. Huginn executes the tool locally
   d. Result is appended to the conversation
4. Conversation (with tool results) is sent back to the model
5. Repeat until model responds without tool calls (up to 20 rounds)
```

This follows the [OpenAI function calling protocol](https://platform.openai.com/docs/guides/function-calling), which is supported by Ollama, OpenRouter, and most OpenAI-compatible endpoints.

## Output Contract

Understanding how stage output works is critical for writing correct skills:

- **Model returns text without using tools** → text is saved as `output.md` (or `output.json` if JSON)
- **Model uses `file_write` to create files** → those files ARE the output; the model's text response is saved as `agent-notes.md`
- **Model uses `file_read` only** → the model's text response is saved as `output.md`

!!! tip "Assembly/Report Stages"
    Final stages that consolidate prior outputs into a deliverable (e.g., a threat model report) must explicitly instruct the model: **"Output the COMPLETE document as your text response. Do NOT use file_write."** Without this instruction, models will often generate a verification checklist instead of the actual report.

## Declaring Tools in Manifests

Specify which tools a stage can use:

```yaml
stages:
  - name: analyze
    tools: [file_read]              # read-only access

  - name: draft
    tools: [file_read, file_write]  # read and write access

  - name: research
    tools: [file_read, web_search, web_fetch]  # web access
    constraints:
      network: true                 # required for web tools

  - name: process
    tools: [file_read, file_write, shell]  # shell access
    constraints:
      shell: true                   # required for shell tool
```

If `tools` is omitted, the default is `[file_read]`.

## Declaring Tools in Skills

Skills can also declare tools in their frontmatter:

```yaml
---
name: my-skill
tools: [file_read, file_write]
---
```

## Constraint Enforcement

The tool runtime enforces skill constraints before executing any tool call:

| Tool | Requires | Default |
|------|----------|---------|
| `file_read` | (always allowed) | - |
| `file_write` | (always allowed) | - |
| `web_search` | `network: true` | Blocked |
| `web_fetch` | `network: true` | Blocked |
| `shell` | `shell: true` | Blocked |

If a model tries to call a tool that's blocked by constraints, the tool returns an error message and the model can continue with other approaches.

## Path Security Model

All file access is sandboxed per stage:

```
Stage working directory:
├── input/     ← file_read can access (read-only)
├── files/     ← file_read can access (read-only, reference docs)
└── output/    ← file_write can access (read-write)
```

- Absolute paths (`/etc/passwd`) are rejected
- Path traversal (`../../config.yaml`) are rejected
- Each stage can only see its own declared inputs
- Stages cannot read other stages' output directories directly
