"""Unit tests for huginn.config — loading, backend resolution, model mapping."""

import os
from pathlib import Path

import pytest
import yaml

from huginn.config import (
    DEFAULT_CONFIG,
    get_backend_config,
    get_backend_url,
    get_huginn_home,
    load_config,
    resolve_model_name,
    save_config,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def huginn_home(tmp_path, monkeypatch):
    """Redirect HUGINN_HOME to a temp directory so tests never touch ~/.huginn."""
    home = tmp_path / "huginn_home"
    monkeypatch.setenv("HUGINN_HOME", str(home))
    return home


# ---------------------------------------------------------------------------
# get_huginn_home
# ---------------------------------------------------------------------------


class TestGetHuginnHome:
    def test_creates_directory(self, huginn_home):
        result = get_huginn_home()
        assert result.exists()
        assert result.is_dir()

    def test_creates_subdirectories(self, huginn_home):
        result = get_huginn_home()
        assert (result / "skills").is_dir()
        assert (result / "pipelines").is_dir()
        assert (result / "tasks").is_dir()

    def test_respects_env_var(self, huginn_home):
        result = get_huginn_home()
        assert result == huginn_home

    def test_idempotent_second_call(self, huginn_home):
        first = get_huginn_home()
        second = get_huginn_home()
        assert first == second


# ---------------------------------------------------------------------------
# load_config / save_config
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_creates_default_config_when_missing(self, huginn_home):
        config = load_config()
        assert "backends" in config
        assert "default_backend" in config

    def test_default_backends_present(self, huginn_home):
        config = load_config()
        assert "i3" in config["backends"]
        assert "mac" in config["backends"]

    def test_returns_dict(self, huginn_home):
        config = load_config()
        assert isinstance(config, dict)

    def test_loads_custom_config(self, huginn_home):
        get_huginn_home()  # create dirs
        config_path = huginn_home / "config.yaml"
        custom = {
            "backends": {
                "mybackend": {"type": "ollama", "url": "http://10.0.0.1:11434"}
            },
            "default_backend": "mybackend",
        }
        with open(config_path, "w") as f:
            yaml.dump(custom, f)

        loaded = load_config()
        assert "mybackend" in loaded["backends"]
        assert loaded["default_backend"] == "mybackend"

    def test_merges_missing_keys_with_defaults(self, huginn_home):
        get_huginn_home()
        config_path = huginn_home / "config.yaml"
        # Write config that is missing some default keys
        partial = {"backends": {"my": {"type": "ollama", "url": "http://localhost:11434"}}}
        with open(config_path, "w") as f:
            yaml.dump(partial, f)

        loaded = load_config()
        # max_parallel_workers from DEFAULT_CONFIG should be merged in
        assert "max_parallel_workers" in loaded

    def test_save_and_reload(self, huginn_home):
        get_huginn_home()
        cfg = {
            "backends": {"local": {"type": "ollama", "url": "http://localhost:11434"}},
            "default_backend": "local",
        }
        save_config(cfg)
        loaded = load_config()
        assert loaded["default_backend"] == "local"


# ---------------------------------------------------------------------------
# get_backend_config / get_backend_url
# ---------------------------------------------------------------------------


class TestGetBackendConfig:
    def setup_method(self):
        self.config = {
            "backends": {
                "mac": {"type": "ollama", "url": "http://localhost:11434"},
                "i3": {"type": "ollama", "url": "http://192.168.2.135:11434"},
                "cloud": {
                    "type": "openrouter",
                    "url": "https://openrouter.ai/api/v1",
                    "api_key_env": "OPENROUTER_API_KEY",
                },
            },
            "default_backend": "mac",
        }

    def test_returns_named_backend(self):
        result = get_backend_config(self.config, "i3")
        assert result["url"] == "http://192.168.2.135:11434"

    def test_uses_default_backend_when_name_is_none(self):
        result = get_backend_config(self.config, None)
        assert result["url"] == "http://localhost:11434"

    def test_sets_default_type_to_ollama(self):
        result = get_backend_config(self.config, "mac")
        assert result["type"] == "ollama"

    def test_preserves_openrouter_type(self):
        result = get_backend_config(self.config, "cloud")
        assert result["type"] == "openrouter"

    def test_injects_backend_name(self):
        result = get_backend_config(self.config, "mac")
        assert result["name"] == "mac"

    def test_raises_for_unknown_backend(self):
        with pytest.raises(ValueError, match="not found"):
            get_backend_config(self.config, "nonexistent")

    def test_error_message_lists_available_backends(self):
        with pytest.raises(ValueError, match="mac"):
            get_backend_config(self.config, "ghost")

    def test_get_backend_url_returns_url_string(self):
        url = get_backend_url(self.config, "mac")
        assert url == "http://localhost:11434"


# ---------------------------------------------------------------------------
# resolve_model_name
# ---------------------------------------------------------------------------


class TestResolveModelName:
    def test_returns_same_name_when_no_map(self):
        backend = {"type": "ollama", "url": "http://localhost:11434"}
        assert resolve_model_name("qwen3:8b", backend) == "qwen3:8b"

    def test_maps_model_when_entry_exists(self):
        backend = {
            "type": "openrouter",
            "url": "https://openrouter.ai/api/v1",
            "model_map": {"qwen3:8b": "qwen/qwen3-8b"},
        }
        assert resolve_model_name("qwen3:8b", backend) == "qwen/qwen3-8b"

    def test_passthrough_for_unmapped_model(self):
        backend = {
            "type": "openrouter",
            "url": "https://openrouter.ai/api/v1",
            "model_map": {"qwen3:8b": "qwen/qwen3-8b"},
        }
        # Model not in map — passes through unchanged
        assert resolve_model_name("llama3:70b", backend) == "llama3:70b"

    def test_empty_model_map(self):
        backend = {"type": "openrouter", "url": "https://openrouter.ai/api/v1", "model_map": {}}
        assert resolve_model_name("qwen3:8b", backend) == "qwen3:8b"
