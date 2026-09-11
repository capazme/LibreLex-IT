# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import os
import stat
import sys

import pytest

from librelex_core import config as c


def test_defaults_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("LIBRELEX_LLM_API_KEY", raising=False)
    cfg = c.load_config(tmp_path / "missing.toml")
    assert cfg.llm.preset == "openrouter"
    assert cfg.mcp_legal_it.mode == "local"
    assert cfg.mcp_legal_it.command[0] == "uvx"
    assert cfg.document.redline_author == "librelex"
    assert cfg.limits.max_iterations == 12
    assert cfg.logging.enabled is False


def test_load_toml_and_env_override(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text(
        '[llm]\npreset = "ollama"\nbase_url = "http://localhost:11434/v1"\n'
        'api_key = "file-key"\n'
        '[mcp_legal_it]\nmode = "remote"\n'
        'remote_url = "https://example.org/legal-it/mcp"\nbearer = "b"\n'
        '[limits]\nmax_iterations = 3\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("LIBRELEX_LLM_API_KEY", "env-key")
    monkeypatch.setenv("LIBRELEX_MCP_BEARER", "env-bearer")
    cfg = c.load_config(path)
    assert cfg.llm.preset == "ollama" and cfg.llm.api_key == "env-key"
    assert cfg.mcp_legal_it.bearer == "env-bearer" and cfg.mcp_legal_it.mode == "remote"
    assert cfg.limits.max_iterations == 3 and cfg.limits.tool_timeout_s == 60


def test_remote_url_must_be_https(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[mcp_legal_it]\nmode = "remote"\nremote_url = "http://example.org/mcp"\n')
    with pytest.raises(c.ConfigError, match="https"):
        c.load_config(path)


def test_remote_url_localhost_http_allowed(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[mcp_legal_it]\nmode = "remote"\nremote_url = "http://127.0.0.1:8000/mcp"\n')
    assert c.load_config(path).mcp_legal_it.remote_url.startswith("http://127.0.0.1")


def test_invalid_toml_raises(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[llm\nbroken")
    with pytest.raises(c.ConfigError):
        c.load_config(path)


def test_invalid_config_error_does_not_leak_secret_value(tmp_path):
    # A stray key next to a real secret must not echo the secret's value in the error:
    # the core's stderr ends up in the extension log file (spec §5.2), which would
    # violate spec §8.1 "Keys never appear in logs" (review finding 4).
    path = tmp_path / "config.toml"
    path.write_text('[llm]\napi_key = "sk-LEAKED-98765"\napi_key_old = "sk-LEAKED-98765"\n')
    with pytest.raises(c.ConfigError) as exc_info:
        c.load_config(path)
    message = str(exc_info.value)
    assert "sk-LEAKED-98765" not in message
    assert "api_key_old" in message
    assert "Extra inputs are not permitted" in message


def test_config_path_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRELEX_CONFIG", str(tmp_path / "x.toml"))
    assert c.config_path() == tmp_path / "x.toml"


def test_config_dir_per_platform(monkeypatch):
    monkeypatch.delenv("LIBRELEX_CONFIG", raising=False)
    d = str(c.config_dir())
    if sys.platform == "darwin":
        assert d.endswith("Library/Application Support/LibreLex")
    elif sys.platform == "win32":
        assert d.endswith("LibreLex")
    else:
        assert d.endswith("librelex")


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")
def test_ensure_private(tmp_path):
    path = tmp_path / "cfg" / "config.toml"
    path.parent.mkdir()
    path.write_text("")
    c.ensure_private(path)
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_extension_section_and_private_dir(tmp_path):
    path = tmp_path / "cfg" / "config.toml"
    path.parent.mkdir()
    path.write_text('[extension]\nuv = "/opt/homebrew/bin/uv"\n', encoding="utf-8")
    cfg = c.load_config(path)
    assert cfg.extension.uv == "/opt/homebrew/bin/uv"
    if os.name == "posix":
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert c.load_config(tmp_path / "missing.toml").extension.uv == ""


def test_llm_endpoint_presets_and_custom_rules():
    ep = c.resolve_llm_endpoint(c.LLMConfig(preset="openrouter", api_key="k"))
    assert ep.base_url == "https://openrouter.ai/api/v1" and ep.host == "openrouter.ai"
    assert ep.headers["X-Title"] == "LibreLex-IT" and ep.headers["HTTP-Referer"].startswith("https://github.com/")
    assert ep.extra_body == {"provider": {"data_collection": "deny"}, "usage": {"include": True}}
    no_zdr = c.LLMConfig(preset="openrouter", zero_data_retention=False)
    assert c.resolve_llm_endpoint(no_zdr).extra_body == {"usage": {"include": True}}
    assert c.resolve_llm_endpoint(c.LLMConfig(preset="cliproxyapi")).base_url == \
        "http://127.0.0.1:8317/v1"
    assert c.resolve_llm_endpoint(c.LLMConfig(preset="ollama")).host == "localhost"
    custom = c.LLMConfig(preset="custom", base_url="https://llm.example.org/v1")
    assert c.resolve_llm_endpoint(custom).extra_body == {}
    with pytest.raises(c.ConfigError, match="base_url"):
        c.resolve_llm_endpoint(c.LLMConfig(preset="custom"))
    with pytest.raises(c.ConfigError, match="https"):
        c.resolve_llm_endpoint(c.LLMConfig(preset="custom", base_url="http://llm.example.org/v1"))
