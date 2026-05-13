# Configuration File Reference

Complete reference for `~/.huginn/config.yaml`.

## Full Example

```yaml
backends:
  mac:
    type: ollama
    url: http://localhost:11434

  i3:
    type: ollama
    url: http://192.168.2.135:11434

  openrouter:
    type: openrouter
    api_key_env: OPENROUTER_API_KEY
    app_name: Huginn
    referer: https://github.com/asgarddev/huginn
    model_map:
      qwen2.5:7b: qwen/qwen-2.5-7b-instruct
      qwen3:30b-a3b: qwen/qwen3-30b-a3b

  vllm:
    type: openai_compatible
    url: http://my-vllm-server:8000/v1
    api_key_env: VLLM_API_KEY

default_backend: i3
max_parallel_workers: 2
task_timeout_minutes: 480
default_resource_limits:
  cpus: "2.0"
  memory: "8g"
```

## Top-Level Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `backends` | object | See below | Named backend configurations |
| `default_backend` | string | `i3` | Backend used when not specified |
| `max_parallel_workers` | int | `2` | Max concurrent workers (future) |
| `task_timeout_minutes` | int | `480` | Global task timeout (8 hours) |
| `default_resource_limits` | object | See below | Container resource limits (future) |

## Backend Configuration

Each entry under `backends` is a named backend:

### Common Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | No | `ollama` (default), `openrouter`, or `openai_compatible` |
| `url` | string | Depends | Backend URL (required for `ollama` and `openai_compatible`) |
| `api_key_env` | string | Depends | Name of env var containing API key |
| `model_map` | object | No | Map Ollama model names to this backend's names |

### Ollama-Specific

```yaml
my-backend:
  type: ollama
  url: http://host:11434
```

No API key needed. URL points to the Ollama API.

### OpenRouter-Specific

```yaml
openrouter:
  type: openrouter
  api_key_env: OPENROUTER_API_KEY    # required
  app_name: My App                   # optional, sent as X-Title
  referer: https://example.com       # optional, sent as HTTP-Referer
```

URL is automatically set to `https://openrouter.ai/api/v1`. Do not set `url` manually.

### OpenAI-Compatible

```yaml
my-server:
  type: openai_compatible
  url: http://host:8000/v1           # required
  api_key_env: MY_KEY                # optional
```

## Model Mapping

The `model_map` field translates Ollama model names to a backend's expected names:

```yaml
backends:
  openrouter:
    type: openrouter
    api_key_env: OPENROUTER_API_KEY
    model_map:
      qwen2.5:7b: qwen/qwen-2.5-7b-instruct
      qwen3:30b-a3b: qwen/qwen3-30b-a3b
```

This lets you write manifests with Ollama names and run them on any backend:

```bash
# Manifest says model: qwen2.5:7b
# With --backend openrouter, Huginn translates to qwen/qwen-2.5-7b-instruct
huginn run my-pipeline --input file.md --backend openrouter
```

## Environment Variables

| Variable | Used By | Description |
|----------|---------|-------------|
| `HUGINN_HOME` | Huginn | Override default home directory (default: `~/.huginn`) |
| `OPENROUTER_API_KEY` | OpenRouter backend | API key for OpenRouter |

## Default Configuration

If no `config.yaml` exists, Huginn creates one with these defaults:

```yaml
backends:
  i3:
    type: ollama
    url: http://192.168.2.135:11434
  mac:
    type: ollama
    url: http://localhost:11434
default_backend: i3
max_parallel_workers: 2
task_timeout_minutes: 480
default_resource_limits:
  cpus: "2.0"
  memory: "8g"
```

## Directory Structure

```
~/.huginn/
├── config.yaml            # This file
├── huginn.db              # SQLite database
├── skills/                # Global skills
├── pipelines/             # Pipeline definitions
└── tasks/                 # Task execution directories
```
