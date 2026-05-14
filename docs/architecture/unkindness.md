# The Unkindness — Distributed Raven Communication

!!! warning "Status: In Design"
    This feature set is being designed and has not been implemented yet. This document captures the architecture, security model, and feature plan. Implementation will follow the resilience track (F106-F120).

---

## Overview

An **unkindness** is a flock of ravens. In Huginn, it's the architecture for distributed pipeline execution — multiple Huginn instances collaborating across machines, each with their own backends and tool runtimes.

Today, Huginn runs on one machine. You call `huginn run`, it executes stages locally using local or remote backends for inference. The tool runtime (file operations, web search, shell commands) always runs where the CLI runs.

The Unkindness extends this: you can dispatch ravens to **workers** — remote Huginn instances that have their own backends and their own tool runtimes. A raven sent to a worker runs *there*, with that worker's tools, that worker's filesystem, and that worker's network access. The dispatching Huginn only needs to send the job and collect the results.

```
              You (laptop)
              huginn run threat-model --input scope.md --worker heimdall
                    │
                    │  dispatch (pipeline + input)
                    ▼
         ┌─────────────────────┐
         │  Heimdall (worker)  │
         │  Huginn daemon      │
         │  Tools: local       │
         │  Backends: i3 local │
         │  Ollama + models    │
         └────────┬────────────┘
                  │
        ┌─────────┼─────────┐
        ▼         ▼         ▼
     Stage 1   Stage 2   Stage 3   ← ravens execute on worker
     research  threats   controls
        │         │         │
        └─────────┼─────────┘
                  │
                  ▼
         results returned to you
         huginn output <task-id>
```

## Why Not Just Remote Backends?

Remote backends already exist — you can point a stage at `--backend openrouter` and the model runs in the cloud while tools run locally. But that only decouples the **brain**. The **hands** (tools) are still local.

Workers decouple both:

| Current | With Workers |
|---------|-------------|
| Brain can be remote (backends) | Brain can be remote |
| Hands are always local | Hands can be remote too |
| Pipelines run on one machine | Pipelines run on any machine |
| One tool runtime | Multiple tool runtimes |
| One filesystem | Workers have their own filesystems |

This matters when:
- You want a pipeline to run on a server that has access to files your laptop doesn't (production logs, databases, git repos)
- You want to offload long-running research pipelines to a headless machine
- You want multiple machines processing different pipelines simultaneously
- You want the pipeline to keep running even when your laptop sleeps

## Architecture

### Three Roles

```
┌──────────────────────────┐
│  OPERATOR                │
│  Your laptop / CLI       │
│  huginn --worker X run   │
│  Dispatches jobs         │
│  Collects results        │
└──────────┬───────────────┘
           │
     ┌─────┴─────┐
     ▼           ▼
┌──────────┐  ┌──────────┐
│ WORKER A │  │ WORKER B │
│ heimdall │  │ cloud-vm │
│          │  │          │
│ Backends │  │ Backends │
│ Tools    │  │ Tools    │
│ Daemon   │  │ Daemon   │
└──────────┘  └──────────┘
```

**Operator**: The Huginn CLI that dispatches work. Doesn't need its own backends — just needs to know where workers are.

**Worker**: A Huginn instance running in daemon mode. Has its own `~/.huginn/` directory with backends, pipelines, skills, and tool runtime. Accepts task submissions over HTTP.

A single machine can be both operator and worker. Your laptop is an operator when you dispatch to heimdall, and a worker when something dispatches to you.

### Worker Configuration

Workers are declared in `~/.huginn/config.yaml` alongside backends:

```yaml
backends:
  i3:
    type: ollama
    url: http://192.168.2.135:11434
  mac:
    type: ollama
    url: http://localhost:11434
  openrouter:
    type: openrouter
    url: https://openrouter.ai/api/v1
    api_key_env: OPENROUTER_API_KEY

workers:
  heimdall:
    url: http://192.168.2.135:8080
    api_key_env: HUGINN_HEIMDALL_KEY
    description: "i3 server — always-on, small models, local tools"
    capabilities:
      - shell
      - git
      - network
    pipelines:                    # pipelines deployed on this worker
      - post-generator
      - threat-model-4q
      - code-reviewer

  cloud:
    url: https://huginn.example.com:8080
    api_key_env: HUGINN_CLOUD_KEY
    description: "Cloud VM — web research, large file processing"
    capabilities:
      - shell
      - git
      - network
      - web_search
      - web_fetch
```

### Dispatch Flow

```
1. Operator: huginn run threat-model-4q --input scope.md --worker heimdall
2. CLI resolves worker config from ~/.huginn/config.yaml
3. CLI authenticates with worker (API key)
4. CLI uploads: pipeline name + input files
5. Worker validates: pipeline exists locally, input accepted
6. Worker creates task, begins execution
7. Worker returns: task ID
8. Operator can poll: huginn --worker heimdall status <task-id>
9. Operator can retrieve: huginn --worker heimdall output <task-id> --download
```

### Pipeline Deployment

Workers need their own copy of the pipeline (skills, manifest, reference files). Two approaches:

**Push model** (recommended for now): Deploy pipelines to workers explicitly.
```bash
# Deploy a pipeline to a worker
huginn deploy threat-model-4q --worker heimdall

# This syncs: manifest.yaml, skills/, files/, prompts/
# Worker-side: pipeline lands in worker's ~/.huginn/pipelines/
```

**Pull model** (future): Worker fetches pipeline definitions from a shared registry (git repo, S3 bucket, etc.).

### Result Retrieval

Workers store task output in their own `~/.huginn/tasks/`. The operator retrieves results over the API:

```bash
# View output
huginn --worker heimdall output <task-id>

# Download to local disk
huginn --worker heimdall output <task-id> --download ./results/

# Stream logs in real-time
huginn --worker heimdall logs <task-id> --follow
```

---

## Security Model

Distributed execution introduces real security concerns. Ravens execute tools — shell commands, file operations, network requests — on the worker machine. A compromised dispatch channel or a malicious pipeline could cause damage.

### Threat Surface

| Threat | Impact | Mitigation |
|--------|--------|------------|
| Unauthorized task submission | Attacker runs arbitrary pipelines on worker | API key authentication + allowlist |
| Pipeline injection | Malicious skill prompts trick model into harmful tool calls | Skill allowlisting per worker, tool constraint enforcement |
| Credential theft | API keys in transit or in config | TLS for all worker communication, env-var-based keys |
| Lateral movement | Compromised worker accesses other workers | Workers don't trust each other, operator is the hub |
| Data exfiltration | Sensitive input data sent to untrusted worker | Pipeline-to-worker mapping in config, operator controls routing |
| Replay attacks | Captured dispatch replayed | Nonce + timestamp in signed requests |

### Authentication

**Worker ↔ Operator**: Mutual API key authentication.
- Operator includes `Authorization: Bearer <key>` on every request
- Workers validate against a configured key hash (never store plaintext)
- Keys are per-worker, stored in environment variables

**No worker-to-worker trust**: Workers never communicate directly. The operator is always the hub. This prevents a compromised worker from pivoting to others.

### Authorization

**Pipeline allowlisting**: Workers declare which pipelines they accept in their config. The worker rejects any pipeline not in its allowlist.

```yaml
# Worker-side config
allowed_pipelines:
  - post-generator
  - threat-model-4q
  - code-reviewer
# Anything else → 403 Forbidden
```

**Tool capability declaration**: Workers declare what tool capabilities they expose. Pipelines that need capabilities the worker doesn't have are rejected at dispatch time, not at runtime.

**Operator-side routing**: The operator's config declares which pipelines go to which workers. This is the first gate — the CLI won't even attempt to send a pipeline to a worker that isn't configured for it.

### Transport Security

- **TLS required** for any worker not on localhost/LAN
- API keys must never appear in URLs (header-only)
- Worker config supports `tls_verify: false` for self-signed certs on LAN (with warning)

---

## Relation to Existing Architecture

The Unkindness builds on top of existing features:

| Existing | Unkindness Extension |
|----------|---------------------|
| `--backend` routes **inference** to remote | `--worker` routes **entire execution** to remote |
| `--bg` runs locally in background | `--worker` runs remotely in background |
| `huginn status/output/logs` for local tasks | Same commands with `--worker` prefix for remote |
| `~/.huginn/config.yaml` backends section | New `workers` section alongside backends |
| `model_map` translates model names per backend | Workers may have different models; pipeline must be compatible |
| HTTP API (planned, F070-F076) | Workers ARE the HTTP API, with auth |

The Unkindness is not a replacement for the HTTP API — it IS the HTTP API, with the addition of worker identity, authentication, and pipeline deployment.

---

## Naming Convention

| Term | Meaning |
|------|---------|
| **Raven** | A single stage execution — an agent with a skill, model, and tools |
| **Flock** | A pipeline — an ordered group of ravens chained by data flow |
| **Unkindness** | The distributed system — multiple Huginn instances sharing work |
| **Worker** | A Huginn instance running in daemon mode, accepting dispatched ravens |
| **Operator** | The Huginn CLI that dispatches work to workers |
| **Roost** | A worker's `~/.huginn/` directory — where its pipelines, skills, and task data live |

---

## Implementation Phases

### Phase A: Worker Foundation (requires HTTP API)
- Worker config in `config.yaml`
- `huginn daemon` starts worker (leverages F070-F071)
- Worker authentication (API key)
- `huginn --worker <name> status/output/logs` proxying
- `huginn workers` command — list configured workers with status

### Phase B: Dispatch
- `huginn run <pipeline> --input <file> --worker <name>` dispatches to worker
- Input file upload to worker
- Task ID returned, stored locally for tracking
- Pipeline validation on worker side (exists + compatible)

### Phase C: Pipeline Deployment
- `huginn deploy <pipeline> --worker <name>` syncs pipeline to worker
- Checksum verification (operator and worker agree on pipeline version)
- `huginn --worker <name> pipelines` shows what's deployed remotely

### Phase D: Security Hardening
- Pipeline allowlisting on workers
- Tool capability declaration and enforcement
- TLS enforcement for non-LAN workers
- Request signing with nonce + timestamp
- Audit logging on workers

### Phase E: Multi-Worker Orchestration
- Dispatch different stages of one pipeline to different workers
- Worker health monitoring from operator
- Automatic failover between workers
- Cross-worker pipeline execution (stage 1 on heimdall, stage 2 on cloud-vm)
