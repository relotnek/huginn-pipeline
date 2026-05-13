# Brain & Hands Separation

The most important architectural decision in Huginn: **model inference and tool execution are completely decoupled.**

## The Model (Brain)

The brain is stateless inference. You send a prompt, you get text back. It has no access to your filesystem, no ability to run commands, no memory between calls.

The brain can be:

- Ollama on your laptop
- Ollama on a server across your network
- Claude via OpenRouter
- Any OpenAI-compatible endpoint

All it does is generate text. It doesn't know where it's running, what files you have, or what tools are available. It can only **request** tool calls — it cannot execute them.

## The Tool Runtime (Hands)

The hands execute tools. When the model generates a tool call (via the OpenAI function-calling protocol), Huginn intercepts it, validates the arguments, executes the tool locally, and sends the result back to the model.

The hands always run where Huginn runs — on your local machine. This means:

- `file_read` reads files from your filesystem
- `file_write` writes files to your filesystem
- Future tools (`web_search`, `shell`) will execute on your machine

## Why This Matters

### Data Sovereignty

When using OpenRouter, your prompts travel to the cloud, but your files don't. The model sees the content of files (via tool results sent in the conversation), but the files themselves never leave your machine. The model generates tool calls like "read file X" — Huginn reads the file locally and sends the content as a tool result.

### Flexible Deployment

Because brain and hands are independent, you can deploy them separately:

```
Scenario 1: Everything local
  Hands: laptop  →  Brain: laptop (Ollama)

Scenario 2: Local tools, remote inference
  Hands: laptop  →  Brain: server with GPU (Ollama)

Scenario 3: Local tools, cloud inference
  Hands: laptop  →  Brain: OpenRouter (Claude, GPT)

Scenario 4: Cloud tools, local inference (planned)
  Hands: cloud VM →  Brain: local GPU
```

### Cost Optimization

Route cheap tasks to free local models. Route quality-critical tasks to paid cloud models. Tools always run for free on your hardware.

```yaml
stages:
  - name: classify        # Free: local model, local tools
    backend: i3
    model: qwen2.5:0.5b

  - name: write-report    # Paid inference, free tools
    backend: openrouter
    model: anthropic/claude-sonnet-4-6
```

## Security Implications

The brain/hands split has a deliberate security boundary:

- The **brain** can only generate text and request tool calls. It cannot execute anything.
- The **hands** validate every tool call before execution:
    - Path traversal (`../../`) is rejected
    - Absolute paths are rejected
    - Reads are restricted to declared input and reference directories
    - Writes are restricted to the stage's output directory

A compromised or hallucinating model can request malicious tool calls, but Huginn's validation layer prevents them from executing.

## How Tool Calls Flow

```
1. Huginn sends [system prompt + user message + tool definitions] to model
2. Model responds: "I'll read the input file"
   → tool_call: file_read(path="input.md")
3. Huginn validates: is "input.md" in the allowed input directory? ✓
4. Huginn executes: reads the file locally
5. Huginn sends tool result back to model
6. Model processes the file contents and responds:
   → tool_call: file_write(path="output.json", content="{...}")
7. Huginn validates: is "output.json" in the output directory? ✓
8. Huginn executes: writes the file locally
9. Huginn sends confirmation back to model
10. Model responds with final text (no more tool calls)
```

The model never touches your filesystem directly. Every access goes through Huginn's validation layer.
