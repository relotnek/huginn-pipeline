# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Huginn is a Python CLI for building and running autonomous LLM pipelines on local hardware. Two parts:

1. **Runner** (Phase 1): Executes hand-written pipelines — sequential stages, each in a Docker sandbox, calling Ollama for local model inference. Checkpoint/resume, verification, stage chaining.
2. **Orchestrator** (Phase 2): Uses Claude Opus via Anthropic API to interactively design pipelines through a structured validation cycle (Research → Design → Threat Model → Build → Test).
3. **Infrastructure** (Phase 3): Parallel execution, task queue, HTTP API, cron scheduling, conditional routing.

Core insight: frontier intelligence authors skills (once), local models execute them (repeatedly, free). The skill file — not the model — is the product.

## Architecture

### Key Artifacts

- **Pipeline**: a folder with `manifest.yaml` (stage definitions, models, wiring), `skills/` (one markdown per stage), `prompts/`, `files/` (reference docs), `tools/`, `validation/`
- **Skill**: markdown file with YAML frontmatter (model, backend, temperature, tools, constraints) + markdown body (system prompt, verification rules). Skills make cheap models smart on narrow tasks.
- **Manifest**: YAML defining the execution graph — stages run sequentially, each stage's output wires to the next stage's input via declared file names
- **Agent Loop**: generic Python worker inside each Docker container — observe → think (call Ollama) → act → verify → checkpoint. Same code powers every stage; the skill prompt differentiates behavior.

### State Layout

```
~/.huginn/
├── huginn.db              # SQLite: tasks, stages, runs
├── config.yaml            # Ollama endpoints, API keys, resource limits
├── skills/                # Global reusable skill library
├── pipelines/{name}/      # Pipeline definitions (manifest + skills + files)
└── tasks/{task_id}/       # Per-task execution dirs with per-stage I/O
    ├── stages/{N}/input/  # Read-only mount for stage
    ├── stages/{N}/output/ # Read-write mount for stage
    └── meta.json          # Task status, timing, errors
```

### Docker Sandboxing (per stage)

- Input mounted read-only, output mounted read-write
- Network restricted to Ollama API endpoint only (unless skill explicitly allows)
- CPU/memory limits, timeout enforcement
- Container created per stage, removed after completion

### Infrastructure

- **Ollama backends**: MacBook Pro M3 Max (big models, localhost:11434) and i3 server "heimdall" (small models, 192.168.2.135:11434)
- **Models**: qwen3:8b (analysis), qwen3:30b-a3b (MoE workhorse), qwen3.6:27b (best prose, Mac only), nomic-embed-text (embeddings), qwen2.5:0.5b (fast classification)
- **Database**: SQLite with tables for tasks, stages, runs

## Technology Stack

- Python 3.11+ CLI application
- Docker for worker sandboxing
- Ollama (OpenAI-compatible API) for local model inference
- SQLite for task queue, run history, checkpoints
- Anthropic API (Claude Opus) for Orchestrator (Phase 2)

## Build & Development

**This is a greenfield project.** See `huginn-spec.md` for the full specification and `huginn-overview.md` for the design philosophy.

### Phase 1 Implementation Tasks (in order)

1. Project structure: CLI entry point, config loader, skill parser
2. config.yaml parser (endpoints, defaults, limits)
3. manifest.yaml parser with validation
4. Skill file parser (YAML frontmatter + markdown)
5. SQLite schema (tasks, stages, runs)
6. Worker Docker image (agent.py + tools.py)
7. Agent loop implementation
8. file_read and file_write tools with path restrictions
9. Ollama client (OpenAI-compatible, configurable endpoint)
10. Verification engine
11. Checkpoint/resume logic
12. Stage executor (container lifecycle)
13. Stage chaining (output → input wiring)
14. CLI commands: `huginn run`, `huginn status`, `huginn pipelines`, `huginn skills`
15. Timeout enforcement and container cleanup
16. Starter pipelines: post-generator, content-classifier, code-reviewer
17. End-to-end testing

## Design Principles

- **Skill is the product**: the system prompt, constraints, and verification rules are what make a 7B model perform — invest effort there
- **Never delete partial work**: on failure, preserve output and checkpoint for resume
- **Error recovery**: Ollama unreachable → retry 3x with backoff; model not loaded → suggest pull command; container OOM → fail stage, suggest smaller model; checkpoint corruption → restart stage, warn
- **Each stage is fully isolated**: can only see its declared inputs, reference files, and the Ollama API
