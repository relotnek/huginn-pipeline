# Manifest Schema Reference

The `manifest.yaml` is the pipeline definition file. It lives at the root of a pipeline folder and defines stages, models, data flow, and constraints.

## Complete Schema

```yaml
# Required: pipeline identity
name: pipeline-name              # Lowercase, hyphenated identifier
description: What this pipeline does in one sentence
version: "1.0"                   # Semantic version (quote to prevent YAML number parsing)

# Optional: defaults applied to all stages unless overridden
defaults:
  backend: i3                    # Default backend name (from ~/.huginn/config.yaml)
  timeout_minutes: 60            # Default timeout per stage

# Required: ordered list of stages
stages:
  - name: stage-name             # Unique identifier for this stage
    skill: skills/01-name.md     # Path to skill file, relative to pipeline dir
    model: qwen2.5:7b            # Model name (must match backend's model list)
    backend: i3                  # Optional: override default backend
    input: $pipeline_input       # What this stage reads (see Input Wiring below)
    output: analysis.json        # Filename this stage produces
    files:                       # Optional: reference files mounted read-only
      - files/style-guide.md
      - files/examples.md
    tools:                       # Optional: tools available to the agent
      - file_read
      - file_write
    constraints:                 # Optional: sandbox restrictions
      network: false
      shell: false
      timeout_minutes: 30
    verification:                # Optional: checks run on output
      - "Output must be valid JSON"
      - "Output is 150-300 words"

# Optional: what to do when pipeline completes
on_complete:
  output_file: final-output.md   # Which file is the final deliverable
```

## Field Reference

### Top-Level Fields

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `name` | Yes | string | Pipeline identifier (lowercase, hyphenated) |
| `description` | Yes | string | One-line description |
| `version` | Yes | string | Semantic version (quoted) |
| `defaults` | No | object | Default settings for all stages |
| `stages` | Yes | list | Ordered list of stage definitions |
| `on_complete` | No | object | Post-completion actions |

### Stage Fields

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `name` | Yes | string | Unique stage identifier |
| `skill` | Yes | string | Path to skill file (relative to pipeline dir) |
| `model` | Yes | string | Model name for this stage |
| `backend` | No | string | Override default backend |
| `input` | Yes | string or list | Input source(s) |
| `output` | Yes | string | Output filename |
| `files` | No | list | Reference files mounted read-only |
| `tools` | No | list | Tools available to the agent |
| `constraints` | No | object | Sandbox restrictions |
| `verification` | No | list | Quality checks on output |

## Input Wiring Rules

The `input` field tells a stage where to get its data:

| Value | Meaning |
|-------|---------|
| `$pipeline_input` | The file/directory the user provided via `--input` |
| `analysis.json` | A file produced by a prior stage's `output` field |
| List of filenames | Multiple inputs from different prior stages |

### Single input from prior stage

```yaml
- name: draft
  input: analysis.json        # reads from whatever stage produced analysis.json
  output: draft.md
```

### Multiple inputs

```yaml
- name: revise
  input:
    - draft.md                 # from the draft stage
    - slop-report.json         # from the slop-filter stage
  output: final-post.md
```

### First stage

```yaml
- name: analyze
  input: $pipeline_input       # REQUIRED for first stage
  output: analysis.json
```

## Output Naming

Use descriptive filenames with appropriate extensions:

| Extension | Use For |
|-----------|---------|
| `.json` | Structured data (analysis, reports, classifications) |
| `.md` | Prose content (drafts, posts, documentation) |
| `.yaml` | Structured config-like output |
| `.txt` | Plain text |

The agent auto-detects JSON content and saves with `.json` extension, but explicit naming in the manifest is clearer.

## Constraints Reference

| Constraint | Default | When to Enable |
|-----------|---------|----------------|
| `network: false` | Default | Enable only for stages that need web access |
| `shell: false` | Default | Enable only for stages that need shell commands |
| `timeout_minutes: 60` | Default | Increase for stages with large inputs or many iterations |

## Tools Reference

| Tool | Description | When to Include |
|------|-------------|----------------|
| `file_read` | Read files from input and reference files directories | Always (default) |
| `file_write` | Write files to output directory | Stages that produce structured output |

## Model Name Format

Model names must exactly match what the backend expects:

```
# Ollama models
qwen2.5:7b           # family:size
qwen3:30b-a3b        # family:size-variant (MoE)
qwen3.6:27b          # family.version:size

# OpenRouter models
anthropic/claude-sonnet-4-6
meta-llama/llama-3.3-70b
google/gemini-2.5-pro
```
