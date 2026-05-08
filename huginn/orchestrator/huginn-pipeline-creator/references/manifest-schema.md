# Huginn Manifest Schema Reference

The manifest.yaml is the pipeline definition file. It lives at the root of a pipeline folder and defines stages, models, data flow, and constraints.

## Complete Schema

```yaml
# Required: pipeline identity
name: pipeline-name              # Lowercase, hyphenated identifier
description: What this pipeline does in one sentence
version: "1.0"                   # Semantic version, quoted to prevent YAML number parsing

# Optional: defaults applied to all stages unless overridden
defaults:
  backend: i3                    # Default Ollama backend name (from ~/.huginn/config.yaml)
  timeout_minutes: 60            # Default timeout per stage

# Required: ordered list of stages
stages:
  - name: stage-name             # Unique identifier for this stage
    skill: skills/01-name.md     # Path to skill file, relative to pipeline dir
    model: qwen2.5:7b            # Ollama model name (must match `ollama list` exactly)
    backend: i3                  # Optional: override default backend
    input: $pipeline_input       # What this stage reads (see Input Wiring below)
    output: analysis.json        # Filename this stage produces
    files:                       # Optional: reference files mounted read-only
      - files/style-guide.md
      - files/examples.md
    tools:                       # Optional: tools available to the agent
      - file_read                # Always available
      - file_write               # For stages that produce output files
    constraints:                 # Optional: sandbox restrictions
      network: false             # Can this stage access the internet?
      shell: false               # Can this stage run shell commands?
      timeout_minutes: 30        # Override default timeout for this stage
    verification:                # Optional: checks run on output
      - "Output must be valid JSON"
      - "Output is 150-300 words"

# Optional: what to do when pipeline completes
on_complete:
  output_file: final-output.md   # Which file is the final deliverable
```

## Input Wiring Rules

The `input` field tells a stage where to get its data:

| Value | Meaning |
|-------|---------|
| `$pipeline_input` | The file/directory the user provided via `--input` |
| `analysis.json` | A file produced by a prior stage's `output` field |
| List of filenames | Multiple inputs from different prior stages |

### Single input from prior stage:
```yaml
- name: draft
  input: analysis.json        # Reads from whatever stage produced analysis.json
  output: draft.md
```

### Multiple inputs:
```yaml
- name: revise
  input:
    - draft.md                 # From the draft stage
    - slop-report.json         # From the slop-filter stage
  output: final-post.md
```

### First stage always uses pipeline input:
```yaml
- name: analyze
  input: $pipeline_input       # REQUIRED for first stage
  output: analysis.json
```

## Output Naming Conventions

Use descriptive filenames with appropriate extensions:

- `.json` for structured data (analysis, reports, classifications)
- `.md` for prose content (drafts, posts, documentation)
- `.yaml` for structured config-like output
- `.txt` for plain text

The agent auto-detects JSON content and saves with `.json` extension, but explicit naming in the manifest is clearer.

## Constraints Reference

| Constraint | Default | When to Enable |
|-----------|---------|----------------|
| `network: false` | Default | Enable only for stages that need web access (research, API calls) |
| `shell: false` | Default | Enable only for stages that need to run commands (git, build tools) |
| `timeout_minutes: 60` | Default | Increase for stages with large inputs or many iterations |

## Tools Reference

| Tool | Description | When to Include |
|------|-------------|----------------|
| `file_read` | Read files from input and files directories | Always (default) |
| `file_write` | Write files to output directory | Stages that produce output |

## Model Name Format

Model names must exactly match what Ollama reports. Common format:

```
qwen2.5:7b          # family:size
qwen3:8b             # family:size
qwen3:30b-a3b        # family:size-variant (MoE)
qwen3.6:27b          # family.version:size
llama3.2:3b          # family:size
nomic-embed-text     # no size tag for some models
```

Check with: `docker exec -it ollama ollama list` (on i3) or `ollama list` (on Mac)

## Complete Example: Post Generator

```yaml
name: post-generator
description: Generate LinkedIn posts in Ken's voice from source material
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
    files: [files/voice-rules.md]
    output: draft.md
    tools: [file_read, file_write]

  - name: slop-filter
    skill: skills/03-slop-filter.md
    model: qwen2.5:7b
    input: draft.md
    output: slop-report.json
    tools: [file_read]

  - name: revise
    skill: skills/04-revise.md
    model: qwen3:30b-a3b
    input:
      - draft.md
      - slop-report.json
    files: [files/voice-rules.md]
    output: final-post.md
    tools: [file_read, file_write]
    verification:
      - "Output is 150-300 words"
      - "No banned phrases from style guide"

on_complete:
  output_file: final-post.md
```
