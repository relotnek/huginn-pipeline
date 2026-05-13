# Roadmap

Huginn is being built in phases. Each phase delivers independently useful functionality.

## Phase 1 — Runner (Current)

**Goal:** Hand-write pipelines, run them with `huginn run`, get results.

**Status:** Core complete. Sequential stages, checkpoint/resume, verification, tool calling (file_read/file_write), multi-backend support (Ollama, OpenRouter, any OpenAI-compatible), background execution, stop/resume.

**What's built:**

- CLI: `run`, `status`, `pipelines`, `skills`, `tasks`, `logs`, `stop`, `resume`
- Config management with multi-backend support
- Skill parser (YAML frontmatter + markdown body + verification)
- Manifest parser with wiring validation
- SQLite database (tasks, stages, runs)
- Model client supporting Ollama, OpenRouter, and OpenAI-compatible endpoints
- Agent loop with tool-call protocol (OpenAI function calling)
- Pipeline executor with sequential stage chaining
- Checkpoint/resume across crashes and interruptions
- Background execution with `--bg` flag
- Starter pipeline: post-generator (4 stages)

**Remaining:**

- Docker sandboxing per stage
- Additional tools: `web_search`, `web_fetch`, `shell`
- More starter pipelines
- Test suite

---

## Phase 2 — Orchestrator

**Goal:** `huginn create` uses Claude Opus to interactively design pipelines through a structured validation cycle.

The validation cycle:

```
RESEARCH    → What models, skills, and tools are available?
DESIGN      → Which stages? Which model per stage? Data flow?
THREAT MODEL → What if a stage hallucinates? Failure modes?
BUILD       → Generate the pipeline folder with all artifacts
TEST        → Run on sample input, review output, iterate
```

---

## Phase 3 — Remote + Async

**Goal:** Set and forget. Submit pipelines locally or remotely, walk away, check results later.

```bash
# Local background
huginn run pipeline --input file.md --bg

# Remote submission (planned)
huginn --target heimdall run pipeline --input file.md
```

Key features:

- HTTP API via FastAPI (daemon mode)
- Remote task submission with input upload
- `huginn output` command for result retrieval
- Config profiles for named remote targets

---

## Phase 3.5 — Resilience

**Goal:** Tasks survive disruption. Backends don't get overwhelmed.

- Mid-execution health checks (detect backend death between stages)
- Wait-and-retry on backend unavailability
- Backend failover to alternate backends with same model
- Per-backend concurrency limiter
- Stage state machine (clean resume semantics)
- `huginn health` command

---

## Phase 4 — Infrastructure

**Goal:** Huginn becomes infrastructure. Daemon, scheduling, parallelism.

- Daemon mode with persistent process
- Cron-style scheduling
- Parallel stage execution for independent stages
- Task queue with priority and concurrency control
- Cross-backend dispatch
- Notification system (desktop, webhook)

---

## Phase 5 — Dashboard

**Goal:** Follow the ravens. See all active pipelines across backends.

- Real-time progress streaming (SSE/WebSocket)
- Web UI for pipeline monitoring
- Backend utilization metrics
- Task history and analytics
