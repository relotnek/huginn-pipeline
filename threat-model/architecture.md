# Q1: What Are We Building — Huginn Pipeline Runner

> Generated: 2026-05-12
> Source: Code-level analysis of `huginn/huginn/` Python package

---

## System Description

Huginn is a Python CLI that executes multi-stage LLM pipelines on local hardware. Each pipeline is a folder containing a manifest (stage definitions, model assignments, input/output wiring) and skill files (system prompts with tool permissions). Stages run sequentially in the same Python process, calling Ollama (local) or OpenRouter (cloud) for model inference and executing tools (file I/O, web access, shell commands) locally.

The system runs on a single operator's Mac M3 Max and an i3 server ("heimdall") on the same LAN. There is no multi-user access, no authentication layer, and no network-facing API. State is stored in `~/.huginn/` — SQLite database, YAML config, pipeline definitions, and per-task execution directories.

Docker sandboxing per stage is designed but not yet implemented. Currently, all stages share the operator's process context with tool-level path restrictions as the primary containment mechanism.

## Architecture Diagram

```
                         ┌─── Internet ─────────────────────────┐
                         │                                       │
                   ┌─────┴──────┐  ┌──────────────┐            │
                   │ OpenRouter  │  │ DuckDuckGo   │            │
                   │ API (HTTPS) │  │ (web_search) │            │
                   │ C5          │  │              │            │
                   └──────┬──────┘  └──────┬───────┘            │
                          │                │                     │
    ══════════════════ Internet / LAN Boundary (TB1) ═══════════╡
                          │                │                     │
    ┌─────────────────────┴────────────────┴──────────────────┐ │
    │                   Mac / i3 Host                          │ │
    │                                                          │ │
    │  ┌────────────────────────────────────────────────────┐  │ │
    │  │              Huginn Process (TB2)                   │  │ │
    │  │                                                     │  │ │
    │  │  ┌──────────┐    ┌──────────┐    ┌──────────────┐  │  │ │
    │  │  │ C1: CLI  │───>│ C2: Exec │───>│ C3: Agent    │  │  │ │
    │  │  │ (click)  │    │ (stages) │    │ (iterate)    │  │  │ │
    │  │  └──────────┘    └────┬─────┘    └──────┬───────┘  │  │ │
    │  │                       │                  │          │  │ │
    │  │              ┌────────┴──────┐    ┌──────┴───────┐  │  │ │
    │  │              │ C7: SQLite DB │    │ C6: Tool     │  │  │ │
    │  │              │ (~/.huginn/   │    │ Runtime      │  │  │ │
    │  │              │  huginn.db)   │    │ (constraint  │  │  │ │
    │  │              └───────────────┘    │  enforcement)│  │  │ │
    │  │                                   └──────┬───────┘  │  │ │
    │  │                                          │          │  │ │
    │  │  ═══════════════ Tool Boundary (TB3) ════╪══════    │  │ │
    │  │                                          │          │  │ │
    │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ │          │  │ │
    │  │  │file_read │ │file_write│ │  shell   │◄┘          │  │ │
    │  │  │(input/   │ │(output/  │ │(shell=T) │            │  │ │
    │  │  │ files/)  │ │ only)    │ │subprocess│            │  │ │
    │  │  └──────────┘ └──────────┘ └──────────┘            │  │ │
    │  │  ┌──────────┐ ┌──────────┐                         │  │ │
    │  │  │web_search│ │web_fetch │  (network=true required) │  │ │
    │  │  │(DDG API) │ │(any URL) │                         │  │ │
    │  │  └──────────┘ └──────────┘                         │  │ │
    │  └────────────────────────────────────────────────────┘  │ │
    │                                                          │ │
    │  ┌────────────────────────────────────────────────────┐  │ │
    │  │ C8: Filesystem State (~/.huginn/)                   │  │ │
    │  │ ├─ config.yaml (backend URLs, env var refs)         │  │ │
    │  │ ├─ huginn.db (tasks, stages, runs)                  │  │ │
    │  │ ├─ pipelines/{name}/ (manifest, skills, files)      │  │ │
    │  │ ├─ tasks/{id}/ (input, output, stages, checkpoint)  │  │ │
    │  │ └─ skills/ (global skill library)                   │  │ │
    │  └────────────────────────────────────────────────────┘  │ │
    │                                                          │ │
    │  ┌──────────────┐       DF3 (HTTP, unencrypted)         │ │
    │  │ C4: Ollama   │◄──────────────────────────────────────┘ │
    │  │ (localhost or │                                         │
    │  │  LAN i3)     │  EP4                                    │
    │  └──────────────┘                                         │
    │                                                           │
    │  Operator workstation (single user, no auth)              │
    └───────────────────────────────────────────────────────────┘
                    │
              ┌─────┴──────┐
              │ EP1: CLI   │
              │ (huginn    │
              │  run/stop) │
              └────────────┘
```

## Component Inventory

| ID | Component | Owner | Description |
|----|-----------|-------|-------------|
| C1 | **CLI** (`cli.py`) | Operator process | Click-based CLI. Commands: run, status, resume, stop, tasks, pipelines, skills. Entry point for all user interaction. Spawns background processes via `Popen`. |
| C2 | **Executor** (`executor.py`) | Huginn process | Orchestrates pipeline execution. Loads manifests, creates task records, runs stages sequentially, wires outputs to inputs, handles resume. |
| C3 | **Agent** (`agent.py`) | Huginn process | Per-stage worker. Implements observe-think-act-verify-checkpoint loop. Sends prompts to model, processes tool calls, enforces iteration limits (default 10) and timeouts (default 60min). |
| C4 | **Ollama Backend** | Separate process (local or LAN) | OpenAI-compatible inference server. Runs on localhost:11434 (Mac) or 192.168.2.135:11434 (i3). Receives conversation context including pipeline input, skill prompts, and tool results. No authentication. |
| C5 | **OpenRouter Backend** | Cloud service | Commercial inference API. Accessed over HTTPS with API key from environment variable. Receives same conversation context as C4. |
| C6 | **Tool Runtime** (`tool_runtime.py`) | Huginn process | Registry + constraint enforcement layer. Maps tool names to handlers. Checks network/shell permissions before execution. Logs all invocations to DB. |
| C7 | **SQLite Database** (`huginn.db`) | Filesystem | Stores task history, stage records, run logs (including tool arguments and results). WAL mode. Located at `~/.huginn/huginn.db`. |
| C8 | **Filesystem State** (`~/.huginn/`) | Filesystem | Config (backend URLs, env var names), pipeline definitions (manifests, skills, reference files), task execution directories (input, output, checkpoints), global skill library. |

## Data Flow Inventory

| ID | From | To | Data | Protocol | Auth |
|----|------|----|------|----------|------|
| DF1 | Operator (EP1) | C1 (CLI) | Pipeline name, input file path, backend override | CLI args | None (local process) |
| DF2 | C2 (Executor) | C8 (Filesystem) | Task directories, stage I/O copies, meta.json | Filesystem | OS file permissions |
| DF3 | C3 (Agent) | C4 (Ollama) | System prompt + user message (contains pipeline input, skill prompt, tool results) | HTTP (plaintext) | None (`api_key="ollama"`) |
| DF4 | C3 (Agent) | C5 (OpenRouter) | Same conversation context as DF3 | HTTPS | Bearer token (from env var) |
| DF5 | C4/C5 (Model) | C3 (Agent) | Model completions, tool call requests (function name + arguments) | HTTP/HTTPS | Same session |
| DF6 | C3 (Agent) | C6 (Tool Runtime) | Tool name + arguments from model output | In-process function call | Constraint check |
| DF7 | C6 (Tool Runtime) | C8 (Filesystem) | file_read: read from input/files dirs. file_write: write to output dir | Filesystem | Path validation |
| DF8 | C6 (Tool Runtime) | Host OS | shell: arbitrary command via `subprocess.run(shell=True)` | Subprocess | 4-item blocklist |
| DF9 | C6 (Tool Runtime) | Internet | web_fetch: HTTP(S) to arbitrary URLs. web_search: DuckDuckGo API | HTTP/HTTPS | None / scheme check only |
| DF10 | C6 (Tool Runtime) | C7 (SQLite DB) | Tool invocation logs: tool name, arguments (JSON), result (truncated to 2KB) | SQLite write | None |
| DF11 | C2 (Executor) | C7 (SQLite DB) | Task/stage lifecycle records, timing, token counts | SQLite write | None |
| DF12 | C1 (CLI) | C1 (Background) | Background process spawn: `python -m huginn.background --task-id ... --pipeline ... --input ...` | `Popen` (list args) | PID file |

## Trust Boundaries

```
TB1: ════ Internet / LAN Boundary ════
     Huginn runs on a local machine. Ollama is on the same LAN
     (192.168.2.135) over unencrypted HTTP. OpenRouter is on the
     internet over HTTPS. web_fetch can reach any URL including
     LAN and localhost services. There is no network-level
     segmentation between Huginn and other LAN hosts.

TB2: ════ Huginn Process / Host OS ════
     All pipeline stages run in the same Python process as the
     operator. There is no per-stage process isolation, no
     containerization, no UID separation. A compromised stage
     has the operator's full process permissions. The tool
     runtime's constraint checks and path validation are the
     only containment mechanisms.

TB3: ════ Tool Constraint Boundary ════
     Skills declare tool permissions (network: true/false,
     shell: true/false). The ToolRuntime enforces these before
     execution. This is the primary security boundary — it
     determines what a model's tool calls can actually do.
     Enforcement is in-process (not OS-level).

TB4: ════ Path Validation Boundary ════
     file_read is restricted to input_dir and files_dir.
     file_write is restricted to output_dir. Path traversal
     is blocked via resolve() + is_relative_to(). This
     prevents stages from reading/writing arbitrary files.

TB5: ════ Pipeline Trust Boundary ════
     Pipeline definitions (manifests, skills) are loaded from
     ~/.huginn/pipelines/ without signature verification.
     Skills declare their own tool permissions. A malicious
     skill file can grant itself shell + network access.
     This boundary assumes the operator authored or
     reviewed all pipeline content.
```

## Entry Points

| ID | Entry Point | Trust Level | Notes |
|----|-------------|-------------|-------|
| EP1 | CLI invocation (`huginn run`) | Trusted operator | Local shell command. Operator provides pipeline name and input file. No remote access, no API. |
| EP2 | Pipeline definitions (`~/.huginn/pipelines/`) | Trusted-but-unverified | Manifest + skill files loaded from disk. Skills declare their own tool permissions. No signing, no integrity checks. Anyone who can write to `~/.huginn/` can modify pipelines. |
| EP3 | Model completions (DF5) | Untrusted content from trusted service | Model output drives tool calls. The model decides which tools to invoke and with what arguments. A compromised or prompt-injected model can request any tool the skill declares. |
| EP4 | Ollama API (C4) | Trusted service, unauthenticated | No auth on Ollama. Any LAN host can query the Ollama API. Conversation context (including pipeline input) is sent unencrypted. A MitM on the LAN could inject model responses. |
| EP5 | web_fetch responses (DF9) | Untrusted internet content | URLs fetched by web_fetch return arbitrary content that becomes part of the model's conversation context. Indirect prompt injection vector. |
| EP6 | Pipeline input files (DF1) | Operator-provided, potentially untrusted | Input files may contain content from external sources (articles, docs, data). This content is sent to the model and may influence tool call decisions. |

---

Review this architecture inventory before I proceed to Q2 (threats). Anything to add, correct, or refine?
