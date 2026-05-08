# Huginn

*Send out the ravens. They come back with results.*

---

## What Is This?

Huginn is a system for building and running autonomous LLM pipelines on your own hardware. You describe what you want — "a pipeline that turns raw notes into LinkedIn posts in my voice" — and Huginn helps you design it, validate it, and then run it overnight while you sleep.

It has two parts:

**The Orchestrator** uses a frontier model (Claude Opus) to help you design pipelines interactively. It researches what models and skills you have available, proposes an architecture, optionally threat models the design, builds all the files, and tests the result. You pay for Opus once during the design phase.

**The Runner** executes those pipelines on local hardware — your i3 server, your MacBook, eventually your Pi cluster. Each pipeline is a chain of stages, each running a specialized local model inside a Docker sandbox. Once built, pipelines run for free, forever, on hardware you control.

The core insight: **the skill file is the product, not the model.** A well-written skill — the system prompt, the constraints, the verification rules, the reference files — is what makes a cheap 7B model perform like a frontier model on a narrow task. You use frontier intelligence to *author* skills, and local models to *execute* them at scale.

---

## How It Works

### You Create a Pipeline

A pipeline is a folder with everything needed to run a multi-stage workflow:

```
~/.huginn/pipelines/post-generator/
├── manifest.yaml       ← Defines the stages, models, and data flow
├── skills/             ← One skill file per stage (the intelligence)
│   ├── 01-analyze.md
│   ├── 02-draft.md
│   ├── 03-slop-filter.md
│   └── 04-revise.md
├── prompts/            ← Reusable prompt templates
├── files/              ← Reference docs skills can read (style guides, examples)
├── tools/              ← Custom tools for this pipeline
├── validation/         ← Research, design, and threat model docs
└── README.md
```

The manifest defines what happens in what order:

```
analyze (qwen3:8b) → draft (qwen3:30b-a3b) → slop-filter (qwen3:8b) → revise (qwen3:30b-a3b)
```

Each stage gets its own Docker container, its own model, its own skill prompt, and only the files and tools it's declared to need. Stage outputs flow forward as inputs to the next stage.

### You Run It

```bash
huginn run post-generator --input ./raw-notes.md
```

Huginn reads the manifest, creates a task directory, and executes each stage in sequence. Each stage runs in an isolated Docker container that can only see its input files, its reference docs, and the Ollama API. When the last stage finishes, the final output lands in the task's output directory.

If the pipeline crashes at stage 3 of 4 (power outage, OOM, network blip), you rerun and it picks up where it left off — stages 1-2 are already done, their output is preserved.

### You Sleep

Queue up a batch of tasks before bed:

```bash
huginn batch post-generator --input-dir ./this-weeks-sources/
```

Wake up to results.

---

## The Validation Cycle

Pipelines that handle real work — especially anything touching client data — go through a structured creation process:

```
RESEARCH    → What models, skills, and tools are available?
    ↓          What are the actual requirements?
DESIGN      → Which stages? Which model per stage? What data flows where?
    ↓  ↑        Iterate until the design satisfies the research.
THREAT MODEL → What if a stage hallucinates? What if input is malicious?
    ↓  ↑        What data is exposed? What are the failure modes?
BUILD       → Generate the pipeline folder with all artifacts.
    ↓
TEST        → Run on sample input. Try adversarial input. Review output.
    ↓  ↑        Iterate until tests pass.
VALIDATED   → Pipeline is ready for autonomous execution.
```

Each phase can circle back to prior phases. The Orchestrator (Opus) guides you through this interactively. For low-risk pipelines (a simple text classifier), skip the threat model and go straight from design to build. For anything touching Asgard client engagements, run the full cycle.

All validation artifacts (research notes, design doc, threat model, test results) are stored in the pipeline's `validation/` folder so you can review or refine later.

---

## What's a Skill?

A skill is a markdown file that defines everything a sub-agent needs to do its job. It's the thing that makes a cheap model smart on a narrow task.

```markdown
---
name: linkedin-writer
model: qwen3:30b-a3b
backend: i3
temperature: 0.7
max_iterations: 5
tools: [file_read, file_write]
constraints:
  network: false
  shell: false
  timeout_minutes: 30
---

# LinkedIn Writer — Ken's Voice

You are writing LinkedIn posts as Ken Toler, who runs Asgard Security.

VOICE RULES:
- No sentence stops and poses
- Sentences accumulate, they don't break into crisp units
- Qualifiers live mid-thought: "sort of", "I think", "actually"
- Start with operational reality, not a hot take
- End human, not with a mic drop
- Never write "leverage", "best practices", "robust"

[... full prompt with banned phrases, calibration examples, etc.]

## Verification
1. No banned phrases appear in output
2. Output is 150-300 words
3. First sentence describes a situation, not a thesis
```

Skills can be global (reusable across pipelines) or pipeline-specific. The agent loop that runs inside each container is generic — the same code powers every stage. The skill prompt is what makes each one behave differently.

---

## The Agent Loop

Every stage runs the same generic Python agent inside its Docker container:

```
1. Load skill (system prompt, rules, verification checks)
2. Load checkpoint if resuming from interruption
3. Read input files and reference documents

Loop until done or max_iterations reached:
    OBSERVE  → Read current state (input, partial output)
    THINK    → Call Ollama with skill prompt + state
    ACT      → Write files, run allowed tools
    VERIFY   → Check output against skill's verification rules
               If checks fail, feed failure back into next iteration
    CHECKPOINT → Save progress (survive crashes)

4. Write final output and status
```

The loop is simple by design. The intelligence is in the skill, not the code.

---

## Sandboxing

Each stage runs in a Docker container with strict controls:

- **Read-only input**: the stage can read its input files but can't modify them
- **Read-write output**: results go here and only here
- **Read-only reference files**: style guides, examples, whatever the manifest declares
- **Network**: restricted to the Ollama API endpoint only (no internet unless the skill explicitly allows it)
- **Resource limits**: CPU and memory caps prevent one stage from eating the whole server
- **No host access**: the container can't see the host filesystem beyond its mounted directories
- **Timeout**: stages that run too long are killed, partial output is preserved

This means a misbehaving model can't leak data, overwrite files, or take down the server. It can only produce output in its designated directory.

---

## Infrastructure

### Current Hardware

```
┌───────────────────────┐     ┌─────────────────────────┐
│  MacBook Pro M3 Max   │     │  i3 Server (heimdall)   │
│  64GB unified memory  │     │  32GB RAM, Debian        │
│  Ollama (native)      │     │  Ollama (Docker)         │
│  Big models: 27B-70B  │     │  Small models: 0.5B-8B   │
│  Overnight batch jobs  │     │  Always-on API server    │
│  localhost:11434      │     │  192.168.2.135:11434     │
└───────────────────────┘     └─────────────────────────┘
```

Pipelines can route stages to different backends. The manifest specifies which backend each stage uses — analysis and filtering on the i3 (small fast models), prose generation on the Mac (big models), or wherever the right model is available.

### Models

| Model | Type | Best For |
|-------|------|----------|
| qwen3:8b | Dense | Analysis, extraction, classification |
| qwen3:30b-a3b | MoE (3B active) | Fast + smart — good general workhorse |
| qwen3.6:27b | Dense | Best prose quality (Mac only) |
| nomic-embed-text | Embedding | Semantic search, dedup, RAG |
| qwen2.5:0.5b | Dense tiny | Fast classification, yes/no routing |

MoE (Mixture of Experts) models activate only a fraction of their parameters per token. The 30B-A3B has 30B total knowledge but only computes 3B worth of math per token — it runs faster than a dense 7B while being smarter.

---

## Example Pipelines

### Post Generator
Source material → analyze themes → draft in Ken's voice → filter AI slop → verify and revise → final post

### Code Reviewer
Source code → inventory files → per-function security analysis → cross-reference patterns → generate docs → assemble report

### Content Factory
Source material → classify type → extract key points → generate drafts for each platform (LinkedIn, blog, Twitter) → style check all → revise all → package

### Slack Digest
Pull Slack messages → classify (action item, decision, FYI, blocker) → extract structured data → summarize by theme → flag items needing response

### Security Doc Generator
Scope description → enumerate STRIDE threats → score risks → plan remediations → write executive summary → write technical deep-dive → assemble deliverable

---

## Roadmap

**Phase 1 — Runner (current)**: Hand-write pipeline folders, run them with `huginn run`. Sequential stages, Docker sandboxing, checkpoint/resume, verification.

**Phase 2 — Orchestrator**: `huginn create` uses Opus to design pipelines interactively. Full validation cycle. Shell and network tools with per-skill permissions.

**Phase 3 — Infrastructure**: Parallel execution, task queue, HTTP API, cron scheduling, conditional stage routing, cross-backend dispatch.

---

## Philosophy

The expensive part of AI isn't inference — it's knowing what to ask for. A well-written skill file encodes weeks of prompt engineering, domain expertise, and quality standards into a reusable artifact. The skill is the intellectual property. The model is a commodity.

Huginn lets you invest frontier-model intelligence into skill creation once, then run those skills on commodity local models indefinitely. Your data never leaves your hardware. Your costs are fixed. Your pipelines get better every time you refine a skill.

Send out the ravens. They come back with results.
