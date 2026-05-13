# Writing Skills

Skills are the core craft of Huginn. A skill file is what makes a cheap 7B model perform like a frontier model on a narrow task. This guide covers how to write effective skills.

## Skill File Format

A skill is a markdown file with YAML frontmatter:

```markdown
---
name: source-analyzer
model: qwen2.5:7b
temperature: 0.3
max_iterations: 3
tools: [file_read]
---

# Source Material Analyzer

Read the input source material and extract a structured analysis.

Output ONLY a JSON object with these fields:
...

## Verification
1. Output must be valid JSON
```

The frontmatter configures the agent. The body **is** the system prompt — it's sent directly to the model.

## Frontmatter Fields

### Required

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Unique identifier for the skill |
| `model` | string | Model to use (e.g., `qwen2.5:7b`, `anthropic/claude-sonnet-4-6`) |

### Optional

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `backend` | string | pipeline default | Override which backend runs this skill |
| `temperature` | float | `0.7` | Model temperature (lower = more deterministic) |
| `max_iterations` | int | `10` | Max agent loop iterations before stopping |
| `tools` | list | `[file_read]` | Tools available to the agent |
| `constraints.network` | bool | `false` | Can the agent access the internet? |
| `constraints.shell` | bool | `false` | Can the agent run shell commands? |
| `constraints.timeout_minutes` | int | `60` | Timeout for this stage |

## Writing Effective Prompts

### Be Specific About Output Format

Bad:
```markdown
Analyze the input and produce a summary.
```

Good:
```markdown
Output ONLY a JSON object with these fields:

{
  "core_idea": "The single most important point in 1-2 sentences",
  "themes": ["theme1", "theme2"],
  "target_audience": "Who would care about this",
  "key_facts": ["Specific facts worth including"]
}
```

Models follow structure. Give them a template and they'll fill it in.

### Include Constraints

Tell the model what **not** to do. This is often more effective than telling it what to do:

```markdown
Rules:
- No sentence should "stop and pose" (end with a dramatic standalone claim)
- Never write "leverage", "best practices", "robust", or "seamless"
- Do not open with a hot take or thesis statement
- Do not end with a call to action
```

### Use Reference Files

Skills can reference files mounted read-only in the stage's `files/` directory:

```markdown
Read the style guide in `voice-rules.md` before writing.
Apply every rule in the guide. If a rule conflicts with
your instincts, follow the rule.
```

The manifest declares which files are available:

```yaml
stages:
  - name: draft
    files: [files/voice-rules.md, files/examples.md]
```

### Calibrate With Examples

The most effective way to tune a skill is to include examples of good and bad output:

```markdown
## Good Output Example

"We finished a security assessment last month. Forty-seven findings 
across their AWS setup, but the interesting one wasn't technical..."

## Bad Output Example (DO NOT write like this)

"In today's rapidly evolving cybersecurity landscape, organizations 
must leverage best practices to ensure robust security postures..."
```

## The Verification Section

The `## Verification` section defines automated quality checks. The agent loop runs these after each iteration and feeds failures back for revision.

```markdown
## Verification
1. Output is 150-300 words
2. No banned phrases from style guide
3. Output must be valid JSON
4. Output must contain 'security'
```

### Supported Check Types

| Check | Example | What It Does |
|-------|---------|-------------|
| Word count | `Output is 150-300 words` | Counts words, checks range |
| Banned phrases | `No banned phrases from style guide` | Checks against built-in banned list |
| JSON validity | `Output must be valid JSON` | Tries to parse as JSON |
| Content containment | `Output must contain 'security'` | Case-insensitive substring check |

When verification fails, the agent gets another iteration with the failure details:

```
Your output failed these checks:
- Output is 150-300 words (actual: 312 words)
- No banned phrases from style guide (found: leverage, robust)

Please revise your output to address all verification failures.
```

This self-correction loop is powerful — the model often fixes issues on the second try.

## Temperature Guidelines

| Task | Temperature | Why |
|------|------------|-----|
| Extraction, classification, analysis | `0.2-0.3` | Deterministic, precise output |
| General writing, drafting | `0.7` | Creative but controlled |
| Brainstorming, ideation | `0.9-1.0` | More variety and surprise |
| JSON output | `0.2-0.3` | Reduces format errors |
| Verification / checking | `0.1-0.2` | You want consistent judgment |

## Choosing a Model

Match model size to task complexity:

| Task | Recommended | Why |
|------|-------------|-----|
| Classification, routing, yes/no | `qwen2.5:0.5b` | Fast, simple decisions |
| Structured extraction | `qwen2.5:7b` | Good at following templates |
| Code analysis | `qwen2.5:7b` or `qwen2.5-coder:32b` | Depends on depth needed |
| Prose generation with voice | `qwen3.6:27b` or `qwen3:30b-a3b` | Needs nuance |
| Complex reasoning | `anthropic/claude-sonnet-4-6` | Frontier model via OpenRouter |

See [Models Reference](../reference/models.md) for the full inventory.

## Skills as Reusable Artifacts

Skills can be:

- **Pipeline-specific**: stored in `pipeline-name/skills/`, used by one pipeline
- **Global**: stored in `~/.huginn/skills/`, available to any pipeline

```bash
# List global skills
huginn skills
```

The skill is the intellectual property. The model is a commodity. A well-written skill encodes weeks of prompt engineering, domain expertise, and quality standards into something any model can execute.

## Next Steps

- [Creating Pipelines](creating-pipelines.md) — wire skills into a pipeline
- [Skill Format Reference](../reference/skill-format.md) — complete field reference
- [Tutorial: Your First Pipeline](../tutorials/first-pipeline.md) — build one from scratch
