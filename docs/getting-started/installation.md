# Installation

## Prerequisites

- **Python 3.11+**
- At least one inference backend:
    - [Ollama](https://ollama.ai) running locally or on a server, **or**
    - An [OpenRouter](https://openrouter.ai) API key, **or**
    - Any OpenAI-compatible endpoint (vLLM, TGI, etc.)

## Install Huginn

```bash
git clone https://github.com/asgarddev/huginn.git
cd huginn/huginn
pip install -e .
```

Verify the installation:

```bash
huginn --help
```

You should see:

```
Usage: huginn [OPTIONS] COMMAND [ARGS]...

  Huginn — Send out the ravens. They come back with results.

Options:
  --version  Show the version and exit.
  --help     Show this message and exit.

Commands:
  logs       Show logs for a background task.
  pipelines  List available pipelines.
  resume     Resume an interrupted task from the last completed stage.
  run        Run a pipeline on an input file.
  skills     List available global skills.
  status     Show the status of a task.
  stop       Stop a running task.
  tasks      List recent tasks.
```

## First Run

On first run, Huginn creates its home directory at `~/.huginn/` with the following structure:

```
~/.huginn/
├── config.yaml            # Backend configuration (auto-generated)
├── huginn.db              # SQLite database for task tracking
├── skills/                # Global reusable skill library
├── pipelines/             # Pipeline definitions
└── tasks/                 # Per-task execution directories
```

## Install a Backend

You need at least one backend for model inference.

### Option A: Ollama (Local, Free)

Install Ollama and pull a model:

```bash
# Install Ollama (macOS)
brew install ollama

# Start the server
ollama serve

# Pull a model
ollama pull qwen2.5:7b
```

### Option B: OpenRouter (Cloud, Pay-per-token)

Sign up at [openrouter.ai](https://openrouter.ai) and set your API key:

```bash
export OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

Add to your shell profile (`~/.zshrc` or `~/.bashrc`) to persist across sessions.

### Option C: Any OpenAI-Compatible Endpoint

If you run vLLM, TGI, or another OpenAI-compatible server, you can point Huginn at it. See [Configuration](configuration.md) for details.

## Next Steps

- [Quick Start](quickstart.md) — run your first pipeline
- [Configuration](configuration.md) — set up multiple backends
