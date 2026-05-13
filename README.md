<div align="center">
  <img src="images/huginnlogobanner.png" alt="Huginn" width="600">
  <br><br>
  <em>Send out the ravens. They come back with results.</em>
</div>

Huginn is a Python CLI for building and running autonomous LLM pipelines on local and remote infrastructure. You write skill files that make cheap models smart on narrow tasks, chain them into pipelines, and run them against your Ollama backends — or through OpenRouter to access any model from any provider. Frontier intelligence authors skills once; local models execute them repeatedly, for free.

## How It Works

A **pipeline** is a folder containing a `manifest.yaml` (the execution graph) and a set of **skill files** (markdown with YAML frontmatter). Each skill defines the system prompt, model, constraints, tools, and verification rules for one stage. Stages execute sequentially, with each stage's output wiring into the next stage's input.

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

The agent loop inside each stage is generic — observe, think (call model), act (use tools), verify, checkpoint. The skill prompt is what differentiates behavior. If a run crashes mid-pipeline, it resumes from the last checkpoint.

### Tools

Stages can use tools during execution. The model generates tool calls (via OpenAI function-calling protocol), the agent executes them locally, and feeds results back to the model in a loop.

Available tools:
- **file_read** — read files from the input or reference files directory
- **file_write** — write files to the output directory

Tools run where Huginn runs (local), not where the model runs (backend). Path restrictions enforce that agents can only read from declared inputs and write to their output directory.

## Prerequisites

- Python 3.11+
- [Ollama](https://ollama.ai) running on at least one backend (or an OpenRouter API key)

## Install

```bash
cd huginn
pip install -e .
```

## Configuration

On first run, Huginn creates `~/.huginn/config.yaml`. Edit to point at your backends:

```yaml
backends:
  # Local Ollama instances
  mac:
    type: ollama
    url: http://localhost:11434
  i3:
    type: ollama
    url: http://192.168.2.135:11434

  # OpenRouter — access Claude, GPT, Llama, Gemini, and 300+ models
  openrouter:
    type: openrouter
    url: https://openrouter.ai/api/v1
    api_key_env: OPENROUTER_API_KEY   # reads from this environment variable
    app_name: Huginn                  # optional, shows in OpenRouter dashboard

  # Any OpenAI-compatible endpoint (vLLM, TGI, etc.)
  vllm:
    type: openai_compatible
    url: http://my-vllm-server:8000/v1
    api_key_env: VLLM_API_KEY        # optional, omit if no auth needed

default_backend: i3
max_parallel_workers: 2
task_timeout_minutes: 480
```

### Backend Types

| Type | Description | API Key |
|------|-------------|---------|
| `ollama` | Local Ollama instance | Not needed |
| `openrouter` | OpenRouter API — unified access to 300+ models | Required via `api_key_env` |
| `openai_compatible` | Any OpenAI-compatible endpoint | Optional via `api_key_env` |

For OpenRouter, set your API key:
```bash
export OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

OpenRouter model names use a `provider/model` prefix:
```yaml
# In a manifest or skill file
model: anthropic/claude-sonnet-4.6    # Claude via OpenRouter
model: meta-llama/llama-3.3-70b       # Llama via OpenRouter
model: qwen2.5:7b                     # Ollama (no prefix)
```

## Usage

```bash
# Run a pipeline (foreground, blocks until complete)
huginn run post-generator --input ./raw-notes.md

# Run in background — returns task ID immediately, survives terminal close
huginn run post-generator --input ./raw-notes.md --bg

# Override the backend for a run
huginn run post-generator --input ./raw-notes.md --backend openrouter

# Check task status
huginn status <task-id>

# Follow logs for a background task
huginn logs <task-id> --follow

# List available pipelines
huginn pipelines

# List global skills
huginn skills

# List recent tasks
huginn tasks
huginn tasks --status failed --limit 5
```

### Background Execution

The `--bg` flag launches the pipeline in a detached process:

```bash
$ huginn run post-generator --input ./draft.md --bg
Task a3f7b2c1 launched in background (PID 42891)
  Logs: ~/.huginn/tasks/a3f7b2c1/run.log
  Check status: huginn status a3f7b2c1
  View logs:    huginn logs a3f7b2c1
```

The task runs independently — you can close your terminal and it keeps going. Check in later with `huginn status` or `huginn logs`.

## Project Structure

```
huginn/                     # This repo
├── huginn/                 # Python package
│   ├── cli.py              # Click CLI (run, status, pipelines, skills, tasks, logs)
│   ├── config.py           # Config loader (~/.huginn/config.yaml)
│   ├── manifest.py         # Manifest parser and pipeline discovery
│   ├── skill.py            # Skill file parser (YAML frontmatter + markdown)
│   ├── db.py               # SQLite (tasks, stages, runs)
│   ├── executor.py         # Stage executor (chaining, backend dispatch)
│   ├── agent.py            # Agent loop (observe → think → act → verify)
│   ├── ollama_client.py    # Model client (Ollama, OpenRouter, OpenAI-compatible)
│   ├── tools.py            # Tool definitions and execution (file_read, file_write)
│   └── background.py       # Background/detached pipeline execution
├── orchestrator/           # Pipeline creator skill (for Claude app sessions)
├── pipelines/
│   └── post-generator/     # Starter pipeline
├── pyproject.toml
└── README.md
```

Runtime state lives in `~/.huginn/` (databases, task output, global skills).

## Architecture

Huginn separates **model inference** (the brain) from **tool execution** (the hands):

```
┌──────────────────────────────────────────┐
│  Huginn CLI — Tool Runtime               │
│  Runs tools (file_read, file_write, ...) │
│  Can be LOCAL or REMOTE                  │
└──────────────────┬───────────────────────┘
                   │  OpenAI-compatible API
┌──────────────────┴───────────────────────┐
│  Backend(s) — Model Inference            │
│  Ollama (local), OpenRouter (cloud),     │
│  or any OpenAI-compatible endpoint       │
└──────────────────────────────────────────┘
```

The model is stateless inference — send prompt, get text back. Tools execute where Huginn runs. This means you can run inference on a beefy GPU server while tools operate on your laptop, or vice versa.

## Roadmap

**Phase 1 (current) — Runner**: Execute hand-written pipelines. Sequential stages, checkpoint/resume, verification, tool calling, multi-backend support.

**Phase 2 — Orchestrator**: `huginn create` uses Claude Opus to interactively design pipelines through a structured validation cycle (Research, Design, Threat Model, Build, Test).

**Phase 3 — Remote + Async**: HTTP API, daemon mode, set-and-forget execution, remote task submission, `huginn output` for result retrieval.

**Phase 4 — Infrastructure**: Parallel execution, task queue, cron scheduling, conditional routing, cross-backend dispatch, notifications.

**Phase 5 — Dashboard**: Web UI for following ravens across backends. Real-time progress, backend utilization, task history.

## Philosophy

The skill file is the product, not the model. A well-written skill encodes prompt engineering, domain expertise, and quality standards into a reusable artifact. Huginn lets you invest frontier-model intelligence into skill creation once, then run those skills on commodity local models indefinitely. Your data stays on your hardware. Your costs are fixed.
