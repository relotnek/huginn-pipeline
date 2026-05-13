# Skill Format Reference

Complete reference for the Huginn skill file format.

## Structure

A skill is a markdown file with YAML frontmatter:

```markdown
---
name: skill-identifier
model: qwen2.5:7b
temperature: 0.7
max_iterations: 5
tools: [file_read, file_write]
constraints:
  network: false
  shell: false
  timeout_minutes: 30
---

# Skill Title

[System prompt — sent directly to the model as instructions]

## Input
[What the skill expects to read]

## Output
[What the skill produces]

## Verification
1. First quality check
2. Second quality check
```

## Frontmatter Fields

### Required

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Unique identifier for the skill |
| `model` | string | Default model (can be overridden in manifest) |

### Optional

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `backend` | string | `null` (uses pipeline default) | Override which backend runs this skill |
| `temperature` | float | `0.7` | Model temperature |
| `max_iterations` | int | `10` | Max agent loop iterations |
| `tools` | list | `[file_read]` | Tools available during execution |
| `constraints.network` | bool | `false` | Internet access allowed? |
| `constraints.shell` | bool | `false` | Shell command access allowed? |
| `constraints.timeout_minutes` | int | `60` | Stage timeout |

## Body Sections

### System Prompt (Required)

Everything in the body (outside of special sections) becomes the system prompt. This is sent directly to the model. Be specific, include constraints, and give examples.

### ## Verification (Optional)

Defines automated quality checks. The agent loop runs these after each iteration:

```markdown
## Verification
1. Output must be valid JSON
2. Output is 150-300 words
3. No banned phrases from style guide
4. Output must contain 'security'
```

### Supported Verification Checks

| Check Type | Syntax | What It Does |
|------------|--------|-------------|
| Word count | `Output is 150-300 words` | Counts words, checks against range |
| JSON validity | `Output must be valid JSON` | Tries `json.loads()` on output |
| Banned phrases | `No banned phrases from style guide` | Checks against built-in banned word list |
| Content containment | `Output must contain 'keyword'` | Case-insensitive substring match |

When a check fails, the agent gets another iteration with feedback:

```
Your output failed these checks:
- Output is 150-300 words (actual: 312 words)
- No banned phrases from style guide (found: leverage, robust)

Please revise your output to address all verification failures.
```

## Override Rules

When a skill is used in a pipeline manifest:

1. The manifest stage's `model` overrides the skill's `model`
2. The manifest stage's `backend` overrides the skill's `backend`
3. Manifest `verification` rules are **merged** with skill verification rules
4. The skill's `tools`, `constraints`, and `max_iterations` are used by the agent loop
5. The skill body (system prompt) is sent to the model as-is

## Skill Locations

| Location | Scope | How to List |
|----------|-------|-------------|
| `~/.huginn/pipelines/<name>/skills/` | Pipeline-specific | Referenced in manifest |
| `~/.huginn/skills/` | Global, reusable | `huginn skills` |

## Validation Checklist

Before using a skill in a pipeline:

- [ ] File has YAML frontmatter between `---` markers
- [ ] `name` field is present
- [ ] `model` field is present and matches an available model
- [ ] Body contains a meaningful system prompt
- [ ] If the skill references input files, the pipeline wiring provides them
- [ ] If the skill produces JSON output, subsequent stages expect that format
- [ ] Verification rules match what the skill actually outputs
