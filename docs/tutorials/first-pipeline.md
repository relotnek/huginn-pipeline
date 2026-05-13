# Tutorial: Your First Pipeline

Build a pipeline from scratch that takes raw meeting notes and produces a structured action-item summary. By the end, you'll understand skills, manifests, input wiring, verification, and running.

## What We're Building

A 2-stage pipeline:

```
meeting-notes.md → [Extract Actions] → actions.json → [Format Summary] → summary.md
```

1. **extract** — Read raw notes, produce structured JSON with action items
2. **summarize** — Read the JSON, produce a clean markdown summary

## Step 1: Create the Pipeline Directory

```bash
mkdir -p ~/.huginn/pipelines/meeting-actions/skills
mkdir -p ~/.huginn/pipelines/meeting-actions/files
```

## Step 2: Write the Extract Skill

Create `~/.huginn/pipelines/meeting-actions/skills/01-extract.md`:

```markdown
---
name: action-extractor
model: qwen2.5:7b
temperature: 0.2
max_iterations: 3
tools: [file_read]
---

# Action Item Extractor

Read the meeting notes and extract every action item, decision, and deadline.

Output ONLY a JSON object with this structure:

{
  "meeting_topic": "Brief description of what the meeting was about",
  "date": "Date if mentioned, otherwise 'unknown'",
  "action_items": [
    {
      "owner": "Person responsible (or 'unassigned')",
      "action": "What needs to be done",
      "deadline": "When it's due (or 'no deadline')",
      "priority": "high | medium | low"
    }
  ],
  "decisions": [
    "Decision that was made"
  ],
  "open_questions": [
    "Question that wasn't resolved"
  ]
}

Rules:
- Extract EVERY action item, even implicit ones ("I'll look into that" = action item)
- If no owner is clear, mark as "unassigned"
- Prioritize based on urgency words: "ASAP", "before Friday" = high; "when you get a chance" = low
- Decisions are final — not proposals or suggestions

## Verification
1. Output must be valid JSON
```

## Step 3: Write the Summarize Skill

Create `~/.huginn/pipelines/meeting-actions/skills/02-summarize.md`:

```markdown
---
name: action-summarizer
model: qwen2.5:7b
temperature: 0.5
max_iterations: 2
tools: [file_read, file_write]
---

# Action Item Summary Writer

Read the structured action items JSON and produce a clean, scannable markdown summary.

Format the output as follows:

# Meeting Actions: [topic]

**Date:** [date]

## Action Items

| Owner | Action | Deadline | Priority |
|-------|--------|----------|----------|
| ...   | ...    | ...      | ...      |

## Decisions Made
- Decision 1
- Decision 2

## Open Questions
- Question 1
- Question 2

Rules:
- Sort action items by priority (high first)
- Bold the owner name in the table
- If there are no open questions, omit that section entirely
- Keep it scannable — no prose, just structured information

## Verification
1. Output must contain 'Action Items'
```

## Step 4: Write the Manifest

Create `~/.huginn/pipelines/meeting-actions/manifest.yaml`:

```yaml
name: meeting-actions
description: Extract action items from meeting notes and produce a structured summary
version: "1.0"

defaults:
  backend: i3
  timeout_minutes: 30

stages:
  - name: extract
    skill: skills/01-extract.md
    model: qwen2.5:7b
    input: $pipeline_input
    output: actions.json
    tools: [file_read]
    constraints:
      network: false
      shell: false

  - name: summarize
    skill: skills/02-summarize.md
    model: qwen2.5:7b
    input: actions.json
    output: summary.md
    tools: [file_read, file_write]
    constraints:
      network: false
      shell: false

on_complete:
  output_file: summary.md
```

## Step 5: Create Test Input

Create a test file `~/test-meeting.md`:

```markdown
# Product Standup - May 8

Attendees: Sarah, Mike, Chen, Pat

Sarah: The API migration is almost done. I need to finish the auth
endpoints by Friday. Mike, can you review the PR when it's up?

Mike: Sure, I'll review it Thursday. Also, we decided to go with 
PostgreSQL over DynamoDB for the new service. Chen was right about 
the query patterns.

Chen: Thanks. I'll update the architecture doc to reflect that. 
Should have it done by end of week. Oh, and are we still doing the 
security review before launch? Nobody's scheduled it.

Pat: I'll talk to the security team today and get that on the calendar. 
We need it done before the 15th. Also, the monitoring dashboard ASAP — 
we keep getting paged for things we should see coming.

Sarah: Agreed. Mike, can you set up the Grafana board? You did the 
last one and it was solid.

Mike: When I get a chance, sure. Not this week though.
```

## Step 6: Verify and Run

Check that the pipeline is visible:

```bash
huginn pipelines
```

Run it:

```bash
huginn run meeting-actions --input ~/test-meeting.md
```

Check the output:

```bash
huginn status <task-id>
```

The final output at `~/.huginn/tasks/<task-id>/output/summary.md` should contain a structured summary with action items sorted by priority, the PostgreSQL decision, and the unresolved security review question.

## Step 7: Iterate on the Skills

If the output isn't right:

1. Check the intermediate JSON at `~/.huginn/tasks/<task-id>/stages/00-extract/output/`
2. Refine the extract skill's prompt (more specific instructions, better examples)
3. Re-run — Huginn creates a new task each time

The skill file is where you invest your time. The model is just executing your instructions.

## What You Learned

- Pipeline folder structure (manifest + skills + files)
- Skill format (YAML frontmatter + markdown prompt + verification)
- Input wiring (`$pipeline_input` and stage-to-stage)
- Verification rules (JSON validity, content checks)
- Running and inspecting output

## Next Steps

- [Writing Skills](../guides/writing-skills.md) — deeper dive into effective prompts
- [Tutorial: Multi-Backend Routing](multi-backend.md) — route stages across backends
- [Manifest Schema](../reference/manifest-schema.md) — complete field reference
