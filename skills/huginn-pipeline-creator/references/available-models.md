# Available Models Reference

## i3 Server (always-on, 32GB RAM, CPU-only)

These models are pulled and available on the i3 at `http://192.168.2.135:11434`:

| Model | Type | Speed | Best For |
|-------|------|-------|----------|
| qwen2.5:0.5b | Dense, tiny | 20-30 tok/s | Fast classification, routing, yes/no |
| qwen2.5:7b | Dense | 5-8 tok/s | Analysis, extraction, review, planning |
| llama3.2:3b | Dense | 10-15 tok/s | Quick interactive, simple tasks |
| nomic-embed-text | Embedding | Fast | Semantic search, dedup, RAG |

### Additional models that may be pulled:
| Model | Type | Speed | Best For |
|-------|------|-------|----------|
| qwen3:8b | Dense | 5-8 tok/s | Strong coding, multilingual |
| qwen3:30b-a3b | MoE (3B active) | 8-15 tok/s | Fast + smart workhorse |

## Mac M3 Max (64GB unified, available when laptop is on)

| Model | Type | Speed | Best For |
|-------|------|-------|----------|
| qwen3.6:27b | Dense | 15-25 tok/s | Best prose quality, deep analysis |
| qwen3:30b-a3b | MoE (3B active) | 25-35 tok/s | Fast general purpose |
| llama3.3:70b | Dense | 10-15 tok/s | Complex reasoning, general purpose |
| qwen2.5-coder:32b | Dense | 12-18 tok/s | Code review, generation |

## Model Selection Rules

1. **Classification, tagging, routing** → smallest model that benchmarks well (usually 0.5b-3b)
2. **Structured extraction** → 7b-8b models
3. **Prose generation needing voice/style** → 27b+ on Mac, or 30b-a3b MoE on i3
4. **Code analysis** → 7b-8b on i3, 32b coder on Mac for deep review
5. **Verification/checking stages** → can use smaller models since they're evaluating, not generating

## MoE Models Explained

Mixture of Experts (MoE) models like `qwen3:30b-a3b` have many total parameters (30B) but only activate a small subset (3B) per token. This means:
- They run as fast as a model the size of their active params (3B)
- They have the knowledge/quality of a much larger model (30B)
- They use more RAM than their active param count suggests (still need ~18GB)
- Perfect for the i3 where CPU speed is the bottleneck

## Backend Selection

- **i3**: For always-on tasks, overnight batch processing, anything that needs to be available 24/7
- **mac**: For quality-critical stages (prose generation, complex reasoning), or when speed matters and the laptop is available
- **Mixed**: Route cheap stages (classify, filter, check) to i3, expensive stages (generate, reason) to Mac

Always check model availability before assigning: `docker exec -it ollama ollama list` (i3) or `ollama list` (Mac)
