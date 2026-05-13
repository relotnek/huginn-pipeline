# Architecture Overview

Huginn separates into three independently deployable layers, with a clear boundary between model inference (the brain) and tool execution (the hands).

## System Architecture

```
┌─────────────────────────────────────────────────┐
│  DASHBOARD                                       │
│  Web UI + API for observing ravens across        │
│  backends. Real-time pipeline progress,          │
│  backend utilization, task history.              │
│  (Phase 5 — planned)                             │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────┐
│  HUGINN — CLI / Tool Runtime                     │
│                                                  │
│  Runs tools (file_read, file_write, ...).        │
│  Can be LOCAL (laptop) or REMOTE (cloud VM).     │
│  The "hands" — cheap, parallelizable.            │
│                                                  │
│  Modes:                                          │
│   • CLI: huginn run pipeline --input file        │
│   • Background: huginn run pipeline --bg         │
│   • Daemon: long-lived, accepts HTTP (planned)   │
└────────────────────┬────────────────────────────┘
                     │ OpenAI-compatible API
┌────────────────────┴────────────────────────────┐
│  BACKEND(S) — Model Inference                    │
│                                                  │
│  Ollama, OpenRouter, or any OpenAI-compatible.   │
│  Can be LOCAL or REMOTE.                         │
│  The "brain" — stateless, text in → text out.    │
│                                                  │
│  Current:                                        │
│   • i3/heimdall — always-on, small models        │
│   • Mac M3 Max — big models, when available      │
│   • OpenRouter — 300+ cloud models               │
└─────────────────────────────────────────────────┘
```

## Deployment Matrix

Because brain and hands are decoupled, you can mix and match:

| Huginn (hands) | Backend (brain) | Use Case |
|----------------|-----------------|----------|
| Local | Local | Dev laptop, everything on-box |
| Local | Remote | Laptop runs tools, server runs models |
| Remote | Local | Cloud VM runs tools, local GPU serves models |
| Remote | Remote | Fully hosted, headless pipelines |

## Key Artifacts

| Artifact | What It Is | Where It Lives |
|----------|-----------|---------------|
| **Pipeline** | Folder with manifest + skills + files | `~/.huginn/pipelines/` |
| **Skill** | Markdown file defining one stage's behavior | Pipeline's `skills/` or `~/.huginn/skills/` |
| **Manifest** | YAML defining the execution graph | Pipeline root |
| **Task** | One execution of a pipeline | `~/.huginn/tasks/<id>/` |
| **Stage** | One step in a task, running one skill | `tasks/<id>/stages/<N>/` |

## Data Flow

```
User Input
    │
    ▼
┌─────────┐     ┌─────────┐     ┌─────────┐
│ Stage 0  │────▶│ Stage 1  │────▶│ Stage 2  │────▶ Final Output
│          │     │          │     │          │
│ input/   │     │ input/   │     │ input/   │
│ output/  │     │ output/  │     │ output/  │
│ files/   │     │ files/   │     │ files/   │
└─────────┘     └─────────┘     └─────────┘
```

Each stage:

1. Reads from its `input/` directory (wired from prior stage's output or pipeline input)
2. Reads reference docs from its `files/` directory (declared in manifest)
3. Calls its assigned model on its assigned backend
4. Uses tools (file_read, file_write) to interact with its directories
5. Writes results to its `output/` directory
6. Gets verified against rules from its skill

## Technology Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| CLI | Click + Rich | Clean argument parsing, pretty terminal output |
| Database | SQLite + WAL | Single-file, no server, fast enough |
| Model client | OpenAI Python SDK | Works with Ollama, OpenRouter, and anything compatible |
| Skill parser | python-frontmatter | YAML frontmatter + markdown body |
| Config | PyYAML | Simple, human-readable |
| Containers | Docker (planned) | Isolation, reproducibility, resource limits |
| HTTP API | FastAPI (planned) | Async, auto-docs |
