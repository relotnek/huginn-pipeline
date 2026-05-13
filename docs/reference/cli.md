# CLI Reference

All Huginn commands with their options and usage.

## huginn run

Run a pipeline on an input file.

```bash
huginn run <pipeline_name> --input <path> [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--input` | `-i` | **Required.** Input file or directory |
| `--backend` | `-b` | Override backend for all stages |
| `--bg` | | Run in background, return immediately with task ID |
| `--quiet` | `-q` | Suppress progress output |

**Examples:**

```bash
# Foreground run (blocks until complete)
huginn run post-generator --input ./notes.md

# Background run (returns immediately)
huginn run post-generator --input ./notes.md --bg

# Override backend
huginn run post-generator --input ./notes.md --backend openrouter

# Quiet mode (no stage-by-stage output)
huginn run post-generator --input ./notes.md -q
```

---

## huginn status

Show the status of a task, including stage-by-stage breakdown.

```bash
huginn status <task_id>
```

Output includes:
- Task ID, status, pipeline name, backend(s) used
- Start/finish timestamps
- Stage table with model, backend, status, timing, tokens, verification
- Output file listing with preview

**Example output:**

```
Task a3f7b2c1 — complete
  Pipeline: post-generator
  Backend:  i3
  Started:  2026-05-08T22:10:00+00:00
  Finished: 2026-05-08T22:11:02+00:00

            Stages
┌───┬──────────────┬───────────┬─────────┬──────────┬───────┬────────┬──────────┐
│ # │ Name         │ Model     │ Backend │ Status   │  Time │ Tokens │ Verified │
├───┼──────────────┼───────────┼─────────┼──────────┼───────┼────────┼──────────┤
│ 1 │ analyze      │ qwen2.5:7b│ i3      │ complete │ 12.3s │    847 │ ✓        │
│ 2 │ draft        │ qwen2.5:7b│ i3      │ complete │ 18.7s │   1243 │ -        │
│ 3 │ slop-filter  │ qwen2.5:7b│ i3      │ complete │  8.2s │    632 │ ✓        │
│ 4 │ revise       │ qwen2.5:7b│ i3      │ complete │ 15.1s │   1891 │ ✓        │
└───┴──────────────┴───────────┴─────────┴──────────┴───────┴────────┴──────────┘

Output files:
  final-post.md (1,247 bytes)
```

---

## huginn tasks

List recent tasks.

```bash
huginn tasks [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--limit` | `-n` | Number of tasks to show (default: 20) |
| `--status` | `-s` | Filter by status: `running`, `complete`, `failed`, `interrupted`, `cancelled` |
| `--mode` | `-m` | Filter by execution mode: `local` or `background` |

**Examples:**

```bash
huginn tasks
huginn tasks --status failed --limit 5
huginn tasks -s running
huginn tasks --mode background
```

---

## huginn resume

Resume an interrupted, failed, or cancelled task from the last completed stage.

```bash
huginn resume <task_id> [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--backend` | `-b` | Override backend for resumed stages |
| `--quiet` | `-q` | Suppress progress output |

Skips stages that already have output. Useful when a backend goes down or a task was stopped.

```bash
huginn resume a3f7b2c1
huginn resume a3f7b2c1 --backend mac
```

---

## huginn stop

Stop a running background task. Sends SIGTERM, preserves partial output.

```bash
huginn stop <task_id>
```

Completed stages are preserved. Resume later with `huginn resume`.

---

## huginn logs

Show logs for a background task.

```bash
huginn logs <task_id> [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--follow` | `-f` | Stream log output in real-time (like `tail -f`) |
| `--lines` | `-n` | Number of lines to show (default: 50) |

```bash
huginn logs a3f7b2c1
huginn logs a3f7b2c1 --follow
huginn logs a3f7b2c1 -n 100
```

!!! note
    Logs are only available for background tasks (`--bg`). Foreground tasks print to stdout.

---

## huginn output

View or download the output of a completed task.

```bash
huginn output <task_id> [options]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--download` | `-d` | Save output files to a local directory |

**Examples:**

```bash
# View output in terminal
huginn output a3f7b2c1

# Download output files to local directory
huginn output a3f7b2c1 --download ./results/
```

---

## huginn pipelines

List all available pipelines in `~/.huginn/pipelines/`.

```bash
huginn pipelines
```

Shows pipeline name, number of stages, and description from the manifest.

---

## huginn skills

List global skills in `~/.huginn/skills/`.

```bash
huginn skills
```

Shows skill name, assigned model, and backend.
