# Configuration

Huginn's configuration lives at `~/.huginn/config.yaml`. It's created automatically on first run with sensible defaults.

## Configuration File

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

## Backend Types

| Type | Description | API Key | URL |
|------|-------------|---------|-----|
| `ollama` | Local Ollama instance | Not needed | Required |
| `openrouter` | OpenRouter API (300+ cloud models) | Required via `api_key_env` | Auto-set to `openrouter.ai/api/v1` |
| `openai_compatible` | Any OpenAI-compatible endpoint | Optional via `api_key_env` | Required |

### Ollama Backend

The simplest backend. Point it at any Ollama instance:

```yaml
backends:
  local:
    type: ollama
    url: http://localhost:11434
  remote-gpu:
    type: ollama
    url: http://192.168.2.135:11434
```

No API key needed. Models are referenced by their Ollama name (e.g., `qwen2.5:7b`).

### OpenRouter Backend

Gives you access to 300+ models from every major provider through a single API:

```yaml
backends:
  openrouter:
    type: openrouter
    api_key_env: OPENROUTER_API_KEY   # name of env var, NOT the key itself
    app_name: Huginn                  # optional, sent as X-Title header
    referer: https://github.com/you  # optional, sent as HTTP-Referer
```

Set the API key in your environment:

```bash
export OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

!!! important
    The `api_key_env` field contains the **name of the environment variable**, not the API key itself. This keeps secrets out of config files.

OpenRouter models use a `provider/model` format:

```yaml
# In manifest.yaml or skill files
model: anthropic/claude-sonnet-4-6
model: meta-llama/llama-3.3-70b
model: google/gemini-2.5-pro
```

### OpenAI-Compatible Backend

For vLLM, TGI, or any endpoint that speaks the OpenAI API:

```yaml
backends:
  my-server:
    type: openai_compatible
    url: http://my-server:8000/v1
    api_key_env: MY_SERVER_KEY        # optional
```

## Default Backend

The `default_backend` field sets which backend is used when a pipeline stage doesn't specify one:

```yaml
default_backend: i3
```

You can override this per-run:

```bash
huginn run my-pipeline --input file.md --backend openrouter
```

Or per-stage in the manifest:

```yaml
stages:
  - name: analyze
    backend: i3        # cheap model on always-on server
    model: qwen2.5:7b
  - name: reason
    backend: openrouter # frontier model for complex reasoning
    model: anthropic/claude-sonnet-4-6
```

## Model Name Mapping

When using OpenRouter, model names differ from Ollama names. Huginn can auto-map between them if you add a `model_map` to a backend:

```yaml
backends:
  openrouter:
    type: openrouter
    api_key_env: OPENROUTER_API_KEY
    model_map:
      qwen2.5:7b: qwen/qwen-2.5-7b-instruct
      qwen3:30b-a3b: qwen/qwen3-30b-a3b
```

This lets you write pipelines with Ollama model names and run them on OpenRouter without changing the manifest.

## Global Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `default_backend` | `i3` | Backend used when stage doesn't specify one |
| `max_parallel_workers` | `2` | Max concurrent stages (future) |
| `task_timeout_minutes` | `480` | Global timeout for tasks (8 hours) |
| `default_resource_limits.cpus` | `2.0` | CPU limit per stage container (future) |
| `default_resource_limits.memory` | `8g` | Memory limit per stage container (future) |

## Directory Structure

Runtime state lives in `~/.huginn/`:

```
~/.huginn/
├── config.yaml            # This file
├── huginn.db              # SQLite: tasks, stages, runs
├── skills/                # Global reusable skill library
├── pipelines/             # Pipeline definitions
│   └── post-generator/    # One folder per pipeline
└── tasks/                 # Per-task execution directories
    └── a3f7b2c1/          # One folder per task run
        ├── input/         # Copied input files
        ├── output/        # Final output
        ├── stages/        # Per-stage I/O
        └── meta.json      # Task metadata
```

## Next Steps

- [Using Backends](../guides/backends.md) — deep dive into multi-backend routing
- [CLI Reference](../reference/cli.md) — all commands and flags
