# Huginn

*Send out the ravens. They come back with results.*

A skill-based LLM pipeline system for local infrastructure.

## Install

```bash
cd huginn
pip install -e .
```

## Quick Start

```bash
# List available pipelines
huginn pipelines

# List available skills
huginn skills

# Run a pipeline
huginn run post-generator --input ./my-draft.md

# Check task status
huginn status <task-id>
```

## Configuration

On first run, Huginn creates `~/.huginn/config.yaml`. Edit to match your setup:

```yaml
backends:
  i3:
    url: http://192.168.2.135:11434
  mac:
    url: http://localhost:11434

default_backend: i3
max_parallel_workers: 2
task_timeout_minutes: 480
```

## Project Structure

```
~/.huginn/
├── config.yaml       # Backend endpoints, resource limits
├── huginn.db         # Task history and state
├── skills/           # Global reusable skill library
├── pipelines/        # Pipeline definitions (manifest + skills + files)
└── tasks/            # Task execution directories
```
