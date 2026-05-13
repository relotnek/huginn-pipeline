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

## How Tool Calling Works

The agent loop implements a multi-turn conversation with tool use:

```
1. Huginn sends system prompt + user message + tool definitions to model
2. Model responds with text and/or tool calls
3. For each tool call:
   a. Huginn validates the path/arguments
   b. Huginn executes the tool locally
   c. Result is appended to the conversation
4. Conversation (with tool results) is sent back to the model
5. Repeat until model responds without tool calls (up to 20 rounds)
```

This follows the [OpenAI function calling protocol](https://platform.openai.com/docs/guides/function-calling), which is supported by Ollama, OpenRouter, and most OpenAI-compatible endpoints.

## Declaring Tools in Manifests

Specify which tools a stage can use:

```yaml
stages:
  - name: analyze
    tools: [file_read]              # read-only access

  - name: draft
    tools: [file_read, file_write]  # read and write access
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

## Planned Tools

These tools are designed but not yet implemented:

| Tool | Description | Phase |
|------|-------------|-------|
| `web_search` | Search the web via SearXNG | Phase 2 |
| `web_fetch` | Fetch and extract content from URLs | Phase 2 |
| `shell` | Execute shell commands (permission-gated) | Phase 2 |

## Path Security Model

All file access is sandboxed per stage:

```
Stage working directory:
├── input/     ← file_read can access (read-only)
├── files/     ← file_read can access (read-only, reference docs)
└── output/    ← file_write can access (read-write)
```

- Absolute paths (`/etc/passwd`) are rejected
- Path traversal (`../../config.yaml`) is rejected
- Each stage can only see its own declared inputs
- Stages cannot read other stages' output directories directly
