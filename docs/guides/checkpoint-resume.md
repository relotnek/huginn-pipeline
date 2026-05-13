# Checkpoint & Resume

Huginn preserves progress at every stage boundary and within the agent loop. If anything goes wrong — crash, timeout, network blip, OOM — you don't lose completed work.

## How It Works

### Stage-Level Resume

Each stage writes its output to a dedicated directory. When you resume a task, the executor checks each stage's output directory:

- If the stage has output files (beyond `checkpoint.json`), it's considered complete and skipped
- If the stage has no output, it runs from scratch

```bash
$ huginn resume a3f7b2c1
Resuming task a3f7b2c1 — pipeline 'post-generator' from stage 3
  Stage 1/4 'analyze' — already complete, skipping
  Stage 2/4 'draft' — already complete, skipping
  Stage 3/4 'slop-filter' (qwen2.5:7b on i3)...
    ✓ 8.2s, 1 iterations, 632 tokens
  Stage 4/4 'revise' (qwen2.5:7b on i3)...
    ✓ 15.1s, 2 iterations, 1891 tokens
```

### Agent-Level Checkpoint

Within each stage, the agent loop saves a checkpoint after every iteration:

```json
{
  "iterations": 2,
  "total_tokens": 1243,
  "history": [
    {
      "iteration": 1,
      "tokens": 847,
      "seconds": 12.3,
      "output_preview": "First 200 chars of output..."
    }
  ],
  "saved_at": "2026-05-08T22:15:00+00:00"
}
```

On resume, the agent picks up its iteration count and token total from the checkpoint.

## Design Principle

**Never delete partial work.** On failure, preserve output and checkpoint for resume. This means:

- A 4-stage pipeline that fails at stage 3 keeps stages 1-2 output intact
- A stage that times out mid-generation keeps whatever output it had
- A verification failure preserves the failed output for debugging

## Switching Backends on Resume

You can resume a task on a different backend:

```bash
# Originally ran on i3, backend went down — resume on mac
huginn resume a3f7b2c1 --backend mac
```

This is useful when:

- A backend goes unreachable (server rebooted, network issue)
- You want to use a faster backend for remaining stages
- You want to switch from local to cloud (or vice versa)

## Inspecting State

Check what a task has completed:

```bash
huginn status a3f7b2c1
```

Look at per-stage output:

```bash
ls ~/.huginn/tasks/a3f7b2c1/stages/
```

Each stage directory contains `input/` and `output/` with the actual files the agent read and produced.
