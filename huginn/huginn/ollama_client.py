"""Model inference client — supports Ollama, OpenRouter, and OpenAI-compatible backends."""

import os
import time
from dataclasses import dataclass
from typing import Any

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
    tool_calls: list[dict] | None = None


def get_client(base_url: str, backend_config: dict[str, Any] | None = None) -> OpenAI:
    """Create an OpenAI client for the given backend.

    Args:
        base_url: The backend URL (used as fallback if no backend_config).
        backend_config: Full backend config dict from get_backend_config().
            If provided, uses type/url/api_key_env to build the client.
    """
    if backend_config is None:
        # Legacy path — assume Ollama
        return OpenAI(base_url=f"{base_url}/v1", api_key="ollama")

    backend_type = backend_config.get("type", "ollama")

    if backend_type == "ollama":
        return OpenAI(
            base_url=f"{backend_config['url']}/v1",
            api_key="ollama",
        )

    elif backend_type == "openrouter":
        api_key = _resolve_api_key(backend_config)
        extra_headers = {}
        if backend_config.get("app_name"):
            extra_headers["X-Title"] = backend_config["app_name"]
        if backend_config.get("referer"):
            extra_headers["HTTP-Referer"] = backend_config["referer"]
        return OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            default_headers=extra_headers or None,
        )

    elif backend_type == "openai_compatible":
        api_key = _resolve_api_key(backend_config, default="no-key")
        return OpenAI(
            base_url=backend_config["url"],
            api_key=api_key,
        )

    else:
        raise ValueError(f"Unknown backend type: {backend_type}")


def _resolve_api_key(backend_config: dict[str, Any], default: str | None = None) -> str:
    """Read API key from environment variable named in api_key_env."""
    env_var = backend_config.get("api_key_env")
    if not env_var:
        if default is not None:
            return default
        raise ValueError(
            f"Backend '{backend_config.get('name', '?')}' requires 'api_key_env' "
            f"pointing to an environment variable with the API key"
        )

    api_key = os.environ.get(env_var)
    if not api_key:
        raise ValueError(
            f"Environment variable '{env_var}' is not set. "
            f"Set it with: export {env_var}=your-api-key"
        )
    return api_key


def check_model_available(client: OpenAI, model: str, backend_config: dict[str, Any] | None = None) -> bool:
    """Check if a model is available on the backend.

    For Ollama, checks if the model is pulled locally.
    For OpenRouter, checks the model catalog.
    """
    try:
        models = client.models.list()
        # OpenRouter model IDs use provider/ prefix (e.g., "anthropic/claude-sonnet-4.6")
        # Ollama model IDs are plain (e.g., "qwen2.5:7b")
        return any(m.id == model for m in models.data)
    except Exception:
        # OpenRouter/remote APIs may not support model listing or may rate-limit it.
        # For paid APIs, assume the model is available and let the completion fail
        # with a clear error if not.
        backend_type = (backend_config or {}).get("type", "ollama")
        if backend_type in ("openrouter", "openai_compatible"):
            return True
        return False


def check_backend_reachable(base_url: str, backend_config: dict[str, Any] | None = None) -> bool:
    """Check if a backend is responding."""
    backend_type = (backend_config or {}).get("type", "ollama")

    if backend_type == "openrouter":
        check_url = "https://openrouter.ai/api/v1/models"
    else:
        check_url = f"{base_url}/v1/models"

    try:
        import urllib.request
        req = urllib.request.Request(check_url, method="GET")

        # OpenRouter needs auth even for model listing
        if backend_type == "openrouter":
            try:
                api_key = _resolve_api_key(backend_config or {})
                req.add_header("Authorization", f"Bearer {api_key}")
            except ValueError:
                # Can't check without key — assume reachable, will fail at completion
                return True

        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception:
        return False


def complete(
    client: OpenAI,
    model: str,
    system_prompt: str,
    user_message: str,
    temperature: float = 0.7,
    tools: list[dict] | None = None,
    messages: list[dict] | None = None,
) -> CompletionResult:
    """Run a chat completion against any OpenAI-compatible backend.

    When messages is provided, it is used directly (for multi-turn tool
    conversations). Otherwise, system_prompt and user_message are used
    to build a two-message conversation.

    When tools is provided, it is passed to the API for function calling.
    """
    start = time.time()
    try:
        if messages is None:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools

        response = client.chat.completions.create(**kwargs)
        elapsed = time.time() - start

        msg = response.choices[0].message
        content = msg.content or ""
        tokens = response.usage.total_tokens if response.usage else 0

        # Extract tool calls if present
        serialized_tool_calls = None
        if msg.tool_calls:
            serialized_tool_calls = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]

        return CompletionResult(
            content=content,
            tokens_used=tokens,
            duration_seconds=round(elapsed, 2),
            model=model,
            success=True,
            tool_calls=serialized_tool_calls,
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
