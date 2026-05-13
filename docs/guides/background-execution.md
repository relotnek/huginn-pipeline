# Background Execution

Run pipelines in the background and check back when they're done. Pipelines survive terminal close, laptop sleep (for server-backed inference), and network interruptions.

## Launching Background Tasks

Add `--bg` to any run command:

```bash
huginn run post-generator --input ./notes.md --bg
```

Output:
```
Task a3f7b2c1 launched in background (PID 42891)
  Logs: ~/.huginn/tasks/a3f7b2c1/run.log
  Check status: huginn status a3f7b2c1
  View logs:    huginn logs a3f7b2c1
```

The task runs in a fully detached process. Close your terminal, and it keeps going.

## Monitoring Tasks

### Check Status

```bash
huginn status a3f7b2c1
```

Shows pipeline name, backend, progress through stages, timing, token usage, and verification results.

### Stream Logs

```bash
huginn logs a3f7b2c1 --follow
```

Like `tail -f` — streams log output in real-time. Use `--lines 100` to control how many lines to show.

### List All Tasks

```bash
huginn tasks
huginn tasks --status running
huginn tasks --status failed --limit 5
```

## Stopping Tasks

```bash
huginn stop a3f7b2c1
```

Sends SIGTERM to the background process, marks the task as cancelled, and preserves all partial output. Completed stages are not lost.

## Resuming Tasks

If a task was interrupted (process died), stopped, or failed mid-pipeline:

```bash
huginn resume a3f7b2c1
```

Resume skips already-completed stages and picks up from where it left off. You can also switch backends on resume:

```bash
huginn resume a3f7b2c1 --backend mac
```

### Resumable Statuses

| Status | Can Resume? | What Happened |
|--------|------------|---------------|
| `interrupted` | Yes | Process died (crash, reboot, OOM) |
| `cancelled` | Yes | Stopped by `huginn stop` |
| `failed` | Yes | Stage error (model unreachable, verification exhausted) |
| `running` | No | Still in progress |
| `complete` | No | Already done |

## Task Lifecycle

```
queued → running → complete
                 → failed     → (resume) → running → ...
                 → cancelled  → (resume) → running → ...
                 → interrupted → (resume) → running → ...
```

## Where Output Lives

```
~/.huginn/tasks/a3f7b2c1/
├── input/                  # Copy of original input
├── output/                 # Final pipeline output
├── stages/
│   ├── 00-analyze/
│   │   ├── input/          # Stage input (wired from prior stage)
│   │   └── output/         # Stage output + checkpoint.json
│   ├── 01-draft/
│   │   ├── input/
│   │   └── output/
│   └── ...
├── run.log                 # Stdout/stderr from background process
├── pid                     # PID file for process tracking
└── meta.json               # Task metadata and timing
```

## Next Steps

- [Checkpoint & Resume](checkpoint-resume.md) — how checkpointing works under the hood
- [CLI Reference](../reference/cli.md) — all commands and flags
