# Setting Up a Local LLM Server

This guide walks you through setting up a dedicated LLM server on commodity hardware — a machine that runs 24/7, serves models via API, and acts as the always-on backend for your Huginn pipelines.

## What You're Building

A Docker-based stack that provides:

- **Ollama** — model server with OpenAI-compatible API
- **Open WebUI** — browser-based chat interface (optional)
- **Caddy** — reverse proxy for clean URLs (optional)
- **Watchtower** — automatic container updates (optional)

Any device on your LAN can call the API. Huginn pipelines run against it by pointing a backend at the server's IP.

## Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | Any modern x86_64 | Intel i3+ or equivalent |
| RAM | 16GB | 32GB+ |
| Storage | 20GB free | 50GB+ (models are 400MB-40GB each) |
| OS | Debian/Ubuntu, any Linux | Debian 12+ |
| Network | LAN connectivity | Static IP or reserved DHCP lease |

!!! tip "CPU vs GPU"
    You don't need a GPU. CPU inference is slower but works fine for pipeline batch jobs that run overnight. A 7B model runs at 5-8 tokens/sec on CPU — plenty for autonomous pipelines where latency doesn't matter.

!!! tip "Mac as a Server"
    Apple Silicon Macs make excellent LLM servers thanks to unified memory bandwidth. A Mac Mini with 32GB+ can run 27B models at 15-25 tok/s. Install Ollama natively (not Docker) for best performance: `brew install ollama && ollama serve`.

## Step 1: Install Docker

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y ca-certificates curl gnupg git ufw

# Add Docker's official repository
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo "deb [arch=$(dpkg --print-architecture) \
  signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/debian \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

# Run Docker without sudo
sudo usermod -aG docker $USER
```

!!! warning
    Log out and back in after `usermod` for the group change to take effect.

Verify:

```bash
docker run --rm hello-world
```

## Step 2: Create Project Structure

```bash
mkdir -p ~/llm-stack/{ollama-data,openwebui-data,caddy-data,caddy-config}
cd ~/llm-stack
```

## Step 3: Docker Compose

Create `~/llm-stack/docker-compose.yml`:

```yaml
services:
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    restart: unless-stopped
    ports:
      - "11434:11434"
    volumes:
      - ./ollama-data:/root/.ollama
    environment:
      - OLLAMA_HOST=0.0.0.0        # Listen on all interfaces
      - OLLAMA_KEEP_ALIVE=30m      # Keep models loaded 30min after last request
      - OLLAMA_NUM_PARALLEL=2      # Max concurrent requests
      - OLLAMA_MAX_LOADED_MODELS=2 # Max models in memory simultaneously
      - OLLAMA_FLASH_ATTENTION=1   # Faster inference where supported
    deploy:
      resources:
        limits:
          cpus: '3.5'
          memory: 24G              # Adjust based on your RAM

  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: open-webui
    restart: unless-stopped
    ports:
      - "3000:8080"
    volumes:
      - ./openwebui-data:/app/backend/data
    environment:
      - OLLAMA_BASE_URL=http://ollama:11434
      - WEBUI_AUTH=true
    depends_on:
      - ollama

  caddy:
    image: caddy:2-alpine
    container_name: caddy
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - ./caddy-data:/data
      - ./caddy-config:/config
    depends_on:
      - ollama
      - open-webui

  watchtower:
    image: containrrr/watchtower
    container_name: watchtower
    restart: unless-stopped
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      - WATCHTOWER_SCHEDULE=0 0 4 * * *   # Update at 4am daily
      - WATCHTOWER_CLEANUP=true
```

### Tuning Resource Limits

Adjust `cpus` and `memory` based on your hardware:

| Server RAM | `memory` limit | Models you can run |
|-----------|----------------|-------------------|
| 16GB | 12G | One 7B model at a time |
| 32GB | 24G | Two 7B models, or one 13B |
| 64GB | 48G | Multiple models, or one 30B+ |

## Step 4: Caddyfile (Optional)

Create `~/llm-stack/Caddyfile`, replacing the IP with your server's LAN address:

```
http://YOUR_SERVER_IP {
    reverse_proxy open-webui:8080
}
```

!!! tip
    If you set up mDNS/Avahi, you can use a hostname like `http://myserver.local` instead of a raw IP.

## Step 5: Launch

```bash
cd ~/llm-stack
docker compose up -d

# Watch startup logs
docker compose logs -f
# Ctrl+C when satisfied (containers keep running)

# Verify
docker compose ps
```

## Step 6: Pull Models

```bash
# Fast general purpose — interactive chat, quick tasks
docker exec -it ollama ollama pull llama3.2:3b

# Workhorse — pipeline analysis, extraction, reasoning
docker exec -it ollama ollama pull qwen2.5:7b

# Tiny specialist — classification, routing, yes/no decisions
docker exec -it ollama ollama pull qwen2.5:0.5b

# Embeddings — semantic search, dedup, RAG
docker exec -it ollama ollama pull nomic-embed-text

# Verify
docker exec -it ollama ollama list
```

### Expected Performance (CPU-Only)

| Model | RAM Used | Speed (approx) | Best For |
|-------|----------|----------------|----------|
| qwen2.5:0.5b | ~400MB | 20-30 tok/s | Classification, routing |
| llama3.2:3b | ~2GB | 10-15 tok/s | Interactive chat, quick answers |
| qwen2.5:7b | ~4.5GB | 5-8 tok/s | Analysis, extraction, pipelines |
| nomic-embed-text | ~275MB | Fast | Embeddings |
| 13B models | ~8GB | 2-4 tok/s | Overnight batch only |

## Step 7: Test the API

### From any LAN device

```bash
curl http://YOUR_SERVER_IP:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3.2:3b",
    "messages": [{"role": "user", "content": "Say hello in 3 languages"}]
  }'
```

### Python (OpenAI library)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://YOUR_SERVER_IP:11434/v1",
    api_key="ollama"  # required by the library, not actually checked
)

response = client.chat.completions.create(
    model="qwen2.5:7b",
    messages=[{"role": "user", "content": "Hello"}]
)
print(response.choices[0].message.content)
```

### Web UI

Open `http://YOUR_SERVER_IP` (port 80, proxied by Caddy) or `http://YOUR_SERVER_IP:3000` (direct). The first user to sign up becomes admin.

## Step 8: Firewall

Lock down to LAN access only:

```bash
sudo ufw allow from 192.168.0.0/16 to any port 11434  # Ollama API
sudo ufw allow from 192.168.0.0/16 to any port 3000    # Open WebUI
sudo ufw allow from 192.168.0.0/16 to any port 80      # Caddy
sudo ufw allow ssh
sudo ufw enable
```

## Step 9: Auto-Start on Boot

```bash
sudo systemctl enable docker
```

Docker's `restart: unless-stopped` handles container restarts. Reboot to verify:

```bash
sudo reboot
# After reboot, SSH back in:
docker compose -f ~/llm-stack/docker-compose.yml ps
```

## Connect Huginn

Add your server as a backend in `~/.huginn/config.yaml`:

```yaml
backends:
  my-server:
    type: ollama
    url: http://YOUR_SERVER_IP:11434

  mac:
    type: ollama
    url: http://localhost:11434

default_backend: my-server
```

Now Huginn routes to your server by default:

```bash
huginn run my-pipeline --input file.md               # uses my-server
huginn run my-pipeline --input file.md --backend mac  # override to local Mac
```

## Operations Reference

### Model Management

```bash
# See what models are loaded in memory
docker exec -it ollama ollama ps

# Pull a new model
docker exec -it ollama ollama pull <model-name>

# Remove a model
docker exec -it ollama ollama rm <model-name>

# Interactive terminal chat
docker exec -it ollama ollama run llama3.2:3b

# List all downloaded models
docker exec -it ollama ollama list
```

### Stack Management

```bash
# View logs
docker compose -f ~/llm-stack/docker-compose.yml logs -f ollama

# Restart a single service
docker compose -f ~/llm-stack/docker-compose.yml restart ollama

# Update all containers manually
docker compose -f ~/llm-stack/docker-compose.yml pull
docker compose -f ~/llm-stack/docker-compose.yml up -d

# Backup models
tar czf ~/llm-stack-backup-$(date +%Y%m%d).tar.gz ~/llm-stack/ollama-data
```

### SSH Config (on your workstation)

Add to `~/.ssh/config` for quick access:

```
Host llm-server
    HostName YOUR_SERVER_IP
    User your-username
```

Then: `ssh llm-server`

## Multi-Machine Architecture

Once your server is running, you can build a multi-backend setup where different machines handle different workloads:

```
┌─────────────────────┐     ┌──────────────────────┐
│  Workstation (Mac)  │     │  Server (always-on)  │
│  Ollama (native)    │     │  Ollama (Docker)     │
│  Large models 27B+  │     │  Small models 0.5-8B │
│  Quality-critical   │     │  24/7 pipeline work  │
│  localhost:11434    │     │  LAN:11434           │
└─────────────────────┘     └──────────────────────┘
```

Route pipeline stages by task:

```yaml
stages:
  # Cheap, fast tasks → always-on server
  - name: classify
    backend: my-server
    model: qwen2.5:0.5b

  # Quality-critical prose → big local model
  - name: draft
    backend: mac
    model: qwen3.6:27b
```

See [Using Backends](backends.md) for full routing details.

## Model Selection Guide

| Task | Recommended Model | Notes |
|------|-------------------|-------|
| Classification, routing, yes/no | qwen2.5:0.5b | Fastest, handles simple decisions well |
| Structured extraction | qwen2.5:7b or qwen3:8b | Good accuracy on structured output |
| Prose generation | qwen3.6:27b+ | Quality drops sharply below 27B |
| Code analysis | qwen2.5:7b on server, qwen2.5-coder:32b on Mac | Coder variant for deep review |
| Embeddings | nomic-embed-text | Fast on any hardware |
| Verification/checking | qwen2.5:0.5b-7b | Evaluating is easier than generating |

!!! tip "Benchmark, Don't Guess"
    Run 20 real inputs through candidate models and compare output quality. A 0.5b model often handles classification as well as a 7b — use the smaller one and save RAM for stages that need it.

## Troubleshooting

### Model won't load (OOM)

The model is larger than available RAM. Check with `docker exec -it ollama ollama ps` — if another model is loaded, it may need to unload first. Reduce `OLLAMA_MAX_LOADED_MODELS` to 1, or use a smaller model.

### API returns connection refused

1. Check the container is running: `docker compose ps`
2. Check Ollama is listening on all interfaces: `OLLAMA_HOST=0.0.0.0` must be set
3. Check firewall: `sudo ufw status`
4. Check the port from another device: `curl http://YOUR_SERVER_IP:11434/api/tags`

### Slow inference

CPU inference is inherently slower than GPU. For batch pipeline work, this is fine — queue jobs overnight. For interactive use, consider a Mac with Apple Silicon (unified memory makes large models fast).

### Container keeps restarting

Check logs: `docker compose logs ollama`. Common cause is insufficient memory — the container gets OOM-killed and Docker restarts it in a loop. Reduce the `memory` limit in docker-compose.yml or use smaller models.
