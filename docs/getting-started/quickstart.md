# Quick Start

This guide walks you through running your first pipeline in under 5 minutes.

## 1. Deploy the Starter Pipeline

Huginn ships with a `post-generator` pipeline. Copy it to your Huginn home:

```bash
cp -r huginn/pipelines/post-generator ~/.huginn/pipelines/
```

Verify it's visible:

```bash
huginn pipelines
```

You should see:

```
┌──────────────────────────────────────────────────────────┐
│ Available Pipelines                                      │
├──────────────────────┬────────┬───────────────────────────┤
│ Name                 │ Stages │ Description               │
├──────────────────────┼────────┼───────────────────────────┤
│ post-generator       │   4    │ Generate LinkedIn posts   │
│                      │        │ in Ken's voice from       │
│                      │        │ source material           │
└──────────────────────┴────────┴───────────────────────────┘
```

## 2. Create Input

Create a file with some source material:

```bash
cat > ~/my-notes.md << 'EOF'
We just finished a security assessment for a mid-market SaaS company. 
They had 47 findings across their AWS infrastructure. The biggest issue 
wasn't a technical vulnerability — it was that three different teams had 
deployed services with admin-level IAM roles because "it was faster." 
Nobody had reviewed the permissions in 18 months. The fix took two weeks 
of painstaking role reduction, but the real fix was setting up automated 
IAM policy reviews that run weekly.
EOF
```

## 3. Run the Pipeline

```bash
huginn run post-generator --input ~/my-notes.md
```

You'll see progress as each stage executes:

```
Task a3f7b2c1 — running pipeline 'post-generator' (4 stages)
  Stage 1/4 'analyze' (qwen2.5:7b on i3)...
    ✓ 12.3s, 1 iterations, 847 tokens
  Stage 2/4 'draft' (qwen2.5:7b on i3)...
    ✓ 18.7s, 1 iterations, 1243 tokens
  Stage 3/4 'slop-filter' (qwen2.5:7b on i3)...
    ✓ 8.2s, 1 iterations, 632 tokens
  Stage 4/4 'revise' (qwen2.5:7b on i3)...
    ✓ 15.1s, 2 iterations, 1891 tokens
  ✓ Pipeline complete in 54.3s — output at ~/.huginn/tasks/a3f7b2c1/output
```

## 4. Check the Output

```bash
huginn status a3f7b2c1
```

Shows a detailed breakdown of each stage with timing, token usage, and verification status. The final output is in the task's output directory.

## 5. Run in Background

For longer pipelines, use `--bg` to run detached:

```bash
huginn run post-generator --input ~/my-notes.md --bg
```

```
Task b7c2d4e8 launched in background (PID 42891)
  Logs: ~/.huginn/tasks/b7c2d4e8/run.log
  Check status: huginn status b7c2d4e8
  View logs:    huginn logs b7c2d4e8
```

The task runs independently. Close your terminal, and it keeps going. Check back later:

```bash
huginn tasks                    # List all recent tasks
huginn status b7c2d4e8          # Detailed status
huginn logs b7c2d4e8 --follow   # Stream logs in real-time
```

## What Just Happened?

The pipeline ran 4 stages in sequence:

1. **analyze** — extracted themes, audience, and angle from your notes (JSON output)
2. **draft** — wrote a LinkedIn post using the analysis (reading reference style guide)
3. **slop-filter** — scanned the draft for AI writing patterns and scored it
4. **revise** — rewrote the draft incorporating the slop report feedback

Each stage used the same `qwen2.5:7b` model but with different skill prompts. The skill file is what made each stage behave differently.

## Next Steps

- [Configuration](configuration.md) — set up multiple backends and OpenRouter
- [Writing Skills](../guides/writing-skills.md) — learn the core craft
- [Creating Pipelines](../guides/creating-pipelines.md) — build your own pipeline
- [CLI Reference](../reference/cli.md) — every command documented
