# Huginn

*Send out the ravens. They come back with results.*

---

Huginn is a Python CLI for building and running autonomous LLM pipelines on local and remote infrastructure. You write **skill files** that make cheap models smart on narrow tasks, chain them into **pipelines**, and run them against your backends — Ollama for local inference, OpenRouter for 300+ cloud models, or any OpenAI-compatible endpoint.

**Frontier intelligence authors skills once. Local models execute them repeatedly, for free.**

## How It Works

```
raw-notes.md
    │
    ▼
┌──────────┐   ┌──────────┐   ┌─────────────┐   ┌──────────┐
│ Analyze  │──▶│  Draft   │──▶│ Slop Filter │──▶│  Revise  │──▶ final-post.md
│ qwen:7b  │   │ qwen:7b  │   │  qwen:7b    │   │ qwen:7b  │
│ (i3)     │   │ (i3)     │   │  (i3)       │   │ (i3)     │
└──────────┘   └──────────┘   └─────────────┘   └──────────┘
```

A **pipeline** is a folder containing a `manifest.yaml` (the execution graph) and a set of **skill files** (markdown with YAML frontmatter). Each skill defines the system prompt, model, constraints, tools, and verification rules for one stage. Stages execute sequentially, with each stage's output wiring into the next stage's input.

The agent loop inside each stage is generic — observe, think (call model), act (use tools), verify, checkpoint. **The skill prompt is what differentiates behavior.** If a run crashes mid-pipeline, it resumes from the last checkpoint.

## Core Concepts

| Concept | What It Is |
|---------|------------|
| **Pipeline** | A folder with a manifest and skills that defines a multi-stage workflow |
| **Skill** | A markdown file that makes a cheap model smart on one narrow task |
| **Stage** | One step in a pipeline — one skill, one model, one set of inputs/outputs |
| **Backend** | An inference endpoint (Ollama, OpenRouter, vLLM) — the "brain" |
| **Raven** | A stage in flight — an autonomous agent executing a skill |
| **Tool** | A capability the agent can use during execution (file_read, file_write) |

## The Key Insight

The expensive part of AI isn't inference — it's knowing what to ask for. A well-written skill file encodes prompt engineering, domain expertise, and quality standards into a reusable artifact. The skill is the intellectual property. The model is a commodity.

Huginn lets you invest frontier-model intelligence into skill creation once, then run those skills on commodity local models indefinitely. Your data never leaves your hardware. Your costs are fixed. Your pipelines get better every time you refine a skill.

## Quick Links

- [Installation](getting-started/installation.md) — get Huginn running in 2 minutes
- [Quick Start](getting-started/quickstart.md) — run your first pipeline
- [Writing Skills](guides/writing-skills.md) — the core craft of Huginn
- [CLI Reference](reference/cli.md) — every command documented
- [Architecture](architecture/overview.md) — how it all fits together
