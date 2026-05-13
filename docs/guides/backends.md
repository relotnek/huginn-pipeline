# Using Backends

Huginn supports multiple inference backends simultaneously. This guide covers how to configure and route work across them.

## Backend Types

```
┌───────────────────────┐     ┌─────────────────────────┐     ┌─────────────────────┐
│  MacBook Pro M3 Max   │     │  i3 Server (heimdall)   │     │  OpenRouter (cloud)  │
│  64GB unified memory  │     │  32GB RAM, Debian       │     │  300+ models         │
│  Ollama (native)      │     │  Ollama (Docker)        │     │  Claude, GPT, Llama  │
│  Big models: 27B-70B  │     │  Small models: 0.5B-8B  │     │  Pay-per-token       │
│  type: ollama         │     │  type: ollama           │     │  type: openrouter    │
│  localhost:11434      │     │  192.168.2.135:11434    │     │  openrouter.ai/api   │
└───────────────────────┘     └─────────────────────────┘     └─────────────────────┘
```

| Type | Use Case | Cost |
|------|----------|------|
| **ollama** | Local/LAN GPU inference | Free (your hardware) |
| **openrouter** | Access to frontier models (Claude, GPT, Gemini) and 300+ others | Pay-per-token |
| **openai_compatible** | Self-hosted vLLM, TGI, or other servers | Your infrastructure |

## Configuring OpenRouter

### 1. Get an API Key

Sign up at [openrouter.ai](https://openrouter.ai) and create an API key.

### 2. Set the Environment Variable

```bash
export OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

Add to `~/.zshrc` or `~/.bashrc` to persist.

### 3. Add to Config

```yaml
backends:
  openrouter:
    type: openrouter
    api_key_env: OPENROUTER_API_KEY
    app_name: Huginn
```

!!! important
    `api_key_env` is the **name** of the environment variable, not the key itself. The `url` field is not needed — Huginn sets it automatically to `https://openrouter.ai/api/v1`.

### 4. Use OpenRouter Model Names

OpenRouter models use `provider/model` format:

```yaml
model: anthropic/claude-sonnet-4-6
model: meta-llama/llama-3.3-70b
model: google/gemini-2.5-pro
model: qwen/qwen-2.5-7b-instruct
```

Browse the full catalog at [openrouter.ai/models](https://openrouter.ai/models).

## Brain/Hands Separation

A critical concept: **the model (brain) and the tools (hands) run in different places.**

- **Brain** = inference backend. Receives prompts, generates text. Runs on Ollama, OpenRouter, or any endpoint.
- **Hands** = Huginn tool runtime. Executes `file_read`, `file_write`, and other tools. Always runs where Huginn runs (your local machine).

When you use OpenRouter as a backend:

1. The model prompt is sent to OpenRouter's API
2. The model generates a response (possibly including tool calls)
3. Tool calls are executed **locally** by Huginn on your machine
4. Tool results are sent back to the model for the next turn

Your files never leave your machine. Only prompts and model responses travel to the cloud.

## Multi-Backend Routing

Route pipeline stages to different backends based on task needs:

```yaml
stages:
  # Small, fast tasks → always-on server
  - name: classify
    backend: i3
    model: qwen2.5:0.5b

  # Structured extraction → medium model
  - name: analyze
    backend: i3
    model: qwen2.5:7b

  # Prose quality → big local model
  - name: draft
    backend: mac
    model: qwen3.6:27b

  # Complex reasoning → frontier cloud model
  - name: deep-analysis
    backend: openrouter
    model: anthropic/claude-sonnet-4-6
```

### When to Route Where

| Task | Backend | Model | Why |
|------|---------|-------|-----|
| Classification, routing | Always-on server | 0.5b-3b | Fast, simple decisions, 24/7 |
| Extraction, analysis | Always-on server | 7b-8b | Good accuracy, always available |
| Prose generation | Laptop (big GPU) | 27b+ | Needs nuance, quality matters |
| Complex reasoning | OpenRouter | Claude, GPT | Frontier capability when needed |
| Overnight batch jobs | Always-on server | Any | Laptop can sleep |

## Overriding Backends at Runtime

Override the backend for an entire run:

```bash
huginn run my-pipeline --input file.md --backend openrouter
```

This overrides all stages' backend settings. Useful for testing a pipeline against a different backend without editing the manifest.

## Model Name Mapping

If you want to write pipelines with Ollama model names and run them on OpenRouter, add a `model_map`:

```yaml
backends:
  openrouter:
    type: openrouter
    api_key_env: OPENROUTER_API_KEY
    model_map:
      qwen2.5:7b: qwen/qwen-2.5-7b-instruct
      qwen3:30b-a3b: qwen/qwen3-30b-a3b
```

Now `huginn run my-pipeline --backend openrouter` translates model names automatically.

## Next Steps

- [Models Reference](../reference/models.md) — full model inventory by backend
- [Configuration Reference](../reference/config.md) — all config options
- [Tutorial: Multi-Backend Routing](../tutorials/multi-backend.md) — hands-on example
