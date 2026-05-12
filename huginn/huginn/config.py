"""Configuration management for Huginn."""

import os
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG = {
    "backends": {
        "i3": {"type": "ollama", "url": "http://192.168.2.135:11434"},
        "mac": {"type": "ollama", "url": "http://localhost:11434"},
    },
    "default_backend": "i3",
    "max_parallel_workers": 2,
    "task_timeout_minutes": 480,
    "default_resource_limits": {
        "cpus": "2.0",
        "memory": "8g",
    },
}


def get_huginn_home() -> Path:
    """Return the Huginn home directory, creating it if needed."""
    home = Path(os.environ.get("HUGINN_HOME", Path.home() / ".huginn"))
    home.mkdir(parents=True, exist_ok=True)
    (home / "skills").mkdir(exist_ok=True)
    (home / "pipelines").mkdir(exist_ok=True)
    (home / "tasks").mkdir(exist_ok=True)
    return home


def get_config_path() -> Path:
    """Return path to config file."""
    return get_huginn_home() / "config.yaml"


def load_config() -> dict[str, Any]:
    """Load config from ~/.huginn/config.yaml, creating with defaults if missing."""
    config_path = get_config_path()

    if not config_path.exists():
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)

    with open(config_path) as f:
        config = yaml.safe_load(f) or {}

    # Merge with defaults for any missing keys
    merged = dict(DEFAULT_CONFIG)
    merged.update(config)
    return merged


def save_config(config: dict[str, Any]) -> None:
    """Write config to disk."""
    config_path = get_config_path()
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def get_backend_url(config: dict[str, Any], backend_name: str | None = None) -> str:
    """Resolve a backend name to its URL. Kept for backwards compatibility."""
    return get_backend_config(config, backend_name)["url"]


def get_backend_config(config: dict[str, Any], backend_name: str | None = None) -> dict[str, Any]:
    """Resolve a backend name to its full config dict.

    Returns dict with at minimum: type, url. May also include api_key_env,
    extra_headers, and other backend-specific settings.

    Backend types:
      - ollama: Local Ollama instance (default, api_key ignored)
      - openrouter: OpenRouter API (requires api_key_env)
      - openai_compatible: Any OpenAI-compatible endpoint
    """
    name = backend_name or config["default_backend"]
    backends = config.get("backends", {})

    if name not in backends:
        available = ", ".join(backends.keys())
        raise ValueError(f"Backend '{name}' not found. Available: {available}")

    backend = dict(backends[name])
    backend.setdefault("type", "ollama")
    backend["name"] = name
    return backend
