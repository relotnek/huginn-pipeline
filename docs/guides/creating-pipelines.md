# Creating Pipelines

A pipeline is a folder that defines a multi-stage LLM workflow. This guide covers how to create one from scratch.

## Pipeline Structure

```
~/.huginn/pipelines/my-pipeline/
├── manifest.yaml           # Stage definitions, models, data flow
├── skills/                 # One skill file per stage
│   ├── 01-analyze.md
│   ├── 02-draft.md
│   └── 03-review.md
├── files/                  # Reference docs (style guides, examples)
│   └── style-guide.md
└── README.md               # Optional documentation
```

## The Manifest

The `manifest.yaml` is the pipeline's execution graph. It defines what happens in what order:

```yaml
name: my-pipeline
description: What this pipeline does in one sentence
version: "1.0"

defaults:
  backend: i3
  timeout_minutes: 60

stages:
  - name: analyze
    skill: skills/01-analyze.md
    model: qwen2.5:7b
    input: $pipeline_input
    output: analysis.json
    tools: [file_read]

  - name: draft
    skill: skills/02-draft.md
    model: qwen3:30b-a3b
    input: analysis.json
    files: [files/style-guide.md]
    output: draft.md
    tools: [file_read, file_write]

  - name: review
    skill: skills/03-review.md
    model: qwen2.5:7b
    input: draft.md
    output: final.md
    tools: [file_read, file_write]
    verification:
      - "Output is 150-300 words"

on_complete:
  output_file: final.md
```

## Input Wiring

Every stage declares where its input comes from:

### First Stage — Pipeline Input

The first stage always reads from the user-provided input:

```yaml
- name: analyze
  input: $pipeline_input       # whatever the user passed via --input
```

### Subsequent Stages — Prior Stage Output

Later stages reference files produced by earlier stages:

```yaml
- name: draft
  input: analysis.json         # reads from analyze stage's output
```

### Multiple Inputs

A stage can read from multiple prior stages:

```yaml
- name: revise
  input:
    - draft.md                 # from the draft stage
    - slop-report.json         # from the slop-filter stage
```

## Reference Files

Stages can mount read-only reference files:

```yaml
- name: draft
  files:
    - files/style-guide.md
    - files/examples.md
```

These are available to the skill via the `file_read` tool. Place the actual files in your pipeline's `files/` directory.

## Constraints

Control what each stage is allowed to do:

```yaml
- name: analyze
  constraints:
    network: false             # no internet access (default)
    shell: false               # no shell commands (default)
    timeout_minutes: 30        # stage-level timeout override
```

## Verification Rules

Add quality checks at the manifest level (merged with any rules in the skill file):

```yaml
- name: revise
  verification:
    - "Output is 150-300 words"
    - "No banned phrases from style guide"
    - "Output must contain 'security'"
```

## Backend Routing

Route different stages to different backends based on task needs:

```yaml
stages:
  - name: classify
    backend: i3                # fast, always-on, small model
    model: qwen2.5:0.5b

  - name: analyze
    backend: i3                # structured extraction
    model: qwen2.5:7b

  - name: generate
    backend: mac               # prose quality needs bigger model
    model: qwen3.6:27b

  - name: verify
    backend: openrouter        # frontier model for judgment
    model: anthropic/claude-sonnet-4-6
```

## Design Patterns

### Analysis-Draft-Review

The most common pattern. Separate understanding from creation from quality control:

```
source → analyze (extract structure) → draft (generate content) → review (check quality) → output
```

Each stage has different requirements — analysis needs precision (low temp, structured output), drafting needs creativity (higher temp, reference files), review needs judgment (low temp, verification rules).

### Filter Chain

Multiple quality filters in sequence:

```
draft → slop-filter → tone-check → fact-check → final
```

Each filter reads the same draft and produces a report. The final stage reads all reports and revises.

### Fan-Out (Future)

Generate multiple outputs from one input:

```
source → analyze → [linkedin-draft, blog-draft, twitter-draft] → package
```

!!! note
    Parallel stage execution is planned for Phase 4. Currently, stages run sequentially.

## Deploying a Pipeline

Copy your pipeline folder to Huginn's pipeline directory:

```bash
cp -r my-pipeline ~/.huginn/pipelines/
```

Verify it's visible:

```bash
huginn pipelines
```

Run it:

```bash
huginn run my-pipeline --input ./my-input.md
```

## Next Steps

- [Manifest Schema Reference](../reference/manifest-schema.md) — every field documented
- [Writing Skills](writing-skills.md) — craft the skills that power your stages
- [Tutorial: Your First Pipeline](../tutorials/first-pipeline.md) — step-by-step walkthrough
