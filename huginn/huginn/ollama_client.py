"""Ollama client — thin wrapper around OpenAI-compatible API."""

import time
from dataclasses import dataclass

from openai import OpenAI


@dataclass
class CompletionResult:
    """Result from a model completion."""

    content: str
    tokens_used: int
    duration_seconds: float
    model: str
    success: bool
    error: str | None = None


def get_client(base_url: str) -> OpenAI:
    """Create an OpenAI client pointed at an Ollama endpoint."""
    return OpenAI(base_url=f"{base_url}/v1", api_key="ollama")


def check_model_available(client: OpenAI, model: str) -> bool:
    """Check if a model is pulled and available."""
    try:
        models = client.models.list()
        return any(m.id == model for m in models.data)
    except Exception:
        return False


def check_backend_reachable(base_url: str) -> bool:
    """Check if a backend is responding."""
    try:
        import urllib.request
        req = urllib.request.Request(f"{base_url}/v1/models", method="GET")
        urllib.request.urlopen(req, timeout=5)
        return True
    except Exception:
        return False


def complete(
    client: OpenAI,
    model: str,
    system_prompt: str,
    user_message: str,
    temperature: float = 0.7,
) -> CompletionResult:
    """Run a chat completion against an Ollama model."""
    start = time.time()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=temperature,
        )
        elapsed = time.time() - start
        content = response.choices[0].message.content or ""
        tokens = response.usage.total_tokens if response.usage else 0

        return CompletionResult(
            content=content,
            tokens_used=tokens,
            duration_seconds=round(elapsed, 2),
            model=model,
            success=True,
        )
    except Exception as e:
        elapsed = time.time() - start
        return CompletionResult(
            content="",
            tokens_used=0,
            duration_seconds=round(elapsed, 2),
            model=model,
            success=False,
            error=str(e),
        )
