# Huginn

*Send out the ravens. They come back with results.*

Huginn is a Python CLI for building and running autonomous LLM pipelines on local hardware. You write skill files that make cheap models smart on narrow tasks, chain them into pipelines, and run them in Docker sandboxes against your own Ollama backends. Frontier intelligence authors skills once; local models execute them repeatedly, for free.

## How It Works

A **pipeline** is a folder containing a `manifest.yaml` (the execution graph) and a set of **skill files** (markdown with YAML frontmatter). Each skill defines the system prompt, model, constraints, tools, and verification rules for one stage. Stages execute sequentially in isolated Docker containers, with each stage's output wiring into the next stage's input.

```
post-generator/
├── manifest.yaml           # 4 stages: analyze → draft → slop-filter → revise
├── skills/
│   ├── 01-analyze.md       # qwen2.5:7b — extract themes from source material
│   ├── 02-draft.md         # qwen2.5:7b — write post in Ken's voice
│   ├── 03-slop-filter.md   # qwen2.5:7b — detect AI slop patterns
│   └── 04-revise.md        # qwen2.5:7b — revise draft using slop report
└── files/
    └── voice-rules.md      # Reference doc: style guide, banned phrases
```

The agent loop inside each container is generic — observe, think (call Ollama), act, verify, checkpoint. The skill prompt is what differentiates behavior. If a run crashes mid-pipeline, it resumes from the last checkpoint.

## Prerequisites

- Python 3.11+
- Docker
- [Ollama](https://ollama.ai) running on at least one backend

## Install

```bash
cd huginn
pip install -e .
```

## Configuration

On first run, Huginn creates `~/.huginn/config.yaml`. Edit to point at your Ollama backends:

```yaml
backends:
  mac:
    url: http://localhost:11434
  i3:
    url: http://192.168.2.135:11434

default_backend: i3
max_parallel_workers: 2
task_timeout_minutes: 480
```

## Usage

```bash
# Run a pipeline
huginn run post-generator --input ./raw-notes.md

# Check task status
huginn status <task-id>

# List available pipelines
huginn pipelines

# List global skills
huginn skills

# List recent tasks
huginn tasks
huginn tasks --status failed --limit 5
```

## Sandboxing

Each stage runs in a Docker container with:

- Read-only input mount
- Read-write output mount (results go here only)
- Network restricted to Ollama API endpoint
- CPU/memory limits and timeout enforcement
- No host filesystem access beyond declared mounts

A misbehaving model can only produce output in its designated directory.

## Project Structure

```
huginn/                     # This repo
├── huginn/                 # Python package
│   ├── cli.py              # Click CLI (run, status, pipelines, skills, tasks)
│   ├── config.py           # Config loader (~/.huginn/config.yaml)
│   ├── manifest.py         # Manifest parser and pipeline discovery
│   ├── skill.py            # Skill file parser (YAML frontmatter + markdown)
│   ├── db.py               # SQLite (tasks, stages, runs)
│   ├── executor.py         # Stage executor (Docker lifecycle, chaining)
│   ├── agent.py            # Agent loop (observe → think → act → verify)
│   └── ollama_client.py    # Ollama API client (OpenAI-compatible)
├── pipelines/
│   └── post-generator/     # Starter pipeline
├── pyproject.toml
└── README.md
```

Runtime state lives in `~/.huginn/` (databases, task output, global skills).

## Roadmap

**Phase 1 (current) — Runner**: Execute hand-written pipelines. Sequential stages, Docker sandboxing, checkpoint/resume, verification.

**Phase 2 — Orchestrator**: `huginn create` uses Claude Opus to interactively design pipelines through a structured validation cycle (Research, Design, Threat Model, Build, Test).

**Phase 3 — Infrastructure**: Parallel execution, task queue, HTTP API, cron scheduling, conditional routing.

## Philosophy

The skill file is the product, not the model. A well-written skill encodes prompt engineering, domain expertise, and quality standards into a reusable artifact. Huginn lets you invest frontier-model intelligence into skill creation once, then run those skills on commodity local models indefinitely. Your data stays on your hardware. Your costs are fixed.
