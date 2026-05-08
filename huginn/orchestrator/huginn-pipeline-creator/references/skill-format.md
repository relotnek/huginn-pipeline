# Huginn Skill File Format

Skills are markdown files with YAML frontmatter that define a single sub-agent's behavior. The pipeline creator doesn't write skills — it consumes them. But it needs to understand the format to validate them and wire them correctly.

## Required Format

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

[System prompt — this is what the model receives as instructions]

## Input
[Description of what the skill expects to read from input/]

## Output
[Description of what the skill writes to output/]

## Verification
1. First check
2. Second check
3. Third check
```

## Required Frontmatter Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| name | string | Yes | Unique identifier |
| model | string | Yes | Ollama model name |

## Optional Frontmatter Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| backend | string | null (uses pipeline default) | Ollama backend name |
| temperature | float | 0.7 | Model temperature |
| max_iterations | int | 10 | Max agent loop iterations |
| tools | list | [file_read] | Available tools |
| constraints.network | bool | false | Internet access |
| constraints.shell | bool | false | Shell command access |
| constraints.timeout_minutes | int | 60 | Stage timeout |

## Verification Section

The `## Verification` section in the skill body defines automated checks. The agent loop runs these after each iteration and feeds failures back for revision.

Supported check types:
- **Word count**: "Output is 150-300 words"
- **JSON validity**: "Output must be valid JSON"
- **Banned phrases**: "No banned phrases from style guide"
- **Content containment**: "Output must contain 'security'"

## What the Pipeline Creator Needs to Know

When incorporating a skill into a pipeline:

1. The skill's `model` field can be overridden in the manifest stage definition
2. The skill's `backend` can be overridden in the manifest
3. The skill's `verification` rules are merged with any `verification` rules in the manifest stage
4. The skill's `tools`, `constraints`, and `max_iterations` are used by the agent loop
5. The skill body (system prompt) is what actually gets sent to the model

## Validating a Skill File

Before incorporating a skill, check:
- [ ] File has YAML frontmatter between `---` markers
- [ ] `name` field is present
- [ ] `model` field is present and matches an available model
- [ ] The body contains a meaningful system prompt (not empty)
- [ ] If the skill references input files, the pipeline wiring provides them
- [ ] If the skill produces structured output (JSON), subsequent stages expect that format
