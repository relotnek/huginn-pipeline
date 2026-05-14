# Huginn Development Summary

**Project**: Huginn — Skill-Based LLM Pipeline System
**Date**: 2026-05-08
**Status**: 73/134 features passing (54%)

---

## Architectural Vision

Huginn is a system for building and running autonomous LLM pipelines. The core insight: **frontier intelligence authors skills once, local models execute them repeatedly for free.** The skill file — not the model — is the product.

The architecture separates into three independently deployable layers:

```
┌─────────────────────────────────────────────────┐
│  DASHBOARD                                       │
│  Web UI + API for observing ravens across        │
│  backends. Real-time pipeline progress,          │
│  backend utilization, task history.              │
│  (Phase 3)                                       │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────┐
│  HUGINN — CLI / Daemon / Tool Runtime            │
│                                                  │
│  Runs tools (file_read, web_search, shell).      │
│  Can be LOCAL (laptop) or REMOTE (cloud VM).     │
│  The "hands" — cheap, parallelizable.            │
│                                                  │
│  Modes:                                          │
│   • CLI: huginn run pipeline --input file        │
│   • Daemon: long-lived, accepts HTTP submissions │
│   • Remote: CLI → API → remote daemon            │
└────────────────────┬────────────────────────────┘
                     │ OpenAI-compatible API
┌────────────────────┴────────────────────────────┐
│  BACKEND(S) — Model Inference                    │
│                                                  │
│  Ollama today. Abstract interface for others.    │
│  Can be LOCAL or REMOTE.                         │
│  The "brain" — expensive, stateless.             │
│                                                  │
│  Current:                                        │
│   • i3/heimdall (192.168.2.135:11434) — small    │
│   • mac (localhost:11434) — big models           │
│  Future:                                         │
│   • Anthropic API (Claude for orchestration)     │
│   • vLLM, TGI, or other inference servers        │
└─────────────────────────────────────────────────┘
```

### Key Architectural Principle: Brain/Hands Separation

The model (brain) is stateless inference — send prompt, get text. The tool runtime (hands) is where state, files, network access, and side effects live. These are decoupled:

| Huginn (hands) | Backend (brain) | Use Case |
|---|---|---|
| Local | Local | Dev laptop, everything on-box |
| Local | Remote | Laptop runs tools, heimdall runs inference |
| Remote | Local | Cloud VM runs tools, local GPU serves models |
| Remote | Remote | Fully hosted, headless pipelines |

This means you can have one beefy inference box serving multiple Huginn runtimes running different pipelines, each with their own tool sandboxes. Or you can run expensive tool operations (web scraping, large file processing) on a cloud VM while keeping inference on your own hardware for data sovereignty.

### Raven Model

Each pipeline stage is a **raven** — an autonomous agent with a skill, a model, and tools. Ravens:
- Read from their input directory (read-only)
- Think via their assigned model on their assigned backend
- Act using tools available in their tool runtime
- Write to their output directory
- Get verified against rules in their skill definition
- Checkpoint progress for resume

A pipeline is a flock of ravens, chained by data flow.

---

## Development Phases

### Phase 1 — Single Pipeline Runner (73% complete → now 49% of expanded scope)

**Goal**: Hand-write a pipeline, run it with `huginn run`, get results.

**What's built:**
- Config management with multi-backend support (i3, mac)
- Skill parser (YAML frontmatter + markdown body + verification extraction)
- Manifest parser with wiring validation
- SQLite database (tasks, stages, runs)
- Ollama client (OpenAI-compatible)
- Agent loop (observe/think/act/verify/checkpoint)
- Pipeline executor with sequential stage chaining and resume
- Full CLI (run, status, pipelines, skills, tasks)
- post-generator starter pipeline (4 stages)
- Error handling with clear messages and partial output preservation
- Orchestrator pipeline-creator skill (for Claude app sessions)

**What's missing from Phase 1:**
- **Tool-call protocol** (F041) — the critical gap. Agent writes raw output, can't invoke tools.
- Tool implementations: file_read, file_write (F042-F043)
- Docker sandboxing per stage (F047-F051)
- 2 more starter pipelines: content-classifier, code-reviewer (F052-F053)
- Tests (F058-F060)

### Phase 2 — Backend Abstraction + Tool Runtime (new)

**Goal**: Decouple model inference from tool execution. Abstract backends. Build the tool system.

**Key features:**
- Backend interface (F061-F062) — not Ollama-specific
- Backend registry with type/URL/capabilities (F063)
- Backend health monitoring (F064-F065)
- Tool runtime abstraction (F066) — tools run where Huginn runs
- Tool registry mapping skill declarations to implementations (F067)
- Constraint enforcement on tools (F068)
- Tool call logging (F069)
- Web tools: web_search via SearXNG, web_fetch (F044-F045)
- Shell tool with permission gating (F046)

### Phase 3 — Remote Interaction + Async Execution

**Goal**: Set and forget. Submit pipelines locally or remotely, walk away, check results later.

This is the operational heart of Huginn. Two execution modes, same CLI:

```
LOCAL (blocking):   huginn run pipeline --input file.md
                    → runs in foreground, prints progress, blocks until done

LOCAL (background): huginn run pipeline --input file.md --bg
                    → returns task ID immediately, runs in detached process
                    → survives terminal close
                    → huginn status <id> to check, huginn output <id> to retrieve

REMOTE:             huginn --target heimdall run pipeline --input file.md
                    → uploads input to remote daemon over HTTP
                    → returns task ID immediately
                    → huginn --target heimdall status <id> to check
                    → huginn --target heimdall output <id> --download to retrieve
```

**The set-and-forget workflow:**
1. `huginn run opensea-intel-briefing --input target.md --bg` (or `--target heimdall`)
2. Task ID returned: `a3f7b2c1`
3. Go do other things
4. Desktop notification: "Task a3f7b2c1 complete"
5. `huginn output a3f7b2c1` → see the briefing
6. `huginn output a3f7b2c1 --download` → save to disk

**Key features:**
- Remote client library (F091-F093) — Python API wrapping daemon HTTP endpoints
- Input file upload on remote submission (F092)
- `huginn output` command for result retrieval (F094-F096)
- Local background execution with `--bg` flag (F097-F098)
- Unified status across local/background/remote (F099-F100)
- Config profiles for named remote targets (F104)
- `huginn connect` for remote health check (F105)

### Phase 3.5 — Resilience + Resource Management

**Goal**: Tasks survive disruption. Backends don't get overwhelmed. Resume actually works.

Three problems this solves:
1. **Laptop closes → backend dies → tasks fail.** Currently if Mac sleeps, tasks hitting the Mac backend fail after 3 retries. Need: wait-and-retry with backoff (F107), backend failover to alternate backends with the same model (F108), auto-pause when all backends are down (F119).
2. **Batched jobs overwhelm the backend.** Nothing prevents 5 background tasks all hitting i3 simultaneously. Need: per-backend concurrency limiter (F109, F114), priority queue (F110), queue visibility (F115).
3. **Resume is fragile.** Duplicate stage records on resume, no way to distinguish clean completion from interrupted mid-write, no way to re-run a single stage. Need: stage state machine (F111), completion markers (F116), partial-output detection (F112), `huginn retry --stage N` (F113).

**Key features:**
- Mid-execution health checks (F106) — detect backend death between stages and tool rounds
- Wait-and-retry on backend unavailability (F107) — configurable backoff, don't fail immediately
- Backend failover (F108) — re-route to alternate backend with same model
- Concurrency limiter per backend (F109, F114) — respect max_parallel_workers, per-backend limits
- Priority task queue (F110) — high-priority tasks get slots first
- Stage state machine (F111) — clean transitions, no duplicate records on resume
- Partial-output detection (F112) — re-run stages that were interrupted mid-write
- `huginn retry <id> --stage N` (F113) — re-run a specific stage
- Completion markers in checkpoint (F116) — distinguish done from died
- Backend health watchdog (F117) — periodic ping, shared status
- `huginn health` command (F118) — operational status check
- Auto-pause on backend loss (F119) — pause instead of fail, auto-resume on wake
- Stale task reaper on startup (F120) — consistent DB state

**Implementation priority within this phase:**
```
F106 Mid-execution health checks        ← quick win, prevents silent failures
F107 Wait-and-retry on backend loss      ← laptop-close survival
F109 Concurrency limiter                 ← prevents backend overload
F116 Completion markers                  ← foundation for clean resume
F111 Stage state machine                 ← fixes duplicate records
F112 Partial-output detection            ← safe resume
F108 Backend failover                    ← automatic recovery
F114 Per-backend concurrency config      ← right-size limits
F110 Priority queue                      ← fair scheduling
F113 huginn retry --stage N              ← operational convenience
F118 huginn health                       ← operational visibility
F117 Backend health watchdog             ← foundation for auto-pause
F119 Auto-pause on backend loss          ← full laptop-close resilience
F120 Stale task reaper                   ← startup consistency
F115 huginn queue                        ← queue visibility
```

### Phase 4 — Infrastructure + Scheduling

**Goal**: Huginn becomes infrastructure. Daemon, API, scheduling, parallelism.

**Key features:**
- Daemon mode (F070)
- FastAPI HTTP API — submit tasks, query status, check backends (F071-F075)
- Auth for remote access (F075)
- Cron-style scheduling (F077-F078)
- Parallel stage execution for independent stages (F079)
- Task queue with concurrency control (F080)
- Cross-backend dispatch (F081)
- Docker Compose for daemon deployment (F086)
- Notification system with configurable hooks (F101-F102)
- Desktop notifications on macOS (F103)
- Webhooks (F087)
- CLI: cancel, logs, batch (F088-F090)

### Phase 5 — The Unkindness (Distributed Ravens)

**Goal**: Multiple Huginn instances collaborate. Dispatch ravens to remote workers with their own backends and tool runtimes.

See `docs/architecture/unkindness.md` for the full architecture document.

**Key features:**
- Worker config alongside backends (F121)
- Worker daemon with auth (F123-F124)
- `huginn run --worker <name>` dispatch (F125)
- Remote status/output/logs proxying (F126)
- Pipeline deployment to workers (F127)
- Pipeline allowlisting + capability enforcement (F128-F129)
- TLS, audit logging, cross-worker execution, failover (F130-F134)

**Security model:** API key auth, pipeline allowlisting, capability declaration, TLS for non-LAN, audit logging, no worker-to-worker trust (operator is always the hub).

### Phase 6 — Dashboard

**Goal**: Follow the ravens across backends and workers.

**Key features:**
- Real-time progress streaming via SSE/WebSocket (F082)
- Ravens overview — all active tasks across backends and workers (F083)
- Web UI (F084)
- Per-backend and per-worker utilization metrics (F085)

---

## Feature Summary

| Category | Passing | Total | Phase |
|---|---|---|---|
| core | 2/2 | 2 | 1 |
| config | 3/3 | 3 | 1 |
| skill-parser | 4/4 | 4 | 1 |
| manifest-parser | 4/4 | 4 | 1 |
| database | 3/3 | 3 | 1 |
| ollama-client | 3/3 | 3 | 1 |
| agent-loop | 3/4 | 4 | 1 |
| verification | 2/2 | 2 | 1 |
| checkpoint | 2/2 | 2 | 1 |
| executor | 5/5 | 5 | 1 |
| cli | 5/8 | 8 | 1-4 |
| pipeline | 1/3 | 3 | 1 |
| orchestrator | 1/1 | 1 | 1 |
| tools | 0/5 | 5 | 1-2 |
| sandbox | 0/5 | 5 | 1 |
| error-handling | 4/4 | 4 | 1 |
| testing | 0/3 | 3 | 1 |
| backend-abstraction | 0/5 | 5 | 2 |
| tool-runtime | 0/4 | 4 | 2 |
| remote-client | 0/5 | 5 | 3 |
| async-execution | 0/4 | 4 | 3 |
| notifications | 0/3 | 3 | 3-4 |
| deployment | 0/8 | 8 | 4 |
| scheduling | 0/2 | 2 | 4 |
| parallel | 0/3 | 3 | 4 |
| resilience | 0/15 | 15 | 3.5 |
| unkindness | 0/14 | 14 | 5 |
| dashboard | 0/4 | 4 | 6 |
| **TOTAL** | **73/134** | **134** | |

---

## Implementation Priority

The recommended build order follows two parallel tracks that converge at the daemon.

### Track A: Make ravens smart (tools + backends)

```
F041 Tool-call protocol          ← CRITICAL: unlocks everything below
  ├── F042 file_read tool
  ├── F043 file_write tool
  ├── F066 Tool runtime          ← hands/brain separation
  │   ├── F067 Tool registry
  │   ├── F068 Constraint enforcement
  │   └── F069 Tool logging
  ├── F044 web_search            ← unlocks research pipelines
  ├── F045 web_fetch
  └── F046 shell tool
```

### Track B: Make ravens reachable (remote + async)

```
F097 --background flag           ← local set-and-forget (quick win)
  └── F098 Detached process execution
F061 Backend interface           ← architectural foundation
  ├── F062 Ollama backend
  ├── F063 Backend registry
  └── F064 Backend health
F071 HTTP API (FastAPI)          ← unlocks remote everything
  ├── F070 Daemon mode
  ├── F072 POST /tasks
  ├── F073 GET /tasks/{id}
  ├── F096 GET /tasks/{id}/output
  └── F075 API auth
F091 Remote client library       ← CLI remote mode
  ├── F092 Input upload
  ├── F093 Status polling
  ├── F076 --target CLI flag
  └── F104 Config profiles
F094 huginn output command       ← result retrieval
  └── F095 --download flag
```

### Convergence

```
F099 Unified status (local + bg + remote)
F101-F103 Notifications
F079-F081 Parallel + dispatch
F082-F085 Dashboard
```

### Recommended session order

1. **F041** — tool-call protocol (unlocks Track A)
2. **F042-F043** — file_read/file_write (existing pipelines become tool-aware)
3. **F097-F098** — local background execution (quickest path to set-and-forget)
4. **F061-F063** — backend abstraction (foundation for everything remote)
5. **F066-F068** — tool runtime (complete hands/brain separation)
6. **F094** — `huginn output` command (result retrieval works for local + bg)
7. **F071-F073, F096** — HTTP API (daemon accepts remote work)
8. **F091-F093** — remote client (CLI can talk to daemon)
9. **F044-F045** — web_search/web_fetch (research pipelines come alive)
10. **F101-F103** — notifications (set-and-forget gets a "done" signal)

**Next session should start with F041** — the tool-call protocol in agent.py.

---

## Technology Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Model inference | Ollama (OpenAI-compatible API) | Self-hosted, no API costs, data sovereignty |
| Search backend | SearXNG (planned) | Self-hosted meta-search, no API keys, Docker container |
| Task database | SQLite + WAL | Single-file, no server, fast enough for local use |
| CLI framework | Click + Rich | Clean argument parsing, pretty terminal output |
| HTTP API | FastAPI (planned) | Async, auto-docs, Python-native |
| Dashboard | TBD | Likely lightweight JS consuming FastAPI endpoints |
| Containerization | Docker per stage | Isolation, reproducibility, resource limits |

---

## Open Questions

1. **Remote tool execution security**: When Huginn daemon runs remotely and accepts pipeline submissions over HTTP, how do we gate which tools are available? API key auth is necessary but insufficient — need per-pipeline tool allowlists.

2. **Backend selection strategy**: When multiple backends are available, should the executor auto-select based on model size / backend capabilities, or should the manifest always be explicit?

3. **Dashboard technology**: Full React app? Lightweight HTMX? Terminal-based with Rich? Depends on who's watching the ravens.

4. **SearXNG vs. external search**: SearXNG is self-hosted and free but requires running another container. For quick wins, Brave Search API (2000 free queries/month) might bootstrap faster.

5. **Remote pipeline sync**: When submitting to a remote daemon, does the daemon need its own copy of pipeline definitions (skills, manifests, reference files)? Or does the client upload the full pipeline definition alongside the input? The first approach means managing pipeline deployment to remote targets. The second is simpler but means larger payloads and no shared pipeline state.

6. **Output storage on remote**: Remote daemon stores outputs on its filesystem. How long? Indefinite until manually cleaned? TTL-based? Need a `huginn cleanup` command or auto-expiry policy.

7. **Local background process model**: Fork-and-detach vs. a lightweight local daemon. Fork is simpler but harder to manage (PID files, orphan cleanup). A local daemon is more robust but heavier — essentially the same code path as the remote daemon running on localhost.
