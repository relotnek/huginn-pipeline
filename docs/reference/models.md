# Models Reference

Model inventory by backend, with selection guidance.

## Ollama Models

### i3 Server (Always-On, 32GB RAM, CPU-Only)

| Model | Type | Speed | Best For |
|-------|------|-------|----------|
| `qwen2.5:0.5b` | Dense, tiny | 20-30 tok/s | Fast classification, routing, yes/no decisions |
| `qwen2.5:7b` | Dense | 5-8 tok/s | Analysis, extraction, review, planning |
| `llama3.2:3b` | Dense | 10-15 tok/s | Quick interactive tasks, simple generation |
| `nomic-embed-text` | Embedding | Fast | Semantic search, dedup, RAG |
| `qwen3:8b` | Dense | 5-8 tok/s | Strong coding, multilingual |
| `qwen3:30b-a3b` | MoE (3B active) | 8-15 tok/s | Fast + smart general workhorse |

### Mac M3 Max (64GB Unified Memory)

| Model | Type | Speed | Best For |
|-------|------|-------|----------|
| `qwen3.6:27b` | Dense | 15-25 tok/s | Best prose quality, deep analysis |
| `qwen3:30b-a3b` | MoE (3B active) | 25-35 tok/s | Fast general purpose |
| `llama3.3:70b` | Dense | 10-15 tok/s | Complex reasoning, general purpose |
| `qwen2.5-coder:32b` | Dense | 12-18 tok/s | Code review, generation |

### Checking Available Models

```bash
# On the i3 server
docker exec -it ollama ollama list

# On Mac (local)
ollama list

# Pull a new model
ollama pull qwen3:8b
```

## OpenRouter Models

OpenRouter provides access to 300+ models. Use the `provider/model` name format:

| Model | Provider | Best For |
|-------|----------|----------|
| `anthropic/claude-sonnet-4-6` | Anthropic | Complex reasoning, nuanced writing |
| `meta-llama/llama-3.3-70b` | Meta | General purpose, open-weight |
| `google/gemini-2.5-pro` | Google | Multimodal, long context |
| `qwen/qwen-2.5-7b-instruct` | Qwen | Same as local Ollama version |

Browse the full catalog at [openrouter.ai/models](https://openrouter.ai/models).

## Model Selection Guide

| Task | Temperature | Recommended Model | Why |
|------|------------|-------------------|-----|
| Classification, routing | 0.1-0.2 | `qwen2.5:0.5b` | Fast, simple decisions |
| Structured extraction | 0.2-0.3 | `qwen2.5:7b` | Good at following templates |
| Code analysis | 0.2-0.3 | `qwen2.5:7b` or `qwen2.5-coder:32b` | Depends on depth |
| Prose with voice/style | 0.7 | `qwen3.6:27b` or `qwen3:30b-a3b` | Needs nuance |
| Complex reasoning | 0.3-0.5 | `anthropic/claude-sonnet-4-6` | Frontier capability |
| Verification / checking | 0.1-0.2 | `qwen2.5:7b` | Consistent judgment |

## MoE Models Explained

Mixture of Experts (MoE) models like `qwen3:30b-a3b` have many total parameters (30B) but only activate a small subset (3B) per token:

- Run as fast as a model the size of their active params (3B)
- Have the knowledge/quality of a much larger model (30B)
- Use more RAM than their active param count suggests (~18GB for 30B-A3B)
- Perfect for CPU backends where speed is the bottleneck

## Backend Selection Strategy

| Scenario | Backend | Why |
|----------|---------|-----|
| Always-on tasks, overnight batch | i3 server | Available 24/7, doesn't need laptop |
| Quality-critical prose | Mac (big GPU) | Bigger models, faster inference |
| Quick classification stages | i3 server | Small models, always available |
| Complex reasoning when needed | OpenRouter | Frontier capability, pay per use |
| Mixed pipeline | Route per stage | Cheap stages to i3, expensive to Mac/cloud |
