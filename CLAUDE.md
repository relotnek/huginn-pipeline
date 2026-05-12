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

- **Backends**: MacBook Pro M3 Max (type: ollama, localhost:11434), i3 server "heimdall" (type: ollama, 192.168.2.135:11434), OpenRouter (type: openrouter, 300+ cloud models via API key)
- **Models**: qwen3:8b (analysis), qwen3:30b-a3b (MoE workhorse), qwen3.6:27b (best prose, Mac only), nomic-embed-text (embeddings), qwen2.5:0.5b (fast classification). OpenRouter: anthropic/claude-sonnet-4.6, meta-llama/llama-3.3-70b, etc.
- **Database**: SQLite with tables for tasks, stages, runs

## Technology Stack

- Python 3.11+ CLI application
- Docker for worker sandboxing (planned)
- Ollama (OpenAI-compatible API) for local model inference
- OpenRouter for cloud model access (Claude, GPT, Llama, 300+ models)
- Any OpenAI-compatible endpoint (vLLM, TGI, etc.)
- SQLite for task queue, run history, checkpoints
- Anthropic API (Claude Opus) for Orchestrator (Phase 2)

## Build & Development

**This is a greenfield project.** See `huginn-spec.md` for the full specification and `huginn-overview.md` for the design philosophy.

### Implementation Status

See `.harness/feature_list.json` for the full 105-feature tracking list and `.harness/development-summary.md` for architecture and priority order.

**Done:**
- CLI (run, status, pipelines, skills, tasks, logs), config loader, skill parser, manifest parser
- SQLite schema, Ollama client, agent loop with tool-call protocol (OpenAI function calling)
- file_read/file_write tools with path restrictions
- Verification engine, checkpoint/resume, stage chaining
- Multi-backend support (ollama, openrouter, openai_compatible)
- Background execution (--bg flag, detached process)
- post-generator starter pipeline

**Not yet built:**
- Docker sandboxing per stage
- web_search, web_fetch, shell tools
- content-classifier and code-reviewer starter pipelines
- HTTP API / daemon mode / remote execution
- Dashboard
- Tests

## Design Principles

- **Skill is the product**: the system prompt, constraints, and verification rules are what make a 7B model perform — invest effort there
- **Never delete partial work**: on failure, preserve output and checkpoint for resume
- **Error recovery**: Backend unreachable → retry 3x with backoff; model not loaded → suggest pull command (Ollama) or check models page (OpenRouter); checkpoint corruption → restart stage, warn
- **Each stage is fully isolated**: can only see its declared inputs, reference files, and its assigned backend API
- **Brain/hands separation**: Model inference (brain) runs on backends. Tool execution (hands) runs where Huginn runs. These are independently deployable.
