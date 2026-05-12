# Huginn

*Send out the ravens. They come back with results.*

A skill-based LLM pipeline system for local and remote infrastructure.

## Install

```bash
cd huginn
pip install -e .
```

## Quick Start

```bash
# List available pipelines
huginn pipelines

# Run a pipeline
huginn run post-generator --input ./my-draft.md

# Run in background
huginn run post-generator --input ./my-draft.md --bg

# Check task status
huginn status <task-id>

# Follow background task logs
huginn logs <task-id> --follow

# List recent tasks
huginn tasks
```

## Configuration

On first run, Huginn creates `~/.huginn/config.yaml`. Edit to match your setup:

```yaml
backends:
  i3:
    type: ollama
    url: http://192.168.2.135:11434
  mac:
    type: ollama
    url: http://localhost:11434
  openrouter:
    type: openrouter
    url: https://openrouter.ai/api/v1
    api_key_env: OPENROUTER_API_KEY

default_backend: i3
max_parallel_workers: 2
task_timeout_minutes: 480
```

Backend types: `ollama` (local inference), `openrouter` (300+ cloud models), `openai_compatible` (any endpoint).

## Project Structure

```
~/.huginn/
├── config.yaml       # Backend endpoints, resource limits
├── huginn.db         # Task history and state
├── skills/           # Global reusable skill library
├── pipelines/        # Pipeline definitions (manifest + skills + files)
└── tasks/            # Task execution directories
```
