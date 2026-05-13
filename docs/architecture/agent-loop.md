# Agent Loop

Every pipeline stage runs the same generic agent loop. The skill prompt is what makes each stage behave differently.

## The Loop

```
1. Load skill (system prompt, rules, verification checks)
2. Load checkpoint if resuming from interruption
3. Read input files and reference documents

Loop until done or max_iterations reached:
    OBSERVE  → Read current state (input, partial output)
    THINK    → Call model with skill prompt + state + tools
    ACT      → Execute tool calls locally, feed results back
    VERIFY   → Check output against skill's verification rules
               If checks fail, feed failure back into next iteration
    CHECKPOINT → Save progress (survive crashes)

4. Write final output and status
```

## Tool Calling Sub-Loop

When a stage declares tools (e.g., `[file_read, file_write]`), the THINK+ACT step becomes a multi-turn conversation:

```
Round 1:
  → Send prompt + input to model (with tool definitions)
  ← Model responds with tool_call: file_read("input.md")
  → Execute file_read, send result back

Round 2:
  → Send conversation (including tool result) to model
  ← Model responds with tool_call: file_write("output.json", content)
  → Execute file_write, send confirmation back

Round 3:
  → Send conversation to model
  ← Model responds with final text (no tool calls)
  → Done — use the final text as stage output
```

This loop runs up to 20 rounds per iteration. Most stages complete in 2-4 rounds.

## Verification

After each iteration, the agent checks output against verification rules from the skill and manifest:

```python
# Supported checks:
"Output must be valid JSON"          # json.loads() succeeds
"Output is 150-300 words"            # word count in range
"No banned phrases from style guide" # checks against banned list
"Output must contain 'security'"     # substring check
```

If verification fails, the agent gets another iteration with feedback:

```
Your output failed these checks:
- Output is 150-300 words (actual: 312 words)
- No banned phrases from style guide (found: leverage)

Please revise your output to address all verification failures.
```

The model typically fixes issues on the second try. After `max_iterations`, the agent stops (the last output is preserved even if verification fails).

## Checkpointing

After every iteration, the agent saves a checkpoint:

```json
{
  "iterations": 2,
  "total_tokens": 1243,
  "history": [
    {
      "iteration": 1,
      "tokens": 847,
      "seconds": 12.3,
      "output_preview": "First 200 chars..."
    }
  ],
  "saved_at": "2026-05-08T22:15:00+00:00"
}
```

On resume, the agent picks up iteration count and token totals from the checkpoint. Stage-level resume works by checking if output files exist (beyond `checkpoint.json`).

## Retry Logic

When a model call fails (network error, timeout, backend down), the agent retries up to 3 times with exponential backoff (2s, 4s, 8s). If all retries fail, the stage fails and the task can be resumed later.

## Output Writing

The agent writes output based on content type:

- If the output looks like JSON (starts with `{` or `[` and parses), it's saved as `.json`
- Otherwise, it's saved as `.md`

When a stage declares tools with `file_write`, the model can write output directly via tool calls. The agent also writes any final text content to a default output file.

## Configuration

The agent loop is configured through the skill frontmatter and manifest:

| Setting | Source | Default | Effect |
|---------|--------|---------|--------|
| `max_iterations` | Skill | 10 | How many revision cycles before stopping |
| `temperature` | Skill | 0.7 | Model randomness |
| `tools` | Skill/Manifest | `[file_read]` | What tools the agent can use |
| `timeout_minutes` | Manifest/Skill | 60 | How long before the agent is killed |
| `verification` | Skill + Manifest | `[]` | Quality checks (merged from both sources) |
