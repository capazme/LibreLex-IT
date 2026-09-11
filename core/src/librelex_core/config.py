# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Configuration file (spec §8.1, Appendix D)."""
from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

MCP_LEGAL_IT_GIT = "git+https://github.com/capazme/mcp-legal-it@v2.14.0"


class ConfigError(Exception):
    """The configuration file is unreadable or invalid."""


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LLMConfig(_Section):
    preset: Literal["cliproxyapi", "openrouter", "ollama", "custom"] = "openrouter"
    base_url: str = "https://openrouter.ai/api/v1"
    api_key: str = ""
    model: str = ""
    zero_data_retention: bool = True


class McpConfig(_Section):
    mode: Literal["local", "remote"] = "local"
    command: list[str] = Field(
        default_factory=lambda: ["uvx", "--from", MCP_LEGAL_IT_GIT, "mcp-legal-it"]
    )
    remote_url: str = ""
    bearer: str = ""

    @field_validator("remote_url")
    @classmethod
    def _https_only(cls, v: str) -> str:
        if not v:
            return v
        u = urlparse(v)
        local = u.hostname in ("localhost", "127.0.0.1", "::1")
        if u.scheme != "https" and not local:
            raise ValueError("remote_url must use https:// (http:// is allowed only for localhost)")
        return v


class DocumentConfig(_Section):
    redline_author: Literal["librelex", "user"] = "librelex"
    verify_footnotes: bool = True


class LimitsConfig(_Section):
    max_iterations: int = 12
    turn_timeout_s: int = 180
    tool_timeout_s: int = 60
    session_token_ceiling: int = 400_000


class LoggingConfig(_Section):
    enabled: bool = False


class ExtensionConfig(_Section):
    """Read by the LibreOffice extension (stdlib tomllib), validated here so the file has one
    schema."""
    uv: str = ""   # absolute path of the uv binary when it is not on LibreOffice's PATH


class Config(_Section):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    mcp_legal_it: McpConfig = Field(default_factory=McpConfig)
    document: DocumentConfig = Field(default_factory=DocumentConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    extension: ExtensionConfig = Field(default_factory=ExtensionConfig)


def config_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "LibreLex"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / "LibreLex"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "librelex"


def config_path() -> Path:
    override = os.environ.get("LIBRELEX_CONFIG")
    return Path(override) if override else config_dir() / "config.toml"


def ensure_private(path: Path) -> None:
    """Directory 0700 and file 0600 (POSIX); no-op on Windows."""
    if os.name != "posix":
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    if path.exists():
        os.chmod(path, 0o600)


def load_config(path: Path | None = None) -> Config:
    path = path or config_path()
    try:
        ensure_private(path)   # directory 0700 / file 0600 on every load (spec §8.1)
    except OSError:
        pass                   # read-only or foreign location: loading still works
    data: dict = {}
    if path.exists():
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError) as e:
            raise ConfigError(f"cannot read {path}: {e}") from e
    try:
        cfg = Config.model_validate(data)
    except ValidationError as e:
        # Build the message from loc/msg only: pydantic's default str(e) embeds the
        # offending input value, which can be a secret (e.g. a stray llm.api_key_old
        # next to a real key). That message ends up in the extension's log file
        # (spec §5.2), violating spec §8.1 "Keys never appear in logs" (review finding 4).
        detail = "; ".join(
            f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}"
            for err in e.errors(include_url=False)
        )
        raise ConfigError(f"invalid configuration in {path}: {detail}") from e
    if key := os.environ.get("LIBRELEX_LLM_API_KEY"):
        cfg.llm.api_key = key
    if bearer := os.environ.get("LIBRELEX_MCP_BEARER"):
        cfg.mcp_legal_it.bearer = bearer
    return cfg
