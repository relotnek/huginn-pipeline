# Tutorial: Multi-Backend Routing

Route pipeline stages to different backends based on task requirements — cheap models on always-on hardware for simple tasks, big models on your GPU for quality-critical stages, and frontier models via OpenRouter when you need the best.

## The Scenario

We'll build a pipeline that reviews a code file:

1. **inventory** (i3, small model) — Scan the file and list functions/classes
2. **analyze** (i3, medium model) — Security analysis of each function
3. **report** (openrouter, frontier model) — Produce an executive-quality report

## Prerequisites

You need at least two backends configured. Check your `~/.huginn/config.yaml`:

```yaml
backends:
  i3:
    type: ollama
    url: http://192.168.2.135:11434
  openrouter:
    type: openrouter
    api_key_env: OPENROUTER_API_KEY
default_backend: i3
```

Make sure your OpenRouter API key is set:

```bash
export OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

## Create the Pipeline

```bash
mkdir -p ~/.huginn/pipelines/code-review/skills
```

### Manifest

Create `~/.huginn/pipelines/code-review/manifest.yaml`:

```yaml
name: code-review
description: Security-focused code review with multi-backend routing
version: "1.0"

defaults:
  timeout_minutes: 30

stages:
  - name: inventory
    skill: skills/01-inventory.md
    model: qwen2.5:7b
    backend: i3                    # cheap, always-on
    input: $pipeline_input
    output: inventory.json
    tools: [file_read]

  - name: analyze
    skill: skills/02-analyze.md
    model: qwen2.5:7b
    backend: i3                    # structured analysis, medium model
    input: inventory.json
    output: analysis.json
    tools: [file_read]

  - name: report
    skill: skills/03-report.md
    model: anthropic/claude-sonnet-4-6
    backend: openrouter            # frontier model for quality writing
    input: analysis.json
    output: review-report.md
    tools: [file_read, file_write]
    verification:
      - "Output must contain 'Finding'"

on_complete:
  output_file: review-report.md
```

### Skills

**`skills/01-inventory.md`** — Fast scan with small model:

```markdown
---
name: code-inventory
model: qwen2.5:7b
temperature: 0.1
max_iterations: 2
tools: [file_read]
---

# Code Inventory

Read the source code file and produce a JSON inventory of all functions,
classes, and methods. Include line count estimates.

Output ONLY a JSON object:

{
  "language": "python",
  "file_summary": "What this file does in one sentence",
  "items": [
    {
      "type": "function | class | method",
      "name": "function_name",
      "line_count": 15,
      "parameters": ["param1", "param2"],
      "description": "What it does in one sentence"
    }
  ]
}

## Verification
1. Output must be valid JSON
```

**`skills/02-analyze.md`** — Security analysis:

```markdown
---
name: security-analyzer
model: qwen2.5:7b
temperature: 0.2
max_iterations: 3
tools: [file_read]
---

# Security Analyzer

Read the code inventory and the original source file.
For each function/method, assess security concerns.

Output a JSON object:

{
  "findings": [
    {
      "function": "function_name",
      "severity": "critical | high | medium | low | info",
      "category": "injection | auth | crypto | data-exposure | etc",
      "description": "What the issue is",
      "recommendation": "How to fix it"
    }
  ],
  "overall_risk": "high | medium | low",
  "summary": "One paragraph overall assessment"
}

Focus on:
- Input validation gaps
- Authentication/authorization issues
- Hardcoded secrets or credentials
- SQL injection, command injection, path traversal
- Insecure cryptographic usage
- Data exposure in logs or error messages

If you find no issues, say so — don't invent problems.

## Verification
1. Output must be valid JSON
```

**`skills/03-report.md`** — Executive report with frontier model:

```markdown
---
name: report-writer
model: anthropic/claude-sonnet-4-6
temperature: 0.5
max_iterations: 2
tools: [file_read, file_write]
---

# Security Review Report Writer

Read the security analysis JSON and produce a professional
security review report in markdown.

Structure the report as:

# Security Review Report

## Executive Summary
[2-3 sentences: what was reviewed, overall risk level, key concern]

## Findings

### Finding 1: [Title]
- **Severity:** Critical/High/Medium/Low
- **Category:** [category]
- **Description:** [clear explanation]
- **Recommendation:** [actionable fix]

[Repeat for each finding, ordered by severity]

## Recommendations Summary
[Prioritized list of what to fix first]

Rules:
- Write for a technical audience that includes both developers and managers
- Be specific — reference function names and line numbers from the analysis
- If no findings exist, say the code looks clean and explain why
- Don't pad the report with generic security advice
```

## Run It

```bash
huginn run code-review --input ./my-code.py
```

Watch the routing in action:

```
Task c4d5e6f7 — running pipeline 'code-review' (3 stages)
  Stage 1/3 'inventory' (qwen2.5:7b on i3)...
    ✓ 5.2s, 1 iterations, 423 tokens
  Stage 2/3 'analyze' (qwen2.5:7b on i3)...
    ✓ 12.8s, 1 iterations, 891 tokens
  Stage 3/3 'report' (anthropic/claude-sonnet-4-6 on openrouter)...
    ✓ 8.3s, 1 iterations, 1547 tokens
  ✓ Pipeline complete in 26.3s
```

Stages 1 and 2 ran on the i3 (free, local). Stage 3 hit OpenRouter for Claude's writing quality (paid, but only for the final report).

## Cost Optimization

The key insight: **only use expensive models where they matter.**

| Stage | Model Cost | Why This Backend |
|-------|-----------|-----------------|
| inventory | Free (local) | Simple scan, any model works |
| analyze | Free (local) | Structured extraction, 7B is sufficient |
| report | ~$0.01-0.05 | Prose quality matters for the deliverable |

You could run all three stages on OpenRouter, but you'd pay for work that a local 7B model handles equally well.

## Fallback: All Local

If OpenRouter is unavailable, run everything locally:

```bash
huginn run code-review --input ./my-code.py --backend i3
```

The `--backend` flag overrides all stage backend settings. The report quality won't be as good with a 7B model, but it works.

## What You Learned

- Per-stage backend routing in the manifest
- Using OpenRouter alongside local Ollama
- Cost optimization by matching model to task
- Runtime backend override with `--backend`
- Brain/hands separation — tools run locally regardless of backend

## Next Steps

- [Using Backends](../guides/backends.md) — full backend configuration guide
- [Models Reference](../reference/models.md) — model inventory and selection
